import ccxt 
import requests
import time
import logging
import numpy as np  # Pour calculer la volatilité
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

# Fonction générique pour gérer les reconnections
def reconnect(exchange_name, max_retries=5, delay=10):
    retries = 0
    while retries < max_retries:
        try:
            # Essayer une requête simple pour vérifier la connexion
            if exchange_name == 'binance':
                binance.fetch_time()
            elif exchange_name == 'kucoin':
                kucoin.fetch_time()
            elif exchange_name == 'kraken':
                kraken.fetch_time()
            logger.info(f"Connexion rétablie avec {exchange_name}")
            return True
        except Exception as e:
            retries += 1
            logger.warning(f"Échec de la connexion avec {exchange_name}. Tentative {retries}/{max_retries}. Erreur : {e}")
            time.sleep(delay)  # Attendre avant de réessayer
    logger.error(f"Impossible de rétablir la connexion avec {exchange_name} après {max_retries} tentatives.")
    send_telegram_message(f"Impossible de rétablir la connexion avec {exchange_name} après {max_retries} tentatives.")
    return False

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
min_price_difference = 0.0005  # Seuil minimum de différence de prix en USDC ajusté
trading_fee_binance = 0.00075  # 0,075% de frais sur Binance
trading_fee_kucoin = 0.001  # 0,1% de frais sur KuCoin
trading_fee_kraken = 0.0016  # 0,16% de frais sur Kraken
stop_loss_percentage = 0.005  # Stop-loss à 0,5% sous le prix d'achat

# Répartition idéale en pourcentage
ideal_allocation = {
    'binance': {'XRP': 24.5, 'USDC': 10.5},
    'kraken': {'XRP': 24, 'USDC': 6},
    'kucoin': {'XRP': 14, 'USDC': 21}
}

def convert_usdc_to_usdt_kucoin(amount):
    try:
        order = kucoin.create_market_sell_order('USDC/USDT', amount)
        logger.info(f"Conversion de {amount} USDC à USDT sur KuCoin")
        return order
    except Exception as e:
        logger.error(f"Erreur lors de la conversion USDC -> USDT sur KuCoin : {e}")
        return None

def convert_usdt_to_usdc_kucoin(amount):
    try:
        order = kucoin.create_market_sell_order('USDT/USDC', amount)
        logger.info(f"Conversion de {amount} USDT à USDC sur KuCoin")
        return order
    except Exception as e:
        logger.error(f"Erreur lors de la conversion USDT -> USDC sur KuCoin : {e}")
        return None

# Fonction pour récupérer les soldes sur chaque plateforme
def get_balances():
    retries = 0
    max_retries = 3  # Nombre maximum de tentatives de reconnexion
    delay = 5  # Délai entre chaque tentative

    while retries < max_retries:
        try:
            binance_balance = binance.fetch_balance()
            kucoin_balance = kucoin.fetch_balance()
            kraken_balance = kraken.fetch_balance()

            logger.info(f"Solde Binance (XRP): {binance_balance['total'].get('XRP', 0)} XRP, {binance_balance['total'].get('USDC', 0)} USDC")
            logger.info(f"Solde KuCoin (XRP): {kucoin_balance['total'].get('XRP', 0)} XRP, {kucoin_balance['total'].get('USDC', 0)} USDC")
            logger.info(f"Solde Kraken (XRP): {kraken_balance['total'].get('XRP', 0)} XRP, {kraken_balance['total'].get('USDC', 0)} USDC")

            return binance_balance, kucoin_balance, kraken_balance
        except Exception as e:
            retries += 1
            logger.error(f"Erreur lors de la récupération des soldes (tentative {retries}) : {e}")
            if not reconnect('binance') or not reconnect('kucoin') or not reconnect('kraken'):
                time.sleep(delay)  # Attendre avant la prochaine tentative
            send_telegram_message(f"Erreur lors de la récupération des soldes, tentative {retries} : {e}")

    logger.error(f"Échec de récupération des soldes après {max_retries} tentatives.")
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

