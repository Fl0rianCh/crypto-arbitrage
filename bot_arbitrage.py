import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import asyncio
from telegram import Bot
import pandas as pd
import math
from telegram import Update
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import time 
from datetime import datetime
import os.path
import traceback
from decimal import Decimal
import logging
from decimal import ROUND_DOWN,ROUND_UP
import asyncio
from decimal import Decimal, InvalidOperation
import numpy as np
from logging.handlers import TimedRotatingFileHandler


# Configure logger with timed rotation
log_file = 'arbitrage.log'

# Set up a timed rotating file handler to create a new log file every day and keep 7 days of logs
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7)  # New log every day, keep last 7 days

# Define log format
formatter = logging.Formatter('%(asctime)s %(message)s')
handler.setFormatter(formatter)

# Set up the logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Adjust this level based on what you want to log (DEBUG, INFO, etc.)
logger.addHandler(handler)

# Start time for performance tracking
start_time = time.time()

# Load API keys from config.env file
load_dotenv('config.env')

binance_api_key = os.environ.get('binance_api_key')
binance_api_secret = os.environ.get('binance_api_secret')

kraken_api_key = os.environ.get('kraken_api_key')
kraken_api_secret = os.environ.get('kraken_api_secret')

kucoin_api_key = os.environ.get('kucoin_api_key')
kucoin_api_secret = os.environ.get('kucoin_api_secret')
kucoin_password = os.environ.get('kucoin_password')

# Load bot token and chat ID
bot_token = os.environ.get('TELEGRAM_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')

# Set the minimum time between messages of the Telegram Bot for each trading pair (in seconds)
min_message_interval = 60   # 1 minute

# Create a dictionary to keep track of the last time a message was sent for each trading pair
last_message_times = {}

# Retrieve all USDC pairs dynamically
def get_usdc_pairs(markets):
    return [symbol for symbol in markets.keys() if symbol.endswith('/USDC')]

# Load exchanges
kucoin = ccxt.kucoin({
    'apiKey': kucoin_api_key,
    'secret': kucoin_api_secret,
    'password': kucoin_password,
    'enableRateLimit': True
})

binance = ccxt.binance({
    'apiKey': binance_api_key,
    'secret': binance_api_secret,
    'enableRateLimit': True
})

kraken = ccxt.kraken({
    'apiKey': kraken_api_key,
    'secret': kraken_api_secret,
    'enableRateLimit': True
})

# Defining function for the telegram Bot, the first is sending message, the second is to stop the script with by sending a message to the bot
async def send_message(bot_token, chat_id, text):
    bot = Bot(bot_token)
    bot.send_message(chat_id=chat_id, text=text)

def stop_command(update: Update, context: CallbackContext):
    global running
    running = False
    update.message.reply_text('Stopping script')


