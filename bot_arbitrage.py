import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
import ccxt  # ccxt directement
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
from decimal import ROUND_DOWN, ROUND_UP
import numpy as np
import tracemalloc  # Import tracemalloc pour la gestion de la mémoire
import psutil
import time
import gc

# Gestion des erreurs ccxt (corrected import)
ccxt_errors = ccxt

logging.basicConfig(filename='arbitrage.log', level=logging.INFO, format='%(asctime)s %(message)s')
start_time = time.time()

# Démarrer le suivi de la mémoire
tracemalloc.start()

def log_memory_usage(message):
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    logging.info(f"{message}: RSS={mem_info.rss / (1024 * 1024):.2f} MB, VMS={mem_info.vms / (1024 * 1024):.2f} MB")

def display_top(snapshot, key_type='lineno', limit=10):
    top_stats = snapshot.statistics(key_type)
    print(f"Top {limit} lignes qui consomment le plus de mémoire :")
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        print(f"#{index}: {frame.filename}:{frame.lineno} - {stat.size / 1024:.1f} KiB")
        
async def load_markets_with_profiling(exchange):
    log_memory_usage(f"Before loading markets for {exchange.id}")
    start_time = time.time()
    markets = await load_markets_with_reconnect(exchange)
    elapsed_time = time.time() - start_time
    log_memory_usage(f"After loading markets for {exchange.id}")
    logging.info(f"Time taken to load markets for {exchange.id}: {elapsed_time:.2f} seconds")
    return markets

async def fetch_tickers_with_profiling(exchange, allowed_pairs):
    log_memory_usage(f"Before fetching tickers for {exchange.id}")
    start_time = time.time()
    tickers = await fetch_specific_tickers_with_reconnect(exchange, allowed_pairs)
    elapsed_time = time.time() - start_time
    log_memory_usage(f"After fetching tickers for {exchange.id}")
    logging.info(f"Time taken to fetch tickers for {exchange.id}: {elapsed_time:.2f} seconds")
    return tickers

# Load API keys from config.env file
load_dotenv('config.env')

binance_api_key = os.environ.get('binance_api_key')
binance_api_secret = os.environ.get('binance_api_secret')

coinbase_api_key = os.environ.get('coinbase_api_key')
coinbase_api_secret = os.environ.get('coinbase_api_secret')

kraken_api_key = os.environ.get('kraken_api_key')
kraken_api_secret = os.environ.get('kraken_api_secret')

kucoin_api_key = os.environ.get('kucoin_api_key')
kucoin_api_secret = os.environ.get('kucoin_api_secret')
kucoin_password = os.environ.get('kucoin_password')

# Load bot token and chat ID
bot_token = os.environ.get('telegram_token')
chat_id = os.environ.get('chat_id')

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

binance = ccxt.binance({
    'apiKey': binance_api_key,
    'secret': binance_api_secret,
    'enableRateLimit': True
})

coinbase = ccxt.coinbase({
    'apiKey': coinbase_api_key,
    'secret': coinbase_api_secret,
    'enableRateLimit': True
})

binance.verbose = True
kucoin.verbose = True
coinbase.verbose = True
kraken.verbose = True

