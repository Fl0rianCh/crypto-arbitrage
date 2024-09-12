import ccxt
import requests
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

# Configuration API Binance
binance_api_key = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
binance_secret_key = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration API KuCoin
kucoin_api_key = '66dffc92e72ff9000190a3ae'
kucoin_secret_key = '786adb6d-03a4-464e-8ed3-15330dc48fc5'

# Configuration API Kraken
kraken_api_key = '6P0Taom57ziQjWXRdiq5LZqTZMKRhF6aEMI/Mhz6OWmInmDuvk/eATUr'
kraken_secret_key = 'I+4fZL3GQmApUXivCLaQpmMFjQ6NIvwvjYACnO/vC9KRVrX0Fm2JNnHx93mu8xOas9YJHd3SNkuDkQYYQtF9XQ=='

# Configuration Telegram
telegram_token = '7501427979:AAE-r03vaNZjuATvSL5FUdAHqn2BjwV0Gok'
chat_id = '1887133385'

# Créer une connexion aux exchanges
binance = ccxt.binance({
    'apiKey': binance_api_key,
    'secret': binance_secret_key,
    'enableRateLimit': True
})

kucoin = ccxt.kucoin({
    'apiKey': kucoin_api_key,
    'secret': kucoin_secret_key,
    'password': 'yD13A5fc18102023$',
    'enableRateLimit': True
})

kraken = ccxt.kraken({
    'apiKey': kraken_api_key,
    'secret': kraken_secret_key,
    'enableRateLimit': True
})

# Configuration du bot
min_price_difference = 0.0005  # Seuil minimum de différence de prix en USDT ajusté
trading_fee_binance = 0.00075  # 0,075% de frais sur Binance
trading_fee_kucoin = 0.001  # 0,1% de frais sur KuCoin
trading_fee_kraken = 0.0016  # 0,16% de frais sur Kraken
stop_loss_percentage = 0.005  # Stop-loss à 0,5% sous le prix d'achat

# Logger pour suivre l'activité et éviter la surcharge
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = TimedRotatingFileHandler("bot_log.log", when="midnight", interval=1, backupCount=2)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Fonction pour envoyer un message sur Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logger.error(f"Erreur d'envoi de la notification Telegram : {response.status_code}")
    except Exception as e:
        logger.error(f"Exception lors de l'envoi de la notification Telegram : {e}")

# Calculer les frais de transaction sur Binance, KuCoin et Kraken
def calculate_fees(amount_traded, price, platform):
    total_amount = amount_traded * price
    if platform == 'binance':
        return total_amount * trading_fee_binance
    elif platform == 'kucoin':
        return total_amount * trading_fee_kucoin
    elif platform == 'kraken':
        return total_amount * trading_fee_kraken

# Vérifier si une opportunité d'arbitrage est disponible entre 3 exchanges
def is_arbitrage_opportunity(buy_price, sell_price, buy_platform, sell_platform):
    buy_price_with_fees = buy_price + calculate_fees(1, buy_price, buy_platform)
    sell_price_with_fees = sell_price - calculate_fees(1, sell_price, sell_platform)

    # Ajouter un log pour afficher les prix avec frais
    logger.info(f"Prix achat avec frais : {buy_price_with_fees}, Prix vente avec frais : {sell_price_with_fees}")

    return (sell_price_with_fees - buy_price_with_fees) > min_price_difference

# Calculer les profits
def calculate_profit(buy_price, sell_price, amount_traded, buy_platform, sell_platform):
    buy_cost = buy_price * amount_traded
    sell_income = sell_price * amount_traded
    fees_buy = calculate_fees(amount_traded, buy_price, buy_platform)
    fees_sell = calculate_fees(amount_traded, sell_price, sell_platform)
    profit = (sell_income - fees_sell) - (buy_cost + fees_buy)
    return profit, fees_buy, fees_sell

# Acheter sur KuCoin
def buy_on_kucoin(amount, price):
    try:
        kucoin.create_limit_buy_order('XRP/USDT', amount, price)
        logger.info(f"Achat de {amount} XRP à {price} USDT sur KuCoin")
    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur KuCoin : {e}")

# Vendre sur Binance
def sell_on_binance(amount, price):
    try:
        binance.create_limit_sell_order('XRP/USDT', amount, price)
        logger.info(f"Vente de {amount} XRP à {price} USDT sur Binance")
    except Exception as e:
        logger.error(f"Erreur lors de la vente sur Binance : {e}")