# Function for executing trades
async def execute_trade(exchange, first_symbol, second_symbol, third_symbol, tickers, initial_amount, fee, first_tick_size, second_tick_size, third_tick_size):

    # Use adjusted trades (including fee)
    first_price = Decimal(tickers[first_symbol]['ask'])
    first_trade = (initial_amount / first_price) * (1 - Decimal(fee))
    first_trade = first_trade.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)

    # Place first order
    print(f'\nPlacing first order: {first_trade} {first_symbol}')
    order = await exchange.create_order(first_symbol, 'market', 'buy', float(first_trade))
    order_id = order['id']

    # Wait for first order to be filled
    while True:
        order = await exchange.fetch_order(order_id, first_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(3)

    # Retrieve actual amount of first trading pair bought
    first_trade = Decimal(order['filled'])

    # Use the entire amount of first trade for the second order
    second_trade = first_trade

    # Place second order
    print(f'Placing second order: {second_trade} {second_symbol}')
    order = await exchange.create_order(second_symbol, 'market', 'sell', float(second_trade))
    order_id = order['id']

    # Wait for second order to be filled
    while True:
        order = await exchange.fetch_order(order_id, second_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(3)

    # Retrieve actual cost of second trading pair
    second_trade = Decimal(order['cost'])

    # Use the entire cost of second trade for the third order
    third_trade = second_trade * (1 - Decimal(fee))

    # Place third order
    print(f'Placing third order: {third_trade} {third_symbol}')
    order = await exchange.create_order(third_symbol, 'market', 'sell', float(third_trade))
    order_id = order['id']

    while True:
        order = await exchange.fetch_order(order_id, third_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(3)
    
    # Fetch final balance
    balance = await exchange.fetch_balance()
    final_amount = balance['free']['USDC']

    # Calculate profit/loss
    profit = final_amount - initial_amount

    print(f'Trade completed: Initial amount: {initial_amount}, Final amount: {final_amount}, Profit: {profit}')

    # return profit and final amount if needed for further calculations or logging
    return profit,  final_amount


# Function for calculating the price impact of the order based on the orderbook asks, bids, and volumes
async def calculate_price_impact(exchange, symbols, order_sizes, sides):
    logging.info(f'Calculating price impact ')

    # Fetch order books concurrently
    order_books = await asyncio.gather(*[exchange.fetch_order_book(symbol) for symbol in symbols])
    logging.info(f'Order books fetched on {exchange}')
    price_impacts = []

    for i in range(len(symbols)):
        symbol = symbols[i]
        side = sides[i]
        order_size = float(order_sizes[i])
        order_book = order_books[i]
        
        # If we're buying, we need to look at the asks. If we're selling, we need to look at the bids.
        orders = np.array(order_book['asks']) if side == 'buy' else np.array(order_book['bids'])

        # Slice orders into prices and volumes
        prices, volumes = orders[:,0], orders[:,1]

        logging.info(f'Processing order book for {symbol} with side {side} and order size {order_size}')
        logging.info(f'Order book prices: {prices}')
        logging.info(f'Order book volumes: {volumes}')

        total_value = 0
        total_volume = 0

        for j in range(len(prices)):
            if order_size > 0:
                volume_for_this_order = min(volumes[j], order_size)
                value_for_this_order = volume_for_this_order * prices[j]

                logging.info(f'At price level {prices[j]}: volume_for_this_order={volume_for_this_order}, value_for_this_order={value_for_this_order}')

                total_value += value_for_this_order
                total_volume += volume_for_this_order
                order_size -= volume_for_this_order

        if order_size <= 0:
            # Calculate price impact
            price_impact = total_value / total_volume if total_volume != 0 else None
            logging.info(f'Price impact for {symbol}: {price_impact}')
            price_impacts.append(price_impact)
        else:
            # If order size was not completely filled, price impact can't be calculated
            price_impacts.append(None)
    
    return price_impacts

#Function for finding triangular arbitrage opportunities for each exchange
async def find_triangular_arbitrage_opportunities(exchange, markets, tickers, exchange_name, fee, initial_amount ):    
    
    logging.info('Finding arbitrage opportunities.')
    # Read existing trades from CSV file
    csv_file = 'tri_arb_opportunities.csv'
    
    if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
        # Create a CSV file with a default header if the file doesn't exist or is empty
        with open(csv_file, 'w') as f:
            f.write("exchange,order_size,first_symbol,second_symbol,third_symbol,first_price,second_price,third_price,profit_percentage,time\n")
        tri_arb_opportunities = []
    else:
        try:
            df = pd.read_csv(csv_file)
            tri_arb_opportunities = df.to_dict('records')
        except pd.errors.EmptyDataError:
            logging.warning("CSV file is empty, creating a new list of opportunities.")
            tri_arb_opportunities = []
    
    # Add a new variable to keep track of the last time a trade was added to the CSV file for each trading pair
    last_trade_time = {}
    
    # Load markets data and tickers
    markets = await exchange.load_markets(True)
    logging.info(f"Markets loaded for {exchange_name}: {len(markets)} pairs available")
    tickers = await exchange.fetch_tickers()
    
    # Dynamically get all USDC pairs
    usdc_symbols = get_usdc_pairs(markets)
    logging.info(f"USDC pairs available on {exchange_name}: {len(usdc_symbols)}")
    
    symbols_by_base = {}
    
    # Create a dictionary grouping symbols by their base currency
    for symbol in markets.keys():
        base, quote = symbol.split('/')
        if base not in symbols_by_base:
            symbols_by_base[base] = set()
        symbols_by_base[base].add(symbol)
    
    # Loop through all USDC symbols
    for usdc_symbol in usdc_symbols:
        first_symbol = usdc_symbol
        base, quote = usdc_symbol.split('/')
        second_base = base
        second_symbols = symbols_by_base.get(second_base, set())
        
        # Loop through all possible second symbols
        for second_symbol in second_symbols:
            unavailable_pairs = {'YGG/BNB', 'RAD/BNB', 'VOXEL/BNB', 'GLMR/BNB', 'UNI/EUR'}
            if second_symbol == first_symbol or second_symbol in unavailable_pairs:
                continue
            base, quote = second_symbol.split('/')
            if base == second_base:
                third_base = quote
            else:
                third_base = base
            # Third symbol 
            third_symbol = f'{third_base}/USDC'
            
            # Check if the trading pairs are valid on the exchange
            if third_symbol in markets and first_symbol in markets and second_symbol in markets:
                
                # Retrieve tick sizes for all trading pairs
                market = exchange.markets
                
                first_market = market[first_symbol]
                first_tick_size = first_market['precision']['price']
                
                second_market = market[second_symbol]
                second_tick_size = second_market['precision']['price']
                
                third_market = market[third_symbol]
                third_tick_size = third_market['precision']['price']
                
                if any(symbol not in tickers for symbol in [first_symbol, second_symbol, third_symbol]):
                    continue
                
                if all(tickers[symbol].get('ask') is not None for symbol in [first_symbol]) and all(tickers[symbol].get('bid') is not None for symbol in [second_symbol, third_symbol]):
                    first_price = Decimal(tickers[first_symbol]['ask'])
                    second_price = Decimal(tickers[second_symbol]['bid'])
                    third_price = Decimal(tickers[third_symbol]['bid'])
                    logging.info(f"Prices for {first_symbol}, {second_symbol}, {third_symbol} on {exchange_name}: {first_price}, {second_price}, {third_price}")
                else:
                    logging.warning(f"Price data missing for {first_symbol}, {second_symbol}, or {third_symbol} on {exchange_name}")
                    continue
    
                # Quantize the prices
                first_price = first_price.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)
                second_price = second_price.quantize(Decimal(str(second_tick_size)), rounding=ROUND_DOWN)
                third_price = third_price.quantize(Decimal(str(third_tick_size)), rounding=ROUND_DOWN)
                logging.info(f"Quantized prices for {first_symbol}, {second_symbol}, {third_symbol}: {first_price}, {second_price}, {third_price}")

                if not first_price or not second_price or not third_price:
                    continue

                # Check for zero prices to avoid division by zero
                if first_price == 0 or second_price == 0 or third_price == 0:
                    logging.warning(f"Invalid prices detected: {first_symbol}, {second_symbol}, {third_symbol}")
                    continue


                # Trades calculation
                first_trade = initial_amount / first_price
                first_trade = first_trade.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)
                
                second_trade = first_trade * second_price
                second_trade = second_trade.quantize(Decimal(str(second_tick_size)), rounding=ROUND_DOWN)

                third_trade = second_trade * third_price
                third_trade = third_trade.quantize(Decimal(str(third_tick_size)), rounding=ROUND_DOWN)

                # Check for negative trades
                if first_trade < 0 or second_trade < 0 or third_trade < 0:
                    continue
                
                # Calculate profits        
                profit = third_trade - initial_amount
                profit_percentage = (profit / initial_amount) * 100
                
                opportunities = []

                if profit_percentage > 0.08:
                    logging.info(f"Arbitrage opportunity found on {exchange_name} for {first_symbol} -> {second_symbol} -> {third_symbol} with profit_percentage: {profit_percentage:.2f}%")
                else:
                    logging.info(f"No profitable opportunity found for {first_symbol} -> {second_symbol} -> {third_symbol}. Profit: {profit_percentage:.2f}%")

                    opportunities.append({
                        'first_symbol': first_symbol,
                        'second_symbol': second_symbol,
                        'third_symbol': third_symbol,
                        'first_trade': first_trade,
                        'second_trade': second_trade,
                        'third_trade': third_trade,
                        'profit': profit,
                        'profit_percentage': profit_percentage
                    })

                    # Sort opportunities by profit percentage in descending order
                    opportunities.sort(key=lambda x: -x['profit_percentage'])

                    # Take the top 1 or 2 opportunities
                    top_opportunities = opportunities[:1]  # Change this to the number of opportunities you want to process

                    # Calculate price impacts for top opportunities
                    for opportunity in top_opportunities:
                        # Log prices before checking opportunity
                        logging.info(f'Before opportunity check on {exchange_name}: first_symbol= {first_symbol}, first_price = {first_price}, second_symbol = {second_symbol}, second_price = {second_price}, third_symbol = {third_symbol}, third_price = {third_price}, profit percentage: {profit_percentage}')

                        price_impacts = await calculate_price_impact(
                            exchange,
                            [opportunity['first_symbol'], opportunity['second_symbol'], opportunity['third_symbol']],
                            [initial_amount, opportunity['first_trade'], opportunity['second_trade']],
                            ['buy', 'sell', 'sell']
                        )

                        # Unpack the results
                        first_price_impact, second_price_impact, third_price_impact = price_impacts

                        # Quantize the price impacts
                        first_price_impact = Decimal(first_price_impact).quantize(Decimal(str(first_tick_size)), rounding=ROUND_UP)
                        second_price_impact = Decimal(second_price_impact).quantize(Decimal(str(second_tick_size)), rounding=ROUND_DOWN)
                        third_price_impact = Decimal(third_price_impact).quantize(Decimal(str(third_tick_size)), rounding=ROUND_DOWN)

                        # Calculate trades considering price impact and including fees
                        first_trade_before_fees = initial_amount / first_price_impact 
                        first_trade_amount = first_trade_before_fees * (1 - Decimal(fee))
                        first_trade_amount = first_trade_amount.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)

                        second_trade_before_fees = first_trade_amount * second_price_impact
                        second_trade_amount = second_trade_before_fees * (1 - Decimal(fee))  
                        second_trade_amount = second_trade_amount.quantize(Decimal(str(second_tick_size)), rounding=ROUND_DOWN)

                        third_trade_before_fees = second_trade_amount * third_price_impact
                        third_trade_amount = third_trade_before_fees * (1 - Decimal(fee))  
                        third_trade_amount = third_trade_amount.quantize(Decimal(str(third_tick_size)), rounding=ROUND_DOWN)

                        # Check real profit after price impact calculation and fees
                        real_profit = third_trade_amount - initial_amount
                        real_profit_percentage = (real_profit / initial_amount) * 100

                        logging.info(f'After liquidity check on {exchange_name}: first_symbol= {first_symbol}, first_price = {first_price_impact}, second_symbol = {second_symbol} second_price = {second_price_impact}, third_symbol = {third_symbol}, third_price = {third_price_impact}, profit percentage: {real_profit_percentage}')
                        
                        if real_profit_percentage > 0.08:
                            logging.info(f'Arbitrage opportunity confirmed on {exchange_name}.')
                            # Execute trades and send notification
                            profit, final_amount = await execute_trade(
                                exchange,
                                first_symbol,
                                second_symbol,
                                third_symbol,
                                tickers,
                                initial_amount,
                                fee,
                                first_tick_size,
                                second_tick_size,
                                third_tick_size
                            )
                                
                            print(f'Profitable trade found on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit percentage: {real_profit_percentage:.2f}%', 'Profit change after checks: ', real_profit-profit, ' USDC')

                            trade_key = f'{exchange_name}-{first_symbol}-{second_symbol}-{third_symbol}'
                            current_time = time.time()
                            last_message_time = last_message_times.get(trade_key, 0)
                            time_since_last_message = current_time - last_message_time

                            if time_since_last_message > min_message_interval:
                                message_text = f'Profitable trade found on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit: {profit:.2f}. Profit percentage: {profit_percentage:.2f}%'
                                await send_message(bot_token, chat_id, message_text)
                                last_message_times[trade_key] = current_time

                            # Check if a trade for the same trading pair has been added to the CSV file within the last minute
                            last_trade_time_for_pair= last_trade_time.get(trade_key, 0)
                            time_since_last_trade= current_time - last_trade_time_for_pair

                            # If a trade for the same trading pair has not been added to the CSV file within the last  5 minute,
                            # append trade_data to trades list and update last_trade_time[trade_key] with current time
                            if time_since_last_trade> 300:
                                trade_data= {
                                    'exchange': exchange_name,
                                    'order size (USDC)': initial_amount,
                                    'first_symbol': first_symbol,
                                    'second_symbol': second_symbol,
                                    'third_symbol': third_symbol,
                                    'first_price': first_price_impact,
                                    'second_price': second_price_impact,
                                    'third_price': third_price_impact,
                                    'profit_percentage': real_profit_percentage,
                                    'time':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                }
                                tri_arb_opportunities.append(trade_data)
                                last_trade_time[trade_key]= current_time
                        else:
                            logging.info(f'Arbitrage opportunity not confirmed on {exchange_name}.')
                            # Print arbitrage opportunity message
                            print(f'\rArbitrage opportunities found, checking liquidity | Opportunities not confirmed', end='\r')     

    # Write updated trades to CSV and Excell file
    df= pd.DataFrame(tri_arb_opportunities)
    df.to_csv(csv_file, index=False)
    