# Function to load markets with reconnection logic
async def load_markets_with_reconnect(exchange, retry_delay=10, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            # Vérifiez si load_markets est asynchrone dans ccxt.async_support
            return await exchange.load_markets(True)  # Assurez-vous que load_markets est bien une coroutine async
        except (ccxt_errors.NetworkError, ccxt_errors.RequestTimeout) as e:
            retries += 1
            logging.error(f"Failed to load markets for {exchange.id}. Attempt {retries}/{max_retries}. Error: {str(e)}")
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logging.error(f"Unexpected error for {exchange.id}: {str(e)}")
            break
    logging.error(f"Failed to load markets for {exchange.id} after {max_retries} attempts.")
    return None

# Optimisation de la fonction fetch_specific_tickers_with_reconnect
async def fetch_specific_tickers_with_reconnect(exchange, symbols, retry_delay=10, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            # Supposons que fetch_ticker est bien une méthode async de ccxt.async_support
            tickers = {}
            for symbol in symbols:
                ticker = await exchange.fetch_ticker(symbol)  # Assurez-vous que fetch_ticker est bien asynchrone
                tickers[symbol] = ticker

            return tickers

        except (ccxt_errors.NetworkError, ccxt_errors.RequestTimeout) as e:
            retries += 1
            logging.error(f"Failed to fetch tickers for {exchange.id}. Attempt {retries}/{max_retries}. Error: {str(e)}")
            await asyncio.sleep(retry_delay)
        except Exception as e:
            logging.error(f"Unexpected error for {exchange.id}: {str(e)}")
            break

    logging.error(f"Failed to fetch tickers for {exchange.id} after {max_retries} attempts.")
    return None

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
        await asyncio.sleep(1)

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
        await asyncio.sleep(1)

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
        await asyncio.sleep(1)
    
    # Fetch final balance
    balance = await exchange.fetch_balance()
    final_amount = balance['free']['USDC']

    # Calculate profit/loss
    profit = final_amount - initial_amount

    print(f'Trade completed: Initial amount: {initial_amount}, Final amount: {final_amount}, Profit: {profit}')
    
    # Send Telegram message after trade completion
    await send_message(bot_token, chat_id, f'Trade completed on {exchange.id}: Initial amount: {initial_amount}, Final amount: {final_amount}, Profit: {profit} USDC')

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

async def find_triangular_arbitrage_opportunities(exchange, markets, tickers, exchange_name, fee, initial_amount ):    
    
    logging.info('Finding arbitrage opportunities.')
    # Read existing trades from CSV file
    csv_file = 'tri_arb_opportunities.csv'
    
    if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
        df = pd.read_csv(csv_file)
        tri_arb_opportunities = df.to_dict('records')
    else:
        tri_arb_opportunities = []
    
    # Add a new variable to keep track of the last time a trade was added to the CSV file for each trading pair
    last_trade_time = {}
    
    # Filter to only consider the specific pairs BTC/USDC, ETH/USDC, BTC/ETH
    allowed_pairs = ['BTC/USDC', 'ETH/USDC', 'BTC/ETH']
    
    # Load markets data
    tickers = await exchange.fetch_tickers()

    for first_symbol in allowed_pairs:
        # Check if first symbol is available in the exchange tickers
        if first_symbol not in tickers or tickers[first_symbol].get('ask') is None or tickers[first_symbol].get('bid') is None:
            continue
        
        first_price = Decimal(tickers[first_symbol]['ask'])
        base, quote = first_symbol.split('/')
        
        # Define the second and third symbols depending on the first pair
        if first_symbol == 'BTC/USDC':
            second_symbol = 'BTC/ETH'
            third_symbol = 'ETH/USDC'
        elif first_symbol == 'ETH/USDC':
            second_symbol = 'ETH/BTC'
            third_symbol = 'BTC/USDC'
        elif first_symbol == 'BTC/ETH':
            second_symbol = 'BTC/USDC'
            third_symbol = 'ETH/USDC'
        else:
            continue
        
        # Verify the second and third symbols exist in the tickers and have valid ask/bid prices
        if all(symbol in tickers and tickers[symbol].get('ask') is not None and tickers[symbol].get('bid') is not None for symbol in [second_symbol, third_symbol]):
            second_price = Decimal(tickers[second_symbol]['bid'])
            third_price = Decimal(tickers[third_symbol]['bid'])
        else:
            continue
        
        # Calculate trades
        first_trade = initial_amount / first_price
        second_trade = first_trade * second_price
        third_trade = second_trade * third_price

        # Quantize the trades (for precision)
        first_trade = first_trade.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        second_trade = second_trade.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        third_trade = third_trade.quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)

        # Calculate profit
        profit = third_trade - initial_amount
        profit_percentage = (profit / initial_amount) * 100
        
        if profit_percentage > 0.1:  # Threshold for minimal profit to trigger the opportunity
            logging.info(f'Arbitrage opportunity found on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit: {profit_percentage:.2f}%')

            # Add opportunity to the list
            opportunities = {
                'first_symbol': first_symbol,
                'second_symbol': second_symbol,
                'third_symbol': third_symbol,
                'profit_percentage': profit_percentage,
                'profit': profit,
                'first_trade': first_trade,
                'second_trade': second_trade,
                'third_trade': third_trade,
            }

            # Log opportunity and trigger trade execution if required
            await send_message(bot_token, chat_id, f'Arbitrage opportunity on {exchange_name}: {first_symbol} -> {second_symbol} -> {third_symbol}. Profit: {profit:.2f} USDC')

            # Sort opportunities by profit percentage in descending order (optional)
            tri_arb_opportunities.append(opportunities)

    # Après avoir écrit les opportunités dans le fichier CSV, vider la liste pour économiser la mémoire
    df = pd.DataFrame(tri_arb_opportunities)
    df.to_csv(csv_file, index=False)

    # Nettoyer la liste pour libérer la mémoire
    tri_arb_opportunities.clear()  # Nettoyer la mémoire des opportunités
    gc.collect()  # Forcer le garbage collector



async def main():
    # Montant initial par défaut en USDC (exemple : 10 USDC)
    initial_amount = Decimal('10')
    
    # Configuration du bot Telegram
    updater = Updater(bot_token)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(MessageHandler(Filters.regex('^/stop$'), stop_command))
    updater.start_polling()
    
    # Envoyer un message à Telegram pour indiquer que le bot démarre
    await send_message(bot_token, chat_id, "Recherche d'opportunités...")
    
    global running
    running = True
    
    # Limiter les paires de trading aux 3 paires spécifiques
    allowed_pairs = ['BTC/USDC', 'ETH/USDC', 'BTC/ETH']
    
    print('\nFinding arbitrage opportunities...')
    
    iteration_count = 1  # Initialiser le compteur d'itérations
    
    while running:
        try:
            # Utilisation de la fonction de reconnexion pour charger les marchés et les tickers
            log_memory_usage("Before loading binance markets")
            binance_markets = await load_markets_with_reconnect(binance)
            log_memory_usage("After loading binance markets")
            
            log_memory_usage("Before loading kucoin markets")
            kucoin_markets = await load_markets_with_reconnect(kucoin)
            log_memory_usage("After loading kucoin markets")
            
            log_memory_usage("Before loading coinbase markets")
            coinbase_markets = await load_markets_with_reconnect(coinbase)
            log_memory_usage("After loading coinbase markets")
            
            log_memory_usage("Before loading kraken markets")
            kraken_markets = await load_markets_with_reconnect(kraken)
            log_memory_usage("After loading kraken markets")

            log_memory_usage("Before tickers binance markets")
            binance_tickers = await fetch_specific_tickers_with_reconnect(binance, allowed_pairs)
            log_memory_usage("After tickers binance markets")
            
            log_memory_usage("Before tickers kucoin markets")
            kucoin_tickers = await fetch_specific_tickers_with_reconnect(kucoin, allowed_pairs)
            log_memory_usage("After tickers binance markets")
            
            log_memory_usage("Before tickers coinbase markets")
            coinbase_tickers = await fetch_specific_tickers_with_reconnect(coinbase, allowed_pairs)
            log_memory_usage("After tickers binance markets")
            
            log_memory_usage("Before tickers kraken markets")
            kraken_tickers = await fetch_specific_tickers_with_reconnect(kraken, allowed_pairs)
            log_memory_usage("After tickers binance markets")

            if binance_markets and kucoin_markets and coinbase_markets and kraken_markets:
                # Définir les frais pour chaque plateforme
                binance_fee = 0.00075
                kucoin_fee = 0.001
                coinbase_fee = 0.002
                kraken_fee = 0.0016           

                # Rechercher des opportunités d'arbitrage en parallèle sur toutes les plateformes
                await asyncio.gather(
                    find_triangular_arbitrage_opportunities(binance, binance_markets, binance_tickers, 'Binance', binance_fee, initial_amount),
                    find_triangular_arbitrage_opportunities(kucoin, kucoin_markets, kucoin_tickers, 'Kucoin', kucoin_fee, initial_amount),
                    find_triangular_arbitrage_opportunities(coinbase, coinbase_markets, coinbase_tickers, 'Coinbase', coinbase_fee, initial_amount),
                    find_triangular_arbitrage_opportunities(kraken, kraken_markets, kraken_tickers, 'Kraken', kraken_fee, initial_amount)
                )

            # Libérer explicitement la mémoire après chaque cycle d'appels API
            binance_tickers.clear()
            kucoin_tickers.clear()
            coinbase_tickers.clear()
            kraken_tickers.clear()
            
            gc.collect()  # Force garbage collection
            log_memory_usage("After garbage collection")

            # Afficher le temps écoulé et le nombre d'itérations
            end_time = time.time()
            elapsed_time = end_time - start_time
            print(f'\n\rElapsed time: {elapsed_time:.2f} seconds | Number of iterations: {iteration_count}', end='\r')

            iteration_count += 1  # Incrémenter le compteur d'itérations
            
            await asyncio.sleep(30)  # Pause de 30 secondes avant la prochaine itération
        
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            traceback.print_exc()
            await send_message(bot_token, chat_id, f"Le bot a rencontré une erreur: {str(e)}")
    
    # Capturer un snapshot final de la mémoire après l'exécution
    snapshot_final = tracemalloc.take_snapshot()
    print("Snapshot final de la mémoire après l'exécution")
    display_top(snapshot_final)

    # Arrêter le bot Telegram quand le script est arrêté
    updater.stop()
    
    # Libérer les ressources utilisées par les plateformes d'échange
    await binance.close()
    await kucoin.close()
    await coinbase.close()
    await kraken.close()

if __name__ == "__main__":
    # Capture initiale de la mémoire
    snapshot_initial = tracemalloc.take_snapshot()
    print("Snapshot initial de la mémoire au démarrage")
    display_top(snapshot_initial)

    asyncio.run(main())
