import os
import time
import ccxt
import logging
from decimal import Decimal
from dotenv import load_dotenv
from telegram import Bot

load_dotenv('config.env')

# Configurations
INVESTMENT = Decimal('300')  # EUR initial investment
GRID_LEVELS = 5  # Number of grid levels
GRID_SPACING_PERCENT = Decimal('1.5')  # Grid spacing as a percentage of the price
STOP_LOSS_PERCENT = Decimal('10')  # Stop-loss at 10% below initial investment
TAKE_PROFIT_PERCENT = Decimal('15')  # Take-profit at 15% above initial investment
FEE_PERCENT = Decimal('0.1')  # Fee as 0.1% per trade on Binance

# Load Binance API keys from environment
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', filename='arbitrage.log')
logger = logging.getLogger(__name__)

# Initialize Binance exchange
exchange = ccxt.binance({
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET_KEY,
    'enableRateLimit': True
})

# Choose the trading pairs to operate on
TRADING_PAIRS = ['BTC/USDC']  # Suitable high liquidity trading pairs

# Calculate the investment in USDC
initial_balance = INVESTMENT  # Assuming EUR to USDC conversion is handled externally

pair_balance = initial_balance / len(TRADING_PAIRS)

# Initialize Telegram Bot
bot = Bot(token=TELEGRAM_TOKEN)

# Function to send Telegram notifications
def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

# Function to place limit orders at grid levels and execute them
def place_grid_orders(current_price, trading_pair, balance):
    grid_orders = []
    base_order_size = balance / (GRID_LEVELS * current_price)

    # Check if base order size meets the minimum requirement
    market = exchange.market(trading_pair)
    min_order_size = market['limits']['amount']['min']
    if base_order_size < min_order_size:
        logger.error(f"Base order size {base_order_size} is below the minimum required {min_order_size} for {trading_pair}.")
        send_telegram_message(f"Base order size {base_order_size} is below the minimum required {min_order_size} for {trading_pair}. Adjusting grid levels or balance may be needed.")
        return []

    for i in range(GRID_LEVELS):
        price = current_price * (1 + GRID_SPACING_PERCENT / 100) ** (i - GRID_LEVELS // 2)
        order_type = 'buy' if price < current_price else 'sell'

        order = {
            'symbol': trading_pair,
            'price': round(price, 2),
            'size': round(base_order_size, 6),
            'type': order_type
        }

        # Ensure the order size meets the minimum requirement before placing
        if order['size'] < min_order_size:
            logger.error(f"Order size {order['size']} is below the minimum required {min_order_size} for {trading_pair}. Skipping this order.")
            continue

        grid_orders.append(order)

        # Execute the order immediately
        execute_order(order)

    return grid_orders

# Function to execute a limit order
def execute_order(order):
    try:
        if order['type'] == 'buy':
            response = exchange.create_limit_buy_order(order['symbol'], order['size'], order['price'])
        else:
            response = exchange.create_limit_sell_order(order['symbol'], order['size'], order['price'])
        logger.info(f"{order['type'].capitalize()} order placed: {order}")
        send_telegram_message(f"{order['type'].capitalize()} order placed: {order}")
    except Exception as e:
        logger.error(f"Failed to place {order['type']} order: {order}, Error: {e}")
        send_telegram_message(f"Failed to place {order['type']} order: {order}, Error: {e}")

# Function to check stop-loss or take-profit
def check_stop_take_profit(current_price, trading_pair, balance):
    open_orders = exchange.fetch_open_orders(trading_pair)
    if not open_orders:
        logger.info(f"No open positions for {trading_pair}. Skipping stop-loss and take-profit check.")
        return False

    profit_target = balance * (1 + TAKE_PROFIT_PERCENT / 100)
    loss_limit = balance * (1 - STOP_LOSS_PERCENT / 100)

    if current_price >= profit_target:
        logger.info(f"Take-profit reached for {trading_pair}. Closing all positions.")
        send_telegram_message(f"Take-profit reached at price {current_price} for {trading_pair}. Closing all positions.")
        close_all_positions(trading_pair)
        return True
    elif current_price <= loss_limit:
        logger.info(f"Stop-loss triggered for {trading_pair}. Closing all positions.")
        send_telegram_message(f"Stop-loss triggered at price {current_price} for {trading_pair}. Closing all positions.")
        close_all_positions(trading_pair)
        return True
    return False

# Function to close all open positions
def close_all_positions(trading_pair):
    try:
        open_orders = exchange.fetch_open_orders(trading_pair)
        if not open_orders:
            logger.info(f"No open positions to close for {trading_pair}.")
            return

        for order in open_orders:
            exchange.cancel_order(order['id'], trading_pair)
        logger.info(f"All positions closed for {trading_pair}.")
        send_telegram_message(f"All positions closed for {trading_pair}.")
    except Exception as e:
        logger.error(f"Failed to close all positions for {trading_pair}: {e}")
        send_telegram_message(f"Failed to close all positions for {trading_pair}: {e}")

# Main trading loop
def main():
    while True:
        try:
            for trading_pair in TRADING_PAIRS:
                ticker = exchange.fetch_ticker(trading_pair)
                current_price = Decimal(ticker['last'])

                # Check for stop-loss or take-profit condition
                if check_stop_take_profit(current_price, trading_pair, pair_balance):
                    continue

                # Place grid orders
                orders = place_grid_orders(current_price, trading_pair, pair_balance)
                if not orders:
                    logger.error(f"No grid orders placed for {trading_pair} due to insufficient balance or other issues.")
                    send_telegram_message(f"No grid orders placed for {trading_pair}. Please review settings.")
                    continue

            # Sleep for a while before rechecking the market
            time.sleep(20)
        except Exception as e:
            logger.error(f"Error in main trading loop: {e}")
            send_telegram_message(f"Error in main trading loop: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()