# Acheter sur KuCoin
def buy_on_kucoin(amount, price):
    try:
        order = kucoin.create_limit_buy_order('XRP/USDC', amount, price)
        logger.info(f"Achat de {amount} XRP à {price} USDC sur KuCoin")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = kucoin.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP acheté à {price} USDC sur KuCoin")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur KuCoin : {e}")
                if not reconnect('kucoin'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        kucoin.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur KuCoin")

    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur KuCoin : {e}")
        if not reconnect('kucoin'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de l'achat sur KuCoin : {e}")

# Vendre sur KuCoin
def sell_on_kucoin(amount, price):
    try:
        order = kucoin.create_limit_sell_order('XRP/USDC', amount, price)
        logger.info(f"Vente de {amount} XRP à {price} USDC sur KuCoin")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = kucoin.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP vendu à {price} USDC sur KuCoin")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur KuCoin : {e}")
                if not reconnect('kucoin'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        kucoin.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur KuCoin")

    except Exception as e:
        logger.error(f"Erreur lors de la vente sur KuCoin : {e}")
        if not reconnect('kucoin'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de la vente sur KuCoin : {e}")

# Acheter sur Binance
def buy_on_binance(amount, price):
    try:
        order = binance.create_limit_buy_order('XRP/USDC', amount, price)
        logger.info(f"Achat de {amount} XRP à {price} USDC sur Binance")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = binance.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP acheté à {price} USDC sur Binance")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur Binance : {e}")
                if not reconnect('binance'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        binance.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur Binance")

    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur Binance : {e}")
        if not reconnect('binance'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de l'achat sur Binance : {e}")

# Vendre sur Binance
def sell_on_binance(amount, price):
    try:
        order = binance.create_limit_sell_order('XRP/USDC', amount, price)
        logger.info(f"Vente de {amount} XRP à {price} USDC sur Binance")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = binance.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP vendu à {price} USDC sur Binance")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur Binance : {e}")
                if not reconnect('binance'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        binance.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur Binance")

    except Exception as e:
        logger.error(f"Erreur lors de la vente sur Binance : {e}")
        if not reconnect('binance'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de la vente sur Binance : {e}")
        
# Acheter sur Kraken
def buy_on_kraken(amount, price):
    try:
        order = kraken.create_limit_buy_order('XRP/USDC', amount, price)
        logger.info(f"Achat de {amount} XRP à {price} USDC sur Kraken")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = kraken.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP acheté à {price} USDC sur Kraken")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur Kraken : {e}")
                if not reconnect('kraken'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        kraken.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur Kraken")

    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur Kraken : {e}")
        if not reconnect('kraken'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de l'achat sur Kraken : {e}")

# Vendre sur Kraken
def sell_on_kraken(amount, price):
    try:
        order = kraken.create_limit_sell_order('XRP/USDC', amount, price)
        logger.info(f"Vente de {amount} XRP à {price} USDC sur Kraken")
        
        start_time = time.time()
        while time.time() - start_time < 60:
            try:
                order_status = kraken.fetch_order(order['id'])
                if order_status['status'] == 'closed':
                    logger.info(f"Ordre exécuté : {amount} XRP vendu à {price} USDC sur Kraken")
                    return
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du statut de l'ordre sur Kraken : {e}")
                if not reconnect('kraken'):
                    return  # Si la reconnexion échoue, arrêter la fonction
            time.sleep(5)

        kraken.cancel_order(order['id'])
        logger.warning(f"Ordre annulé après 60 secondes sans exécution : {amount} XRP à {price} USDC sur Kraken")

    except Exception as e:
        logger.error(f"Erreur lors de la vente sur Kraken : {e}")
        if not reconnect('kraken'):
            return  # Si la reconnexion échoue, arrêter la fonction
        send_telegram_message(f"Erreur lors de la vente sur Kraken : {e}")

# Fonction pour calculer les frais de transaction sur chaque plateforme
def calculate_fees(amount_traded, price, platform):
    total_amount = amount_traded * price
    if platform == 'binance':
        return total_amount * trading_fee_binance
    elif platform == 'kucoin':
        return total_amount * trading_fee_kucoin
    elif platform == 'kraken':
        return total_amount * trading_fee_kraken
    return 0

# Fonction pour annuler tous les ordres ouverts sur une plateforme donnée
def cancel_open_orders(exchange, platform_name):
    try:
        open_orders = exchange.fetch_open_orders()
        if len(open_orders) > 0:
            logger.info(f"{len(open_orders)} ordres ouverts trouvés sur {platform_name}, annulation en cours.")
            for order in open_orders:
                exchange.cancel_order(order['id'])
                logger.info(f"Ordre {order['id']} annulé sur {platform_name}.")
            send_telegram_message(f"{len(open_orders)} ordres ouverts annulés sur {platform_name}.")
        else:
            logger.info(f"Aucun ordre ouvert sur {platform_name}.")
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation des ordres sur {platform_name} : {e}")
        send_telegram_message(f"Erreur lors de l'annulation des ordres sur {platform_name} : {e}")

# Fonction pour vérifier et annuler les ordres ouverts avant chaque transfert
def check_and_cancel_open_orders():
    try:
        # Annuler les ordres ouverts sur Binance
        cancel_open_orders(binance, 'Binance')

        # Annuler les ordres ouverts sur KuCoin
        cancel_open_orders(kucoin, 'KuCoin')

        # Annuler les ordres ouverts sur Kraken
        cancel_open_orders(kraken, 'Kraken')

        logger.info("Tous les ordres ouverts ont été annulés avec succès.")
        send_telegram_message("Tous les ordres ouverts ont été annulés avec succès.")
    except Exception as e:
        logger.error(f"Erreur lors de la vérification et de l'annulation des ordres : {e}")
        send_telegram_message(f"Erreur lors de la vérification et de l'annulation des ordres : {e}")

# Fonction pour vérifier si une opportunité d'arbitrage est disponible
def is_arbitrage_opportunity(buy_price, sell_price, buy_platform, sell_platform, min_price_difference):
    # Calcul des prix avec les frais inclus
    buy_price_with_fees = buy_price + calculate_fees(1, buy_price, buy_platform)
    sell_price_with_fees = sell_price - calculate_fees(1, sell_price, sell_platform)

    # Ajouter un log pour afficher les prix avec frais
    logger.info(f"Prix achat avec frais ({buy_platform}) : {buy_price_with_fees}, Prix vente avec frais ({sell_platform}) : {sell_price_with_fees}")

    # Vérifier si la différence entre le prix de vente et le prix d'achat dépasse le seuil minimal
    return (sell_price_with_fees - buy_price_with_fees) > min_price_difference

# Fonction pour récupérer la valeur totale du portefeuille (XRP et USDC)
def get_total_portfolio_value(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price):
    total_xrp = binance_balance['total'].get('XRP', 0) + kucoin_balance['total'].get('XRP', 0) + kraken_balance['total'].get('XRP', 0)
    total_USDC = binance_balance['total'].get('USDC', 0) + kucoin_balance['total'].get('USDC', 0) + kraken_balance['total'].get('USDC', 0)

    # Convertir tous les XRP en USDC pour obtenir la valeur totale du portefeuille en USDC
    total_xrp_value_in_USDC = total_xrp * (binance_price + kucoin_price + kraken_price) / 3
    total_portfolio_value = total_xrp_value_in_USDC + total_USDC
    
    return total_portfolio_value

# Fonction pour calculer les écarts et rééquilibrer les portefeuilles
def rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price):
    total_value = get_total_portfolio_value(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

    # Calculer la valeur idéale en XRP et USDC pour chaque plateforme
    ideal_binance_xrp = (ideal_allocation['binance']['XRP'] / 100) * total_value / binance_price
    ideal_binance_USDC = (ideal_allocation['binance']['USDC'] / 100) * total_value
    
    ideal_kraken_xrp = (ideal_allocation['kraken']['XRP'] / 100) * total_value / kraken_price
    ideal_kraken_USDC = (ideal_allocation['kraken']['USDC'] / 100) * total_value
    
    ideal_kucoin_xrp = (ideal_allocation['kucoin']['XRP'] / 100) * total_value / kucoin_price
    ideal_kucoin_USDC = (ideal_allocation['kucoin']['USDC'] / 100) * total_value
    
    # Calculer les différences entre le solde actuel et l'idéal pour chaque plateforme
    delta_binance_xrp = ideal_binance_xrp - binance_balance['total'].get('XRP', 0)
    delta_binance_USDC = ideal_binance_USDC - binance_balance['total'].get('USDC', 0)
    
    delta_kraken_xrp = ideal_kraken_xrp - kraken_balance['total'].get('XRP', 0)
    delta_kraken_USDC = ideal_kraken_USDC - kraken_balance['total'].get('USDC', 0)
    
    delta_kucoin_xrp = ideal_kucoin_xrp - kucoin_balance['total'].get('XRP', 0)
    delta_kucoin_USDC = ideal_kucoin_USDC - kucoin_balance['total'].get('USDC', 0)
    
    # Transferts pour rééquilibrer
    if delta_binance_xrp > 0:
        transfer_xrp('kucoin', 'binance', delta_binance_xrp)
    if delta_binance_USDC > 0:
        transfer_USDC('kucoin', 'binance', delta_binance_USDC)
    
    if delta_kraken_xrp > 0:
        transfer_xrp('kucoin', 'kraken', delta_kraken_xrp)
    if delta_kraken_USDC > 0:
        transfer_USDC('kucoin', 'kraken', delta_kraken_USDC)
    
    if delta_kucoin_xrp > 0:
        transfer_xrp('binance', 'kucoin', delta_kucoin_xrp)
    if delta_kucoin_USDC > 0:
        transfer_USDC('binance', 'kucoin', delta_kucoin_USDC)
    
    logger.info("Rééquilibrage effectué.")
    send_telegram_message("Rééquilibrage des portefeuilles effectué.")

def transfer_xrp(from_platform, to_platform, amount):
    try:
        # Vérifier et annuler les ordres ouverts avant le transfert
        check_and_cancel_open_orders()

        # Ensuite, procéder au transfert
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

def transfer_USDC(from_platform, to_platform, amount):
    try:
        # Vérifier et annuler les ordres ouverts avant le transfert
        check_and_cancel_open_orders()

        # Ensuite, procéder au transfert
        if from_platform == 'binance' and to_platform == 'kucoin':
            binance.withdraw('USDC', amount, kucoin.fetch_deposit_address('USDC')['address'])
        elif from_platform == 'kucoin' and to_platform == 'binance':
            kucoin.withdraw('USDC', amount, binance.fetch_deposit_address('USDC')['address'])
        elif from_platform == 'kucoin' and to_platform == 'kraken':
            kucoin.withdraw('USDC', amount, kraken.fetch_deposit_address('USDC')['address'])
        elif from_platform == 'kraken' and to_platform == 'kucoin':
            kraken.withdraw('USDC', amount, kucoin.fetch_deposit_address('USDC')['address'])
        logger.info(f"Transfert de {amount} USDC de {from_platform} à {to_platform} effectué.")
        send_telegram_message(f"Transfert de {amount} USDC de {from_platform} à {to_platform} effectué.")
    except Exception as e:
        logger.error(f"Erreur lors du transfert de USDC : {e}")
        send_telegram_message(f"Erreur lors du transfert de USDC de {from_platform} à {to_platform} : {e}")

# Fonction pour calculer la volatilité sur l'historique des prix
def calculate_volatility(prices):
    return np.std(prices) / np.mean(prices)

# Fonction pour ajuster dynamiquement le seuil de profit minimal en fonction de la volatilité
def calculate_dynamic_price_difference(volatility, base_min_difference=0.0005):
    return base_min_difference * (1 + volatility)

# Fonction pour calculer le montant à investir en fonction des soldes disponibles
def calculate_trade_amount(balance, price, platform):
    available_balance = balance['total'].get('USDC' if platform == 'kucoin' else 'XRP', 0)
    
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
# Remplacer les paires utilisées par chaque exchange
binance_price = binance.fetch_ticker('XRP/USDC')['last']  # Binance : XRP/USDC
kraken_price = kraken.fetch_ticker('XRP/USDT')['last']  # Kraken : XRP/USDT
kucoin_price_usdc = kucoin.fetch_ticker('XRP/USDC')['last']  # KuCoin : XRP/USDC
kucoin_price_usdt = kucoin.fetch_ticker('XRP/USDT')['last']  # KuCoin : XRP/USDT

            # Si tous les prix sont récupérés correctement, les ajouter à l'historique
            price_history.append((binance_price + kucoin_price + kraken_price) / 3)
            if len(price_history) > 20:
                price_history.pop(0)  # Limiter l'historique à 20 points

            volatility = calculate_volatility(price_history)  # Calculer la volatilité
            min_price_difference_dynamic = calculate_dynamic_price_difference(volatility, base_min_difference=0.0005)

            binance_balance, kucoin_balance, kraken_balance = get_balances()

            # Vérifier si une conversion USDC -> USDT ou USDT -> USDC est nécessaire sur KuCoin avant l'arbitrage
if binance_balance['total']['USDC'] < amount_to_trade_binance and kucoin_balance['total']['USDT'] >= amount_to_trade_binance:
    logger.info("Conversion nécessaire: USDT vers USDC sur KuCoin")
    convert_usdt_to_usdc_kucoin(amount_to_trade_binance)

if kraken_balance['total']['USDT'] < amount_to_trade_kraken and kucoin_balance['total']['USDC'] >= amount_to_trade_kraken:
    logger.info("Conversion nécessaire: USDC vers USDT sur KuCoin")
    convert_usdc_to_usdt_kucoin(amount_to_trade_kraken)

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
                logger.info(f"Profit net : {profit} USDC, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage KuCoin -> Binance: Profit de {profit:.2f} USDC")

                # Rééquilibrer après chaque arbitrage
                rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

            # Arbitrage Kraken -> Binance
            elif amount_to_trade_kraken > 0 and is_arbitrage_opportunity(kraken_price, binance_price, 'kraken', 'binance', min_price_difference_dynamic):
                logger.info("Opportunité d'arbitrage Kraken -> Binance détectée")
                buy_on_kraken(amount_to_trade_kraken, kraken_price)
                sell_on_binance(amount_to_trade_kraken, binance_price)

                # Calcul des profits
                profit, fees_buy, fees_sell = calculate_profit(kraken_price, binance_price, amount_to_trade_kraken, 'kraken', 'binance')
                logger.info(f"Profit net : {profit} USDC, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage Kraken -> Binance: Profit de {profit:.2f} USDC")

                # Rééquilibrer après chaque arbitrage
                rebalance_portfolios(binance_balance, kucoin_balance, kraken_balance, binance_price, kucoin_price, kraken_price)

            # Arbitrage KuCoin -> Kraken
            elif amount_to_trade_kucoin > 0 and is_arbitrage_opportunity(kucoin_price, kraken_price, 'kucoin', 'kraken', min_price_difference_dynamic):
                logger.info("Opportunité d'arbitrage KuCoin -> Kraken détectée")
                buy_on_kucoin(amount_to_trade_kucoin, kucoin_price)
                sell_on_kraken(amount_to_trade_kucoin, kraken_price)

                # Calcul des profits
                profit, fees_buy, fees_sell = calculate_profit(kucoin_price, kraken_price, amount_to_trade_kucoin, 'kucoin', 'kraken')
                logger.info(f"Profit net : {profit} USDC, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                send_telegram_message(f"Arbitrage KuCoin -> Kraken: Profit de {profit:.2f} USDC")

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
