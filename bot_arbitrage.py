import ccxt 
import requests
import time
import logging
import numpy as np  # Pour calculer la volatilité
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

# Répartition idéale en pourcentage
ideal_allocation = {
    'binance': {'XRP': 24.5, 'USDT': 10.5},
    'kraken': {'XRP': 24, 'USDT': 6},
    'kucoin': {'XRP': 14, 'USDT': 21}
}

# Fonction pour récupérer les soldes sur chaque plateforme
def get_balances():
    try:
        binance_balance = binance.fetch_balance()
        kucoin_balance = kucoin.fetch_balance()
        kraken_balance = kraken.fetch_balance()

        logger.info(f"Solde Binance (XRP): {binance_balance['total'].get('XRP', 0)} XRP, {binance_balance['total'].get('USDT', 0)} USDT")
        logger.info(f"Solde KuCoin (XRP): {kucoin_balance['total'].get('XRP', 0)} XRP, {kucoin_balance['total'].get('USDT', 0)} USDT")
        logger.info(f"Solde Kraken (XRP): {kraken_balance['total'].get('XRP', 0)} XRP, {kraken_balance['total'].get('USDT', 0)} USDT")

        return binance_balance, kucoin_balance, kraken_balance
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des soldes : {e}")
        send_telegram_message(f"Erreur lors de la récupération des soldes : {e}")
        return None, None, None

# Logger pour suivre l'activité et éviter la surcharge
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = TimedRotatingFileHandler("bot_log.log", when="midnight", interval=1, backupCount=2)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Suivi des prix pour la volatilité
price_history = []

# Fonction pour envoyer un message sur Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logger.error(f"Erreur d'envoi de la notification Telegram : {response.status_code}")
        else:
            logger.info(f"Notification Telegram envoyée : {message}")
    except Exception as e:
        logger.error(f"Exception lors de l'envoi de la notification Telegram : {e}")

# Fonction pour récupérer la valeur totale du portefeuille (XRP et USDT)
def get_total_portfolio_value(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price):
    total_xrp = binance_balance['total'].get('XRP', 0) + kucoin_balance['total'].get('XRP', 0) + kraken_balance['total'].get('XRP', 0)
    total_usdt = binance_balance['total'].get('USDT', 0) + kucoin_balance['total'].get('USDT', 0) + kraken_balance['total'].get('USDT', 0)

    # Convertir tous les XRP en USDT pour obtenir la valeur totale du portefeuille en USDT
    total_xrp_value_in_usdt = total_xrp * (binance_price + kucoin_price + kraken_price) / 3
    total_portfolio_value = total_xrp_value_in_usdt + total_usdt
    
    return total_portfolio_value

