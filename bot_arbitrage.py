import ccxt
import time
import logging
from decimal import Decimal
from telegram import Bot
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
import os

# Charger les variables d'environnement depuis config.env
load_dotenv("config.env")

# Récupérer les variables d'environnement (pour sécuriser les clés API)
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Paramètres du bot
initial_investment = Decimal('200')  # Montant initial en USDC
trade_size_percentage = Decimal('0.10')  # Utilisation de 10% du capital pour chaque trade
min_profit_threshold = Decimal('0.001')  # Profit minimum attendu (0.1%)
spread = Decimal('0.001')  # Spread de 0.1% autour du prix du marché
DEFAULT_FEES = Decimal('0.00075')  # Frais Binance par défaut : 0.075%

# Initialisation du bot Telegram
bot = Bot(token=TELEGRAM_TOKEN)

# Configuration des logs avec rotation
log_file = "market_making_bot.log"
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7)
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
handler.suffix = "%Y-%m-%d"
logging.basicConfig(level=logging.INFO, handlers=[handler])

logging.info("Démarrage du bot de Market-Making avec 200 USDC")

# Connexion à Binance via ccxt
def connect_to_binance():
    binance = ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_SECRET_KEY,
        'enableRateLimit': True,
    })
    binance.load_markets()
    logging.info("Connexion à l'API Binance réussie.")
    return binance

binance = connect_to_binance()

# Fonction pour envoyer des notifications Telegram
def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi d'un message Telegram: {str(e)}")

# Fonction pour récupérer le prix actuel d'une paire
def fetch_ticker_price(symbol):
    try:
        ticker = binance.fetch_ticker(symbol)
        return Decimal(ticker['close'])
    except Exception as e:
        logging.error(f"Erreur lors de la récupération du prix pour {symbol}: {str(e)}")
        return None

# Calculer le montant à investir pour chaque trade (10% du capital total)
def calculate_trade_size(capital):
    return (capital * trade_size_percentage).quantize(Decimal('0.0001'))

# Calculer les ordres limites pour la stratégie de Market-Making
def generate_market_making_orders(symbol, trade_size, spread):
    price = fetch_ticker_price(symbol)
    if price:
        buy_price = (price * (1 - spread)).quantize(Decimal('0.0001'))
        sell_price = (price * (1 + spread)).quantize(Decimal('0.0001'))
        logging.info(f"Ordres générés : Achat à {buy_price}, Vente à {sell_price} pour {symbol}")
        return buy_price, sell_price
    return None, None

# Exécuter un ordre d'achat ou de vente
def place_order(symbol, order_type, price, amount):
    try:
        if order_type == 'buy':
            order = binance.create_limit_buy_order(symbol, amount, price)
        else:
            order = binance.create_limit_sell_order(symbol, amount, price)
        logging.info(f"Ordre {order_type} placé pour {symbol} : {amount} à {price}")
        return order
    except Exception as e:
        logging.error(f"Erreur lors du placement de l'ordre {order_type} pour {symbol}: {str(e)}")
        return None

# Vérifier si l'ordre a été exécuté
def is_order_filled(order):
    try:
        order_status = binance.fetch_order(order['id'], order['symbol'])
        return order_status['status'] == 'closed'
    except Exception as e:
        logging.error(f"Erreur lors de la vérification de l'état de l'ordre : {str(e)}")
        return False

# Annuler les ordres en attente
def cancel_open_orders(symbol):
    try:
        open_orders = binance.fetch_open_orders(symbol)
        for order in open_orders:
            binance.cancel_order(order['id'], symbol)
            logging.info(f"Ordre annulé : {order['id']} pour {symbol}")
    except Exception as e:
        logging.error(f"Erreur lors de l'annulation des ordres pour {symbol}: {str(e)}")

# Stratégie de Market-Making
def market_making_strategy(symbol, capital):
    trade_size = calculate_trade_size(capital)
    buy_price, sell_price = generate_market_making_orders(symbol, trade_size, spread)

    if buy_price and sell_price:
        # Annuler les ordres en attente pour éviter les conflits
        cancel_open_orders(symbol)

        # Placer les ordres d'achat et de vente
        buy_order = place_order(symbol, 'buy', buy_price, trade_size)
        sell_order = place_order(symbol, 'sell', sell_price, trade_size)

        # Vérifier les exécutions
        if buy_order and is_order_filled(buy_order):
            logging.info(f"Ordre d'achat exécuté pour {symbol} à {buy_price}")
            send_telegram_message(f"Achat exécuté pour {symbol} à {buy_price}")

        if sell_order and is_order_filled(sell_order):
            logging.info(f"Ordre de vente exécuté pour {symbol} à {sell_price}")
            send_telegram_message(f"Vente exécutée pour {symbol} à {sell_price}")

# Boucle principale du bot
def run_market_making_bot(symbol='BTC/USDC', initial_capital=initial_investment):
    while True:
        try:
            market_making_strategy(symbol, initial_capital)
            time.sleep(60)  # Pause de 1 minute entre chaque itération
        except Exception as e:
            logging.error(f"Erreur dans la boucle principale : {str(e)}")
            send_telegram_message(f"Erreur dans la boucle principale : {str(e)}")
            time.sleep(10)

# Démarrage du bot
if __name__ == '__main__':
    send_telegram_message("Démarrage du bot de Market-Making avec 200 USDC")
    run_market_making_bot()
