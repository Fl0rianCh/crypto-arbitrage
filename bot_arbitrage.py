import os
import time
import ccxt
import logging
from decimal import Decimal
from dotenv import load_dotenv
from telegram import Bot
from datetime import datetime

load_dotenv('config.env')

# Configurations
INVESTMENT = Decimal('400')  # EUR initial investment
GRID_LEVELS = 5  # Number of grid levels
GRID_SPACING_PERCENT = Decimal('1.5')  # Grid spacing as a percentage of the price
STOP_LOSS_PERCENT = Decimal('10')  # Stop-loss at 10% below initial investment
TAKE_PROFIT_PERCENT = Decimal('20')  # Take-profit at 15% above initial investment
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

# Performance metrics
successful_trades = 0
failed_trades = 0
total_profit = Decimal('0')
start_time = datetime.now()
open_positions = {}  # Store open positions with their prices

# Function to send Telegram notifications
def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

# Function to send periodic performance report
def send_performance_report(frequency):
    uptime = datetime.now() - start_time
    roi = (total_profit / initial_balance) * 100 if initial_balance != 0 else Decimal('0')
    report = (
        f"Performance Report:\n"
        f"Report Frequency: {frequency // 3600} hours\n"
        f"Uptime: {uptime}\n"
        f"Successful Trades: {successful_trades}\n"
        f"Failed Trades: {failed_trades}\n"
        f"Total Profit: {total_profit:.2f} USDC\n"
        f"ROI: {roi:.2f}%"
    )
    send_telegram_message(report)

# Function to check if there is sufficient balance for an order
def has_sufficient_balance(order):
    balance = exchange.fetch_free_balance()
    symbol = order['symbol'].split('/')[0]  # Example: BTC
    required_balance = order['price'] * order['size'] * (1 + FEE_PERCENT / 100)
    if order['type'] == 'buy':
        if balance['USDC'] < required_balance:
            logger.error(f"Insufficient USDC balance for order: {order}")
            return False
    else:
        if balance[symbol] < order['size']:
            logger.error(f"Insufficient {symbol} balance for order: {order}")
            return False
    return True

# Function to place limit orders at grid levels and execute them
def place_grid_orders(current_price, trading_pair, balance):
    grid_orders = []
    market = exchange.market(trading_pair)
    min_order_size = market['limits']['amount']['min']

    # Calculate the maximum possible order size per grid level
    base_order_size = balance / GRID_LEVELS / current_price

    # Ensure base order size meets the minimum requirement
    if base_order_size < min_order_size:
        logger.error(f"Base order size {base_order_size} is below the minimum required {min_order_size} for {trading_pair}. Adjusting grid levels or balance may be needed.")
        # send_telegram_message(f"Base order size {base_order_size} is below the minimum required {min_order_size} for {trading_pair}. Adjusting grid levels or balance may be needed.")
        return []

    # Adjust the base order size to meet the minimum requirement if necessary
    adjusted_order_size = max(base_order_size, min_order_size)
    total_required_balance = adjusted_order_size * GRID_LEVELS * current_price

    # If the total required balance exceeds the available balance, reduce the number of grid levels
    if total_required_balance > balance:
        logger.warning(f"Total required balance {total_required_balance} exceeds available balance {balance}. Reducing grid levels.")
        # send_telegram_message(f"Total required balance {total_required_balance} exceeds available balance {balance}. Reducing grid levels.")
        max_levels = int(balance / (adjusted_order_size * current_price))
        if max_levels < 1:
            logger.error(f"Insufficient balance to place even a single order for {trading_pair}.")
            send_telegram_message(f"Insufficient balance to place even a single order for {trading_pair}.")
            return []
        adjusted_grid_levels = min(GRID_LEVELS, max_levels)
    else:
        adjusted_grid_levels = GRID_LEVELS

    # Place grid orders
    for i in range(adjusted_grid_levels):
        price = current_price * (1 + GRID_SPACING_PERCENT / 100) ** (i - adjusted_grid_levels // 2)
        order_type = 'buy' if price < current_price else 'sell'

        order = {
            'symbol': trading_pair,
            'price': round(price, 2),
            'size': round(adjusted_order_size, 6),
            'type': order_type
        }

        if has_sufficient_balance(order):
            grid_orders.append(order)
            # Execute the order immediately
            execute_order(order)
        else:
            logger.error(f"Cannot place order due to insufficient balance: {order}")
            # send_telegram_message(f"Cannot place order due to insufficient balance: {order}")

    return grid_orders

# Function to execute a limit order
def execute_order(order):
    global successful_trades, failed_trades, total_profit, open_positions
    try:
        if order['type'] == 'buy':
            response = exchange.create_limit_buy_order(order['symbol'], order['size'], order['price'])
            # Store the open position with the purchase price
            open_positions[order['symbol']] = order['price']
        elif order['type'] == 'sell':
            if order['symbol'] in open_positions:
                buy_price = open_positions.pop(order['symbol'])
                profit = (order['price'] - buy_price) * order['size']
                total_profit += profit
            response = exchange.create_limit_sell_order(order['symbol'], order['size'], order['price'])
        successful_trades += 1
        logger.info(f"{order['type'].capitalize()} order placed: {order}")
    except Exception as e:
        failed_trades += 1
        logger.error(f"Failed to place {order['type']} order: {order}, Error: {e}")

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
        # send_telegram_message(f"Take-profit reached at price {current_price} for {trading_pair}. Closing all positions.")
        close_all_positions(trading_pair)
        return True
    elif current_price <= loss_limit:
        logger.info(f"Stop-loss triggered for {trading_pair}. Closing all positions.")
        # send_telegram_message(f"Stop-loss triggered at price {current_price} for {trading_pair}. Closing all positions.")
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
        # send_telegram_message(f"All positions closed for {trading_pair}.")
    except Exception as e:
        logger.error(f"Failed to close all positions for {trading_pair}: {e}")
        # send_telegram_message(f"Failed to close all positions for {trading_pair}: {e}")

# Main trading loop
def main():
    report_interval = int(os.getenv('REPORT_INTERVAL', 60 * 60 * 1))  # 24 hours
    last_report_time = time.time()

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
            
            # Send performance report periodically
            current_time = time.time()
            if current_time - last_report_time >= report_interval:
                send_performance_report(report_interval)
                last_report_time = current_time
                
            # Sleep for a while before rechecking the market
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error in main trading loop: {e}")
            send_telegram_message(f"Error in main trading loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