# Fonction pour calculer les écarts et rééquilibrer les portefeuilles
def rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price):
    total_value = get_total_portfolio_value(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

    # Calculer la valeur idéale en XRP et USDT pour chaque plateforme
    ideal_binance_xrp = (ideal_allocation['binance']['XRP'] / 100) * total_value / binance_price
    ideal_binance_usdt = (ideal_allocation['binance']['USDT'] / 100) * total_value
    
    ideal_kraken_xrp = (ideal_allocation['kraken']['XRP'] / 100) * total_value / kraken_price
    ideal_kraken_usdt = (ideal_allocation['kraken']['USDT'] / 100) * total_value
    
    ideal_kucoin_xrp = (ideal_allocation['kucoin']['XRP'] / 100) * total_value / kucoin_price
    ideal_kucoin_usdt = (ideal_allocation['kucoin']['USDT'] / 100) * total_value
    
    # Calculer les différences entre le solde actuel et l'idéal pour chaque plateforme
    delta_binance_xrp = ideal_binance_xrp - binance_balance['total'].get('XRP', 0)
    delta_binance_usdt = ideal_binance_usdt - binance_balance['total'].get('USDT', 0)
    
    delta_kraken_xrp = ideal_kraken_xrp - kraken_balance['total'].get('XRP', 0)
    delta_kraken_usdt = ideal_kraken_usdt - kraken_balance['total'].get('USDT', 0)
    
    delta_kucoin_xrp = ideal_kucoin_xrp - kucoin_balance['total'].get('XRP', 0)
    delta_kucoin_usdt = ideal_kucoin_usdt - kucoin_balance['total'].get('USDT', 0)
    
    # Transferts pour rééquilibrer
    if delta_binance_xrp > 0:
        transfer_xrp('kucoin', 'binance', delta_binance_xrp)
    if delta_binance_usdt > 0:
        transfer_usdt('kucoin', 'binance', delta_binance_usdt)
    
    if delta_kraken_xrp > 0:
        transfer_xrp('kucoin', 'kraken', delta_kraken_xrp)
    if delta_kraken_usdt > 0:
        transfer_usdt('kucoin', 'kraken', delta_kraken_usdt)
    
    if delta_kucoin_xrp > 0:
        transfer_xrp('binance', 'kucoin', delta_kucoin_xrp)
    if delta_kucoin_usdt > 0:
        transfer_usdt('binance', 'kucoin', delta_kucoin_usdt)
    
    logger.info("Rééquilibrage effectué.")
    send_telegram_message("Rééquilibrage des portefeuilles effectué.")

# Fonction pour transférer des XRP entre plateformes
def transfer_xrp(from_platform, to_platform, amount):
    try:
        if from_platform == 'binance' and to_platform == 'kucoin':
            binance.withdraw('XRP', amount, kucoin.fetch_deposit_address('XRP')['address'])
        elif from_platform == 'kucoin' and to_platform == 'binance':
            kucoin.withdraw('XRP', amount, binance.fetch_deposit_address('XRP')['address'])
        elif from_platform == 'kucoin' and to_platform == 'kraken':
            kucoin.withdraw('XRP', amount, kraken.fetch_deposit_address('XRP')['address'])
        elif from_platform == 'kraken' and to_platform == 'kucoin':
            kraken.withdraw('XRP', amount, kucoin.fetch_deposit_address('XRP')['address'])
        logger.info(f"Transfert de {amount} XRP de {from_platform} à {to_platform} effectué.")
        send_telegram_message(f"Transfert de {amount} XRP de {from_platform} à {to_platform} effectué.")
    except Exception as e:
        logger.error(f"Erreur lors du transfert de XRP : {e}")
        send_telegram_message(f"Erreur lors du transfert de XRP de {from_platform} à {to_platform} : {e}")

# Fonction pour transférer des USDT entre plateformes
def transfer_usdt(from_platform, to_platform, amount):
    try:
        if from_platform == 'binance' and to_platform == 'kucoin':
            binance.withdraw('USDT', amount, kucoin.fetch_deposit_address('USDT')['address'])
        elif from_platform == 'kucoin' and to_platform == 'binance':
            kucoin.withdraw('USDT', amount, binance.fetch_deposit_address('USDT')['address'])
        elif from_platform == 'kucoin' and to_platform == 'kraken':
            kucoin.withdraw('USDT', amount, kraken.fetch_deposit_address('USDT')['address'])
        elif from_platform == 'kraken' and to_platform == 'kucoin':
            kraken.withdraw('USDT', amount, kucoin.fetch_deposit_address('USDT')['address'])
        logger.info(f"Transfert de {amount} USDT de {from_platform} à {to_platform} effectué.")
        send_telegram_message(f"Transfert de {amount} USDT de {from_platform} à {to_platform} effectué.")
    except Exception as e:
        logger.error(f"Erreur lors du transfert de USDT : {e}")
        send_telegram_message(f"Erreur lors du transfert de USDT de {from_platform} à {to_platform} : {e}")

# Fonction pour calculer la volatilité sur l'historique des prix
def calculate_volatility(prices):
    return np.std(prices) / np.mean(prices)

# Fonction pour ajuster dynamiquement le seuil de profit minimal en fonction de la volatilité
def calculate_dynamic_price_difference(volatility, base_min_difference=0.0005):
    return base_min_difference * (1 + volatility)

# Fonction pour calculer le montant à investir en fonction des soldes disponibles
def calculate_trade_amount(balance, price, platform):
    available_balance = balance['total'].get('USDT' if platform == 'kucoin' else 'XRP', 0)
    
    # Allouer un pourcentage du solde disponible pour l'achat
    capital_allocation_percentage = 0.5  # Utiliser 50% du capital disponible
    trade_amount = (available_balance * capital_allocation_percentage) / price if platform == 'kucoin' else available_balance * capital_allocation_percentage
    
    if trade_amount <= 0:
        logger.info(f"Montant à trader trop faible : {trade_amount} {platform}, aucune transaction.")
        return 0
    return trade_amount

# Fonction principale d'arbitrage avec réinvestissement automatique et rééquilibrage
def arbitrage():
    logger.info("Le bot d'arbitrage a démarré !")
    send_telegram_message("Le bot XRP a démarré !")
    
    start_time = time.time()  # Pour la notification périodique
    while True:
        try:
            # Récupérer les prix actuels sur Binance, KuCoin et Kraken
            binance_price = binance.fetch_ticker('XRP/USDT')['last']
            kucoin_price = kucoin.fetch_ticker('XRP/USDT')['last']
            kraken_price = kraken.fetch_ticker('XRP/USDT')['last']
            
            price_history.append((binance_price + kucoin_price + kraken_price) / 3)  # Ajouter les prix dans l'historique
            if len(price_history) > 20:
                price_history.pop(0)  # Limiter l'historique à 20 points

            volatility = calculate_volatility(price_history)  # Calculer la volatilité

            min_price_difference_dynamic = calculate_dynamic_price_difference(volatility, base_min_difference=0.0005)

            binance_balance, kucoin_balance, kraken_balance = get_balances()

            # Calculer le montant à trader en utilisant les soldes disponibles
            amount_to_trade_kucoin = calculate_trade_amount(kucoin_balance, kucoin_price, 'kucoin')
            amount_to_trade_binance = calculate_trade_amount(binance_balance, binance_price, 'binance')
            amount_to_trade_kraken = calculate_trade_amount(kraken_balance, kraken_price, 'kraken')

            # Vérification des montants minimums et arbitrage KuCoin -> Binance
            if amount_to_trade_kucoin > 0 and is_arbitrage_opportunity(kucoin_price, binance_price, 'kucoin', 'binance', min_price_difference_dynamic):
                logger.info("Opportunité d'arbitrage KuCoin -> Binance détectée")
                buy_on_kucoin(amount_to_trade_kucoin, kucoin_price)
                sell_on_binance(amount_to_trade_kucoin, binance_price)

                # Calcul des profits
                profit, fees_buy, fees_sell = calculate_profit(kucoin_price, binance_price, amount_to_trade_kucoin, 'kucoin', 'binance')
                logger.info(f"Profit net : {profit} USDT, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage KuCoin -> Binance: Profit de {profit:.2f} USDT")

                # Rééquilibrer après chaque arbitrage
                rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

            # Arbitrage Kraken -> Binance
            elif amount_to_trade_kraken > 0 and is_arbitrage_opportunity(kraken_price, binance_price, 'kraken', 'binance', min_price_difference_dynamic):
                logger.info("Opportunité d'arbitrage Kraken -> Binance détectée")
                buy_on_kraken(amount_to_trade_kraken, kraken_price)
                sell_on_binance(amount_to_trade_kraken, binance_price)

                # Calcul des profits
                profit, fees_buy, fees_sell = calculate_profit(kraken_price, binance_price, amount_to_trade_kraken, 'kraken', 'binance')
                logger.info(f"Profit net : {profit} USDT, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage Kraken -> Binance: Profit de {profit:.2f} USDT")

                # Rééquilibrer après chaque arbitrage
                rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

            # Arbitrage KuCoin -> Kraken
            elif amount_to_trade_kucoin > 0 and is_arbitrage_opportunity(kucoin_price, kraken_price, 'kucoin', 'kraken', min_price_difference_dynamic):
                logger.info("Opportunité d'arbitrage KuCoin -> Kraken détectée")
                buy_on_kucoin(amount_to_trade_kucoin, kucoin_price)
                sell_on_kraken(amount_to_trade_kucoin, kraken_price)

                # Calcul des profits
                profit, fees_buy, fees_sell = calculate_profit(kucoin_price, kraken_price, amount_to_trade_kucoin, 'kucoin', 'kraken')
                logger.info(f"Profit net : {profit} USDT, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage KuCoin -> Kraken: Profit de {profit:.2f} USDT")

                # Rééquilibrer après chaque arbitrage
                rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

            # Notification Telegram toutes les 12 heures
            if time.time() - start_time >= 12 * 3600:  # 12 heures écoulées
                send_telegram_message("Le bot XRP fonctionne correctement.")
                start_time = time.time()

            time.sleep(10)  # Ajuster le temps de pause (en secondes)

        except Exception as e:
            logger.error(f"Erreur dans le processus d'arbitrage : {e}")
            send_telegram_message(f"Erreur dans le processus d'arbitrage : {e}")

# Lancer le bot d'arbitrage
arbitrage()
