import ccxt
import requests
import time
import logging
from logging.handlers import TimedRotatingFileHandler

# Configuration API Binance
binance_api_key = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
binance_secret_key = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration API KuCoin
kucoin_api_key = '66db75000a48170001a2a302'
kucoin_secret_key = '958f9568-57c4-4804-8a43-dacfdcf07591'

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
    'password': '131093',
    'enableRateLimit': True
})

# Configuration du bot
min_price_difference = 10  # Seuil minimum de différence de prix en USDT
trading_fee = 0.001  # 0,1% de frais de transaction
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

# Calculer les frais de transaction
def calculate_fees(price):
    return price * trading_fee

# Vérifier si une opportunité d'arbitrage est disponible
def is_arbitrage_opportunity(buy_price, sell_price):
    buy_price_with_fees = buy_price + calculate_fees(buy_price)
    sell_price_with_fees = sell_price - calculate_fees(sell_price)
    return (sell_price_with_fees - buy_price_with_fees) > min_price_difference

# Calculer les profits
def calculate_profit(buy_price, sell_price, amount_traded):
    buy_cost = buy_price * amount_traded
    sell_income = sell_price * amount_traded
    fees_buy = calculate_fees(buy_cost)
    fees_sell = calculate_fees(sell_income)
    profit = (sell_income - fees_sell) - (buy_cost + fees_buy)
    return profit, fees_buy, fees_sell

# Acheter sur KuCoin
def buy_on_kucoin(amount, price):
    try:
        kucoin.create_limit_buy_order('BTC/USDT', amount, price)
        logger.info(f"Achat de {amount} BTC à {price} USDT sur KuCoin")
        send_telegram_message(f"Achat exécuté sur KuCoin : {amount} BTC à {price} USDT")
    except Exception as e:
        logger.error(f"Erreur lors de l'achat sur KuCoin : {e}")

# Vendre sur Binance
def sell_on_binance(amount, price):
    try:
        binance.create_limit_sell_order('BTC/USDT', amount, price)
        logger.info(f"Vente de {amount} BTC à {price} USDT sur Binance")
        send_telegram_message(f"Vente exécutée sur Binance : {amount} BTC à {price} USDT")
    except Exception as e:
        logger.error(f"Erreur lors de la vente sur Binance : {e}")

# Fonction pour calculer le montant à investir en fonction des soldes disponibles
def calculate_trade_amount(kucoin_balance, kucoin_price):
    # Utiliser l'USDT disponible sur KuCoin pour calculer combien de BTC acheter
    usdt_available_kucoin = kucoin_balance['total']['USDT']
    
    # Allouer un pourcentage du solde USDT disponible pour l'achat
    capital_allocation_percentage = 0.1  # Utiliser 10% du capital disponible, ajustable
    trade_amount = (usdt_available_kucoin * capital_allocation_percentage) / kucoin_price
    
    # Vérifier si le trade_amount est supérieur à un minimum pour éviter les petites transactions
    if trade_amount < 0.001:  # Par exemple, 0.001 BTC comme minimum
        logger.info(f"Montant à trader trop faible : {trade_amount} BTC, aucune transaction")
        return 0
    return trade_amount

# Récupérer les soldes sur chaque plateforme
def get_balances():
    binance_balance = binance.fetch_balance()
    kucoin_balance = kucoin.fetch_balance()
    return binance_balance, kucoin_balance

# Fonction principale d'arbitrage avec réinvestissement automatique
def arbitrage():
    # Envoyer un message au démarrage du bot
    send_telegram_message("Le bot d'arbitrage est maintenant en ligne et prêt à analyser les marchés.")
    logger.info("Le bot d'arbitrage a démarré !")
    
    while True:
        try:
            # Récupérer les prix actuels sur Binance et KuCoin avec gestion des erreurs
            try:
                binance_price = binance.fetch_ticker('BTC/USDT')['last']
                logger.info(f"Prix sur Binance : {binance_price}")
            except Exception as e:
                logger.error(f"Erreur lors de la récupération du prix sur Binance : {e}")
                send_telegram_message(f"Erreur lors de la récupération du prix sur Binance : {e}")
                continue  # Continue le cycle si une erreur se produit

            kucoin_price = kucoin.fetch_ticker('BTC/USDT')['last']
            logger.info(f"Prix sur KuCoin : {kucoin_price}")

            # Récupérer les soldes actuels sur les deux plateformes
            binance_balance, kucoin_balance = get_balances()

            # Calculer le montant à investir basé sur les profits accumulés
            amount_to_trade = calculate_trade_amount(kucoin_balance, kucoin_price)

            # Si le montant est suffisant, effectuer l'arbitrage
            if amount_to_trade > 0:
                if is_arbitrage_opportunity(kucoin_price, binance_price):
                    logger.info("Opportunité d'arbitrage détectée")
                    # Exécuter l'achat et la vente
                    buy_on_kucoin(amount_to_trade, kucoin_price)
                    sell_on_binance(amount_to_trade, binance_price)

                    # Calculer et envoyer le profit réalisé
                    profit, fees_buy, fees_sell = calculate_profit(kucoin_price, binance_price, amount_to_trade)
                    logger.info(f"Profit net : {profit} USDT, Frais d'achat : {fees_buy}, Frais de vente : {fees_sell}")
                    send_telegram_message(f"Arbitrage effectué !\nProfit net : {profit} USDT\nFrais d'achat : {fees_buy} USDT\nFrais de vente : {fees_sell} USDT")
                else:
                    logger.info("Pas d'opportunité d'arbitrage détectée")

            # Afficher les soldes après l'exécution des ordres
            send_telegram_message(f"Soldes après arbitrage : Binance = {binance_balance['total']['BTC']} BTC, KuCoin = {kucoin_balance['total']['USDT']} USDT")

            # Attendre avant de relancer le cycle
            time.sleep(60)  # Pause de 60 secondes

        except Exception as e:
            logger.error(f"Erreur dans le processus d'arbitrage : {e}")

# Lancer le bot d'arbitrage
arbitrage()
