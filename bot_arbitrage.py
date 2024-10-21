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


logging.basicConfig(filename='arbitrage.log', level=logging.INFO, format='%(asctime)s %(message)s')
start_time = time.time()

# Load API keys from config.env file
load_dotenv('config.env')

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

#Load exchanges

kraken = ccxt.kraken({
    'apiKey': kraken_api_key,
    'secret': kraken_api_secret,
    'enableRateLimit': True
})

kucoin = ccxt.kucoin({
    'apiKey': kucoin_api_key,
    'secret': kucoin_api_secret,
    'password': kucoin_password,
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
async def execute_trade(exchange, first_symbol, second_symbol, third_symbol, tickers, initial_amount, first_tick_size, second_tick_size, third_tick_size):
    # Calculate the amount for the first trade (buying the first asset)
    first_price = Decimal(tickers[first_symbol]['ask'])
    first_trade = initial_amount / first_price
    first_trade = first_trade.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)

    # Place the first order to buy the first asset
    print(f'\nPlacing first order: {first_trade} {first_symbol}')
    order = await exchange.create_order(first_symbol, 'market', 'buy', float(first_trade))
    order_id = order['id']

    # Wait for the first order to be filled
    while True:
        order = await exchange.fetch_order(order_id, first_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(1)

    # Retrieve the actual amount bought in the first trade
    first_trade = Decimal(order['filled'])

    # Use the entire amount from the first trade for the second trade (selling for the second asset)
    second_trade = first_trade

    # Place the second order to sell the first asset for the second asset
    print(f'Placing second order: {second_trade} {second_symbol}')
    order = await exchange.create_order(second_symbol, 'market', 'sell', float(second_trade))
    order_id = order['id']

    # Wait for the second order to be filled
    while True:
        order = await exchange.fetch_order(order_id, second_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(1)

    # Retrieve the amount received in the second trade
    second_trade = Decimal(order['cost'])

    # Use the amount from the second trade for the third trade (selling for USDT)
    third_trade = second_trade

    # Place the third order to sell the second asset for USDT
    print(f'Placing third order: {third_trade} {third_symbol}')
    order = await exchange.create_order(third_symbol, 'market', 'sell', float(third_trade))
    order_id = order['id']

    # Wait for the third order to be filled
    while True:
        order = await exchange.fetch_order(order_id, third_symbol)
        if order['status'] == 'closed':
            break
        await asyncio.sleep(1)
    
    balance = await exchange.fetch_balance()
    final_amount = balance['free']['USDT']

    # Calculate profit including fees
    fee = Decimal('0.001')  # Assuming a 0.1% fee per trade
    total_fee = (first_trade * first_price * fee) + (second_trade * first_price * fee) + (third_trade * first_price * fee)
    profit = final_amount - initial_amount - total_fee
    print(f'Trade completed: Initial amount: {initial_amount}, Final amount: {final_amount}, Profit: {profit}')
    return profit, final_amount

# Function for calculating the price impact of the order based on the orderbook asks, bids, and volumes
async def calculate_price_impact(exchange, symbols, order_sizes, sides):
    logging.info(f'Calculating price impact')
    
    # Fetch order books for multiple symbols in parallel with a limit of 100 orders per book
    order_books = await asyncio.gather(
        *[exchange.fetch_order_book(symbol, limit=100) for symbol in symbols]
    )
    logging.info(f'Order books fetched on {exchange}')
    
    price_impacts = []
    slippage_margin = Decimal("0.002")  # Default slippage margin
    min_volume_threshold = Decimal("0.0001")  # Filter levels with very low volume

    for i in range(len(symbols)):
        symbol = symbols[i]
        side = sides[i]
        order_size = Decimal(order_sizes[i])
        order_book = order_books[i]
        
        # Extract prices and volumes from the order book
        prices, volumes = np.array(order_book['asks' if side == 'buy' else 'bids']).T
        total_cost = 0
        total_volume = 0
        remaining_order_size = order_size

        # Calculate the spread between the bid and ask to adjust slippage dynamically
        best_bid = order_book['bids'][0][0]
        best_ask = order_book['asks'][0][0]
        spread = (best_ask - best_bid) / best_ask
        dynamic_slippage = max(Decimal("0.002"), Decimal(spread) * 2)  # Adjusted slippage

        # Iterate through the price levels to calculate the total cost for the required order size
        for j in range(len(prices)):
            price = Decimal(prices[j])
            volume_available = Decimal(volumes[j])
            
            if volume_available < min_volume_threshold:
                logging.info(f'Volume at price {price} for {symbol} is too low, skipping this level')
                continue  # Skip levels with very low volume

            if remaining_order_size <= volume_available:
                total_cost += remaining_order_size * price
                total_volume += remaining_order_size
                break  # The order is completely executed
            else:
                logging.info(f'Not enough volume at price {price} for {symbol}, moving to next level')
                total_cost += volume_available * price
                total_volume += volume_available
                remaining_order_size -= volume_available  # Reduce the remaining order size

        if total_volume > 0:
            # Calculate the weighted average price considering slippage
            price_impact = total_cost / total_volume
            price_impact = price_impact * (1 + dynamic_slippage) if side == 'buy' else price_impact * (1 - dynamic_slippage)
            logging.info(f'Price impact for {symbol}: {price_impact}')
            price_impacts.append(price_impact)
        else:
            logging.warning(f'Insufficient liquidity for {symbol}')
            price_impacts.append(None)  # Mark as not viable

    return price_impacts

#Function for finding triangular arbitrage opportunities for each exchange
async def find_triangular_arbitrage_opportunities(exchange, markets, tickers, exchange_name, fee, initial_amount):
    logging.info('Finding arbitrage opportunities.')
    min_liquidity = Decimal("10000")  # Seuil minimal de liquidité

    # Read existing trades from CSV file
    csv_file = 'tri_arb_opportunities.csv'
    
    if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
        df = pd.read_csv(csv_file)
        tri_arb_opportunities = df.to_dict('records')
    else:
        tri_arb_opportunities = []

    # Add a new variable to keep track of the last time a trade was added to the CSV file for each trading pair
    last_trade_time = {}

    # Load markets data
    markets = await exchange.load_markets(True)
    symbols = list(markets.keys())
    tickers = await exchange.fetch_tickers()

    # Create a dictionary with all the USDT symbols
    usdt_symbols = {symbol for symbol in markets.keys() if symbol.endswith('/USDT')}
    symbols_by_base = {}

    for symbol in markets.keys():
        base, quote = symbol.split('/')
        if base not in symbols_by_base:
            symbols_by_base[base] = set()
        symbols_by_base[base].add(symbol)

    # Split the first symbol in base and quote
    for usdt_symbol in usdt_symbols:
        first_symbol = usdt_symbol
        base, quote = usdt_symbol.split('/')
        second_base = base
        second_symbols = symbols_by_base.get(second_base, set())

        # Loop to find all the possible second symbols
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
            third_symbol = f'{third_base}/USDT'

            # Check if trading pairs are valid on the exchange
            if third_symbol in markets and first_symbol in markets and second_symbol in markets:

                # Retrieve tick size for all trading pairs
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
                else:
                    continue

                # Quantize the prices
                first_price = first_price.quantize(Decimal(str(first_tick_size)), rounding=ROUND_DOWN)
                second_price = second_price.quantize(Decimal(str(second_tick_size)), rounding=ROUND_DOWN)
                third_price = third_price.quantize(Decimal(str(third_tick_size)), rounding=ROUND_DOWN)

                if not first_price or not second_price or not third_price:
                    continue

                # Check for zero prices to avoid division by zero
                if first_price == 0 or second_price == 0 or third_price == 0:
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

                # Improved liquidity check across multiple levels
                order_books = await asyncio.gather(
                    exchange.fetch_order_book(first_symbol, limit=100),
                    exchange.fetch_order_book(second_symbol, limit=100),
                    exchange.fetch_order_book(third_symbol, limit=100)
                )

                first_order_book, second_order_book, third_order_book = order_books

                def is_liquidity_sufficient(order_book, required_amount, side):
                    total_volume = Decimal(0)
                    levels = order_book['asks' if side == 'buy' else 'bids']

                    for price, volume in levels:
                        total_volume += Decimal(volume)
                        if total_volume >= required_amount:
                            return True
                    return False

                # Check if there's enough liquidity in the order books for the trades
                if (not is_liquidity_sufficient(first_order_book, first_trade, 'buy') or
                        not is_liquidity_sufficient(second_order_book, first_trade, 'sell') or
                        not is_liquidity_sufficient(third_order_book, second_trade, 'sell')):
                    logging.info(f'Not enough liquidity for arbitrage on {exchange_name}: {first_symbol}, {second_symbol}, {third_symbol}')
                    continue

                # Calculate profits
                profit = third_trade - initial_amount
                profit_percentage = (profit / initial_amount) * 100

                opportunities = []

                if profit_percentage > 0.8:
                    logging.info(f'Arbitrage opportunity found. Executing trades on {exchange_name}...')
                    print(f'\rArbitrage opportunities found, executing trades', end='\r')

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

                    # Take the top 1 opportunity
                    top_opportunities = opportunities[:1]

                    for opportunity in top_opportunities:
                        # Execute trades
                        profit, final_amount = await execute_trade(
                            exchange,
                            first_symbol,
                            second_symbol,
                            third_symbol,
                            tickers,
                            initial_amount,
                            first_tick_size,
                            second_tick_size,
                            third_tick_size
                        )

                        print(f'Profitable trade found on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit percentage: {profit_percentage:.2f}%')

                        trade_key = f'{exchange_name}-{first_symbol}-{second_symbol}-{third_symbol}'
                        current_time = time.time()
                        last_message_time = last_message_times.get(trade_key, 0)
                        time_since_last_message = current_time - last_message_time

                        if time_since_last_message > min_message_interval:
                            message_text = f'Profitable trade found on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit: {profit:.2f}. Profit percentage: {profit_percentage:.2f}%'
                            await send_message(bot_token, chat_id, message_text)
                            last_message_times[trade_key] = current_time

                        # Record the trade
                        last_trade_time_for_pair = last_trade_time.get(trade_key, 0)
                        time_since_last_trade = current_time - last_trade_time_for_pair

                        if time_since_last_trade > 300:
                            trade_data = {
                                'exchange': exchange_name,
                                'order size (USDT)': initial_amount,
                                'first_symbol': first_symbol,
                                'second_symbol': second_symbol,
                                'third_symbol': third_symbol,
                                'first_price': first_price,
                                'second_price': second_price,
                                'third_price': third_price,
                                'profit_percentage': profit_percentage,
                                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            }
                            tri_arb_opportunities.append(trade_data)
                            last_trade_time[trade_key] = current_time

    # Write updated trades to CSV file
    df = pd.DataFrame(tri_arb_opportunities)
    df.to_csv(csv_file, index=False)   

async def main():
    
    # Get user input on USDT initial amount
    while True:
        initial_amount_input = input("How many USDT do you want to trade? | Only numbers are accepted (in the form 1, 10, 20.1) \nUSDT amount:  ")
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
    await send_message(bot_token, chat_id, "Ok lets go ! Finding arbitrage opportunities...")
    global running
    running = True
    
    print('\nFinding arbitrage opportunities...')
    
    iteration_count = 1 # initialize iteration counter
    while running:
        try:
            # Load markets and tickers for all exchanges concurrently
            kucoin_markets, kucoin_tickers, kraken_markets, kraken_tickers = await asyncio.gather(
                kucoin.load_markets(True),
                kucoin.fetch_tickers(),
                kraken.load_markets(True),
                kraken.fetch_tickers()
            )

            # Set fees for all exchanges
            kucoin_fee = 0.001
            kraken_fee = 0.001          
         
            # Search for arbitrage opportunities on all exchanges concurrently
            await asyncio.gather(
                find_triangular_arbitrage_opportunities(kucoin, kucoin_markets, kucoin_tickers, 'Kucoin', kucoin_fee, initial_amount),
                find_triangular_arbitrage_opportunities(kraken, kraken_markets, kraken_tickers, 'Kraken', kraken_fee, initial_amount )
            )
            end_time = time.time()
            elapsed_time = end_time - start_time
            # Print elapsed time and number of iterations
            print(f'\n\rElapsed time: {elapsed_time:.2f} seconds | Number of iterations: {iteration_count}', end='\r')

            iteration_count += 1 # increment iteration counter
            
            await asyncio.sleep(3) # sleep for 3 seconds before starting next iteration
        
        except Exception as e:
            print(f'An error occurred: {e}')
            traceback.print_exc()
    
    # Stop the updater when the script is stopped
    updater.stop()
    
    # Release resources used by the exchange instances
    await kucoin.close()
    await kraken.close()

if __name__ == "__main__":
    asyncio.run(main())