async def main():
    
    # Get user input on USDC initial amount
    while True:
        initial_amount_input = input("How many USDC do you want to trade? | Only numbers are accepted (in the form 1, 10, 20.1) \nUSDC amount:  ")
        try:
            # Try to convert the input to a Decimal
            initial_amount = Decimal(initial_amount_input)
            break  # If the conversion succeeds, break out of the loop
        except InvalidOperation:
            print("Please enter a valid number.")
    
    # Set up the updater and dispatcher
    updater = Updater(bot_token)
    dispatcher = updater.dispatcher
    
    # Add a command handler for the /stop command
    dispatcher.add_handler(MessageHandler(Filters.regex('^/stop$'), stop_command))
    
    # Start the updater
    updater.start_polling()
    
    # Message from the Telegram Bot
    await send_message(bot_token, chat_id, "Finding arbitrage opportunities...")
    global running
    running = True
    
    print('\nFinding arbitrage opportunities...')
    
    iteration_count = 1 # initialize iteration counter
    while running:
        try:
            binance_markets, binance_tickers, kucoin_markets, kucoin_tickers, kraken_markets, kraken_tickers = await asyncio.gather(
                binance.load_markets(True),
                binance.fetch_tickers(),
                kucoin.load_markets(True),
                kucoin.fetch_tickers(),
                kraken.load_markets(True),
                kraken.fetch_tickers()
            )

            # Set fees for all exchanges
            binance_fee = 0.0007
            kucoin_fee = 0.001
            kraken_fee = 0.001           
         
            # Search for arbitrage opportunities on all exchanges concurrently
            await asyncio.gather(
                find_triangular_arbitrage_opportunities(binance, binance_markets, binance_tickers, 'Binance', binance_fee, initial_amount),
                find_triangular_arbitrage_opportunities(kucoin, kucoin_markets, kucoin_tickers, 'Kucoin', kucoin_fee, initial_amount),
                find_triangular_arbitrage_opportunities(kraken, kraken_markets, kraken_tickers, 'Kraken', kraken_fee, initial_amount )
            )
            end_time = time.time()
            elapsed_time = end_time - start_time
            # Print elapsed time and number of iterations
            print(f'\n\rElapsed time: {elapsed_time:.2f} seconds | Number of iterations: {iteration_count}', end='\r')

            iteration_count += 1 # increment iteration counter
            
            await asyncio.sleep(10) # sleep for 15 seconds before starting next iteration
        
        except Exception as e:
            print(f'An error occurred: {e}')
            traceback.print_exc()
    
    # Stop the updater when the script is stopped
    updater.stop()
    
    # Release resources used by the exchange instances
    await binance.close()
    await kucoin.close()
    await kraken.close()

if __name__ == "__main__":
    asyncio.run(main())