# Acheter sur Kraken
def buy_on_kraken(amount, price):
    try:
        kraken.create_limit_buy_order('XRP/USDT', amount, price)
        logger.info(f"Achat de {amount} XRP à {price} USDT sur Kraken")
    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur Kraken : {e}")

# Vendre sur Kraken
def sell_on_kraken(amount, price):
    try:
        kraken.create_limit_sell_order('XRP/USDT', amount, price)
        logger.info(f"Vente de {amount} XRP à {price} USDT sur Kraken")
    except Exception as e:
        logger.error(f"Erreur lors de la vente sur Kraken : {e}")

# Fonction pour récupérer les soldes sur chaque plateforme
def get_balances():
    binance_balance = binance.fetch_balance()
    kucoin_balance = kucoin.fetch_balance()
    kraken_balance = kraken.fetch_balance()

    logger.info(f"Solde Binance (XRP) : {binance_balance['total'].get('XRP', 0)} XRP")
    logger.info(f"Solde KuCoin (USDT) : {kucoin_balance['total'].get('USDT', 0)} USDT")
    logger.info(f"Solde Kraken (XRP) : {kraken_balance['total'].get('XRP', 0)} XRP")

    return binance_balance, kucoin_balance, kraken_balance

# Fonction pour calculer le montant à investir en fonction des soldes disponibles
def calculate_trade_amount(kucoin_balance, kucoin_price):
    usdt_available_kucoin = kucoin_balance['total'].get('USDT', 0)
    
    # Allouer un pourcentage du solde USDT disponible pour l'achat
    capital_allocation_percentage = 0.5  # Utiliser 50% du capital disponible
    trade_amount = (usdt_available_kucoin * capital_allocation_percentage) / kucoin_price
    
    # Vérifier si le trade_amount est supérieur à un minimum pour éviter les petites transactions
    if trade_amount < 1:  # Par exemple, 1 XRP comme minimum
        logger.info(f"Montant à trader trop faible : {trade_amount} XRP, aucune transaction")
        return 0
    return trade_amount

# Fonction principale d'arbitrage avec réinvestissement automatique
def arbitrage():
    logger.info("Le bot d'arbitrage a démarré !")
    send_telegram_message("Le bot XRP a démarré !")
    
    start_time = time.time()  # Pour la notification périodique
    while True:
        try:
            # Récupérer les prix actuels sur Binance, KuCoin et Kraken
            binance_price = binance.fetch_ticker('XRP/USDT')['last']
            logger.info(f"Prix sur Binance : {binance_price}")
            
            kucoin_price = kucoin.fetch_ticker('XRP/USDT')['last']
            logger.info(f"Prix sur KuCoin : {kucoin_price}")
            
            kraken_price = kraken.fetch_ticker('XRP/USDT')['last']
            logger.info(f"Prix sur Kraken : {kraken_price}")

            # Comparer les opportunités d'arbitrage entre Binance, KuCoin et Kraken
            binance_balance, kucoin_balance, kraken_balance = get_balances()
            amount_to_trade = calculate_trade_amount(kucoin_balance, kucoin_price)

            if amount_to_trade > 0:
                # Arbitrage KuCoin -> Binance
                if is_arbitrage_opportunity(kucoin_price, binance_price, 'kucoin', 'binance'):
                    logger.info("Opportunité d'arbitrage KuCoin -> Binance détectée")
                    buy_on_kucoin(amount_to_trade, kucoin_price)
                    sell_on_binance(amount_to_trade, binance_price)

                # Arbitrage Kraken -> Binance
                elif is_arbitrage_opportunity(kraken_price, binance_price, 'kraken', 'binance'):
                    logger.info("Opportunité d'arbitrage Kraken -> Binance détectée")
                    buy_on_kraken(amount_to_trade, kraken_price)
                    sell_on_binance(amount_to_trade, binance_price)

                # Arbitrage KuCoin -> Kraken
                elif is_arbitrage_opportunity(kucoin_price, kraken_price, 'kucoin', 'kraken'):
                    logger.info("Opportunité d'arbitrage KuCoin -> Kraken détectée")
                    buy_on_kucoin(amount_to_trade, kucoin_price)
                    sell_on_kraken(amount_to_trade, kraken_price)

            # Notification Telegram toutes les 12 heures
            if time.time() - start_time >= 12 * 3600:  # 12 heures écoulées
                send_telegram_message("Le bot XRP fonctionne correctement.")
                start_time = time.time()

            time.sleep(30)  # Pause de 30 secondes

        except Exception as e:
            logger.error(f"Erreur dans le processus d'arbitrage : {e}")

# Lancer le bot d'arbitrage
arbitrage()
