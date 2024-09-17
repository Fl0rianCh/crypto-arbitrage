import ccxt
import requests
import logging
import time
from datetime import datetime
import numpy as np
from logging.handlers import TimedRotatingFileHandler

# Configuration API Binance
binance_api_key = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
binance_secret_key = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration API KuCoin
kucoin_api_key = '66dffc92e72ff9000190a3ae'
kucoin_secret_key = '786adb6d-03a4-464e-8ed3-15330dc48fc5'
kucoin_password = 'yD13A5fc18102023$'

# Configuration API Kraken
kraken_api_key = '6P0Taom57ziQjWXRdiq5LZqTZMKRhF6aEMI/Mhz6OWmInmDuvk/eATUr'
kraken_secret_key = 'I+4fZL3GQmApUXivCLaQpmMFjQ6NIvwvjYACnO/vC9KRVrX0Fm2JNnHx93mu8xOas9YJHd3SNkuDkQYYQtF9XQ=='

# Configuration Telegram
telegram_token = '7501427979:AAE-r03vaNZjuATvSL5FUdAHqn2BjwV0Gok'
chat_id = '1887133385'

# Connexion aux exchanges
binance = ccxt.binance({
    'apiKey': binance_api_key,
    'secret': binance_secret_key,
    'enableRateLimit': True
})

kucoin = ccxt.kucoin({
    'apiKey': kucoin_api_key,
    'secret': kucoin_secret_key,
    'password': kucoin_password,
    'enableRateLimit': True
})

kraken = ccxt.kraken({
    'apiKey': kraken_api_key,
    'secret': kraken_secret_key,
    'enableRateLimit': True
})

# Frais de chaque plateforme
fees = {
    'binance': 0.00075,  # 0.075%
    'kucoin': 0.001,     # 0.1%
    'kraken': 0.0016     # 0.16%
}

# Paires disponibles par plateforme
available_pairs = {
    'binance': ['XRP/USDC'],
    'kucoin': ['XRP/USDC', 'XRP/USDT'],
    'kraken': ['XRP/USDC']
}

# Configuration du logging pour suivre les activités
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = TimedRotatingFileHandler("arbitrage_bot.log", when="midnight", interval=1, backupCount=7)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Fonction pour envoyer une notification Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logger.error(f"Erreur lors de l'envoi de la notification Telegram : {response.status_code}")
        else:
            logger.info(f"Notification Telegram envoyée : {message}")
    except Exception as e:
        logger.error(f"Exception lors de l'envoi de la notification Telegram : {e}")

# Fonction pour calculer les profits en prenant en compte les frais
def calculate_profit(buy_price, sell_price, amount, buy_platform, sell_platform):
    fee_buy = fees[buy_platform] * buy_price * amount
    fee_sell = fees[sell_platform] * sell_price * amount
    profit = (sell_price - buy_price) * amount - (fee_buy + fee_sell)
    return profit, fee_buy, fee_sell

# Fonction pour récupérer les soldes sur chaque plateforme
def get_balances():
    try:
        binance_balance = binance.fetch_balance()
        kucoin_balance = kucoin.fetch_balance()
        kraken_balance = kraken.fetch_balance()

        logger.info(f"Solde Binance: {binance_balance['total']}")
        logger.info(f"Solde KuCoin: {kucoin_balance['total']}")
        logger.info(f"Solde Kraken: {kraken_balance['total']}")

        return binance_balance, kucoin_balance, kraken_balance
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des soldes : {e}")
        send_telegram_message(f"Erreur lors de la récupération des soldes : {e}")
        return None, None, None

# Fonction pour suivre les prix des cryptos sur les 3 plateformes
def get_prices():
    try:
        binance_xrp_usdc = binance.fetch_ticker('XRP/USDC')['last']
        kucoin_xrp_usdc = kucoin.fetch_ticker('XRP/USDC')['last']
        kucoin_xrp_usdt = kucoin.fetch_ticker('XRP/USDT')['last']
        kraken_xrp_usdc = kraken.fetch_ticker('XRP/USDC')['last']

        prices = {
            'binance': {'XRP/USDC': binance_xrp_usdc},
            'kucoin': {'XRP/USDC': kucoin_xrp_usdc, 'XRP/USDT': kucoin_xrp_usdt},
            'kraken': {'XRP/USDC': kraken_xrp_usdc}
        }
        logger.info(f"Prix des cryptos récupérés : {prices}")
        return prices
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des prix : {e}")
        send_telegram_message(f"Erreur lors de la récupération des prix : {e}")
        return None

# Fonction pour détecter une opportunité d'arbitrage
def detect_arbitrage_opportunity(prices):
    try:
        binance_xrp_usdc = prices['binance']['XRP/USDC']
        kucoin_xrp_usdc = prices['kucoin']['XRP/USDC']
        kucoin_xrp_usdt = prices['kucoin']['XRP/USDT']
        kraken_xrp_usdc = prices['kraken']['XRP/USDC']

        # Comparaison entre Binance et KuCoin (USDC)
        if kucoin_xrp_usdc < binance_xrp_usdc:
            logger.info("Opportunité d'arbitrage KuCoin -> Binance (USDC) détectée")
            return 'kucoin', 'binance', 'XRP/USDC', kucoin_xrp_usdc, binance_xrp_usdc

        # Comparaison entre KuCoin (USDT) et Kraken (USDC)
        if kucoin_xrp_usdt < kraken_xrp_usdc:
            logger.info("Opportunité d'arbitrage KuCoin -> Kraken (USDT -> USDC) détectée")
            return 'kucoin', 'kraken', 'XRP/USDT', kucoin_xrp_usdt, kraken_xrp_usdc

        logger.info("Aucune opportunité d'arbitrage détectée")
        return None, None, None, None, None
    except Exception as e:
        logger.error(f"Erreur lors de la détection des opportunités : {e}")
        send_telegram_message(f"Erreur lors de la détection des opportunités : {e}")
        return None, None, None, None, None

# Fonction pour s'assurer que la paire est disponible avant de passer l'ordre
def check_pair_availability(exchange_name, symbol):
    if symbol in available_pairs[exchange_name]:
        return True
    else:
        logger.warning(f"La paire {symbol} n'est pas disponible sur {exchange_name}")
        return False

# Fonction pour acheter sur une plateforme
def place_buy_order(exchange, symbol, amount, price):
    try:
        order = exchange.create_limit_buy_order(symbol, amount, price)
        logger.info(f"Achat passé pour {amount} {symbol} à {price}")
        return order
    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur {exchange}: {e}")
        send_telegram_message(f"Erreur lors de l'achat sur {exchange}: {e}")
        return None

# Fonction pour vendre sur une plateforme
def place_sell_order(exchange, symbol, amount, price):
    try:
        order = exchange.create_limit_sell_order(symbol, amount, price)
        logger.info(f"Vente passée pour {amount} {symbol} à {price}")
        return order
    except Exception as e:
        logger.error(f"Erreur lors de la vente sur {exchange}: {e}")
        send_telegram_message(f"Erreur lors de la vente sur {exchange}: {e}")
        return None

# Fonction pour annuler un ordre après un délai s'il n'est pas exécuté
def monitor_order_and_cancel(exchange, order_id, symbol, max_wait_time=600):  # 10 minutes = 600 sec
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        try:
            order_status = exchange.fetch_order(order_id, symbol)
            if order_status['status'] == 'closed':
                logger.info(f"Ordre {order_id} exécuté avec succès")
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du statut de l'ordre {order_id} : {e}")
            return False

        time.sleep(60)  # Vérification toutes les minutes

    # Si le délai a expiré, annuler l'ordre
    try:
        exchange.cancel_order(order_id, symbol)
        logger.warning(f"Ordre {order_id} annulé après {max_wait_time} secondes sans exécution.")
        return False
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation de l'ordre {order_id} : {e}")
        return False

# Fonction principale du bot d'arbitrage
def arbitrage_bot():
    logger.info("Le bot d'arbitrage a démarré")
    send_telegram_message("Le bot d'arbitrage a démarré")

    while True:
        try:
            # Récupérer les soldes et les prix
            binance_balance, kucoin_balance, kraken_balance = get_balances()
            prices = get_prices()

            if not prices:
                continue

            # Détection des opportunités
            from_exchange, to_exchange, symbol, buy_price, sell_price = detect_arbitrage_opportunity(prices)

            if from_exchange and to_exchange:
                if not check_pair_availability(from_exchange, symbol) or not check_pair_availability(to_exchange, symbol):
                    continue

                # Calcul de la quantité à trader
                amount = min(100, kucoin_balance['total']['XRP'])  # Exemple : utiliser 100 XRP max
                if from_exchange == 'kucoin' and to_exchange == 'binance':
                    order_buy = place_buy_order(kucoin, symbol, amount, buy_price)
                    if order_buy:
                        order_sell = place_sell_order(binance, symbol, amount, sell_price)
                        if order_sell:
                            monitor_order_and_cancel(binance, order_sell['id'], symbol)

                elif from_exchange == 'kucoin' and to_exchange == 'kraken':
                    order_buy = place_buy_order(kucoin, symbol, amount, buy_price)
                    if order_buy:
                        order_sell = place_sell_order(kraken, symbol, amount, sell_price)
                        if order_sell:
                            monitor_order_and_cancel(kraken, order_sell['id'], symbol)

            time.sleep(10)  # Pause avant la prochaine itération
        except Exception as e:
            logger.error(f"Erreur dans le processus d'arbitrage : {e}")
            send_telegram_message(f"Erreur dans le processus d'arbitrage : {e}")
            time.sleep(60)  # Attendre avant de réessayer
