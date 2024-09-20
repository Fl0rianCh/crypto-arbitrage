import ccxt
import time
import logging
from decimal import Decimal, ROUND_DOWN
from telegram import Bot
import datetime
import logging
from logging.handlers import TimedRotatingFileHandler

# Configuration des clés API directement dans le script
BINANCE_API_KEY = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
BINANCE_SECRET_KEY = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'
KUCOIN_API_KEY = '66dffc92e72ff9000190a3ae'
KUCOIN_SECRET_KEY = '786adb6d-03a4-464e-8ed3-15330dc48fc5'
KUCOIN_PASSWORD = 'yD13A5fc18102023$'
KRAKEN_API_KEY = '6P0Taom57ziQjWXRdiq5LZqTZMKRhF6aEMI/Mhz6OWmInmDuvk/eATUr'
KRAKEN_SECRET_KEY = 'I+4fZL3GQmApUXivCLaQpmMFjQ6NIvwvjYACnO/vC9KRVrX0Fm2JNnHx93mu8xOas9YJHd3SNkuDkQYYQtF9XQ=='

# Configuration de l'API Telegram pour les notifications
TELEGRAM_TOKEN = '7501427979:AAE-r03vaNZjuATvSL5FUdAHqn2BjwV0Gok'
TELEGRAM_CHAT_ID = '1887133385'
bot = Bot(token=TELEGRAM_TOKEN)

# Fonction d'envoi de notifications sur Telegram
def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"Error sending Telegram message: {str(e)}")

# Configuration de la journalisation avec rotation des logs
log_file = "arbitrage.log"
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=1)
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
handler.suffix = "%Y-%m-%d"  # Ajouter la date dans le nom du fichier log

logging.basicConfig(level=logging.INFO, handlers=[handler])

# Exemple de message dans les logs
logging.info("Logging system initialized with daily rotation")

# Frais par plateforme (éditables)
fees = {
    'binance': 0.001,  # 0.1%
    'kucoin': 0.001,
    'kraken': 0.0026,  # 0.26%
}

# Création des instances CCXT pour chaque exchange
def connect_to_exchanges():
    try:
        binance = ccxt.binance({
            'apiKey': BINANCE_API_KEY,
            'secret': BINANCE_SECRET_KEY,
        })
        kucoin = ccxt.kucoin({
            'apiKey': KUCOIN_API_KEY,
            'secret': KUCOIN_SECRET_KEY,
            'password': KUCOIN_PASSWORD,
        })
        kraken = ccxt.kraken({
            'apiKey': KRAKEN_API_KEY,
            'secret': KRAKEN_SECRET_KEY,
        })
        
        # Charger les marchés pour CCXT (Binance, KuCoin, Kraken)
        binance.load_markets()
        kucoin.load_markets()
        kraken.load_markets()
 
        # Envoyer un message Telegram lorsque le bot démarre avec succès
        send_telegram_message("Arbitrage bot started successfully and connected to Binance, KuCoin, and Kraken.")
        
        logging.info("Connected to Binance, KuCoin, and Kraken successfully")
        return binance, kucoin, kraken
    except Exception as e:
        logging.error(f"Error connecting to exchanges: {str(e)}")
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Error connecting to exchanges: {str(e)}")
        except Exception as telegram_error:
            logging.error(f"Error sending Telegram message: {str(telegram_error)}")
        return None, None, None

binance, kucoin, kraken = connect_to_exchanges()
        
def retry_request(func, *args, max_retries=5, delay=2, **kwargs):
    retries = 0
    while retries < max_retries:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}. Retrying {retries + 1}/{max_retries}...")
            time.sleep(delay)
            retries += 1
    logging.error(f"Max retries exceeded for {func.__name__}")
    return None

# Récupération des frais via l'API CCXT
def get_trading_fees(exchange, pair):
    try:
        # Récupérer les frais de trading pour la paire spécifiée
        fees = exchange.fetch_trading_fees()
        if pair in fees:
            return fees[pair]
        else:
            # Si la paire n'a pas de frais spécifiques, retourner les frais généraux par défaut
            logging.warning(f"Fees for {pair} not found, using default fees for {exchange.id}")
            return {
                'maker': Decimal(fees.get('maker', 0.001)),  # Par défaut 0.1% maker
                'taker': Decimal(fees.get('taker', 0.001))   # Par défaut 0.1% taker
            }
    except Exception as e:
        logging.error(f"Error fetching trading fees for {pair} on {exchange.id}: {str(e)}")
        # Retourner les frais par défaut en cas d'erreur
        return {
            'maker': Decimal('0.001'),  # Frais par défaut 0.1% maker
            'taker': Decimal('0.001')   # Frais par défaut 0.1% taker
        }
        
# Fonction d'attente de remplissage d'ordre avec timeout
def wait_for_order(exchange, order_id, pair, timeout=30):
    start_time = datetime.datetime.now()
    while True:
        order_status = retry_request(exchange.fetch_order, order_id, pair)
        if order_status:
            status = order_status['status']
            # Gérer les statuts possibles de l'ordre
            if status in ['closed', 'filled', 'partially_closed', 'partially_filled']:
                return order_status
            elif status in ['canceled', 'rejected']:
                logging.error(f"Order {order_id} on {pair} was {status}.")
                send_telegram_message(f"Order {order_id} on {pair} was {status}.")
                return None
        # Vérifier si le timeout est atteint
        if (datetime.datetime.now() - start_time).seconds > timeout:
            logging.error(f"Order {order_id} on {pair} not filled within {timeout} seconds.")
            send_telegram_message(f"Order {order_id} on {pair} not filled within {timeout} seconds.")
            return None
        time.sleep(1)

# Fonction pour rechercher des opportunités d'arbitrage triangulaire
def triangular_arbitrage(exchange, pair1, pair2, pair3):
    try:
        # Montant à investir pour le premier ordre (ici, 10 USDC)
        amount_to_invest = Decimal('10')  # Utiliser Decimal pour précision
        
        # Récupérer les prix actuels pour les trois paires
        ticker1 = exchange.fetch_ticker(pair1)
        ticker2 = exchange.fetch_ticker(pair2)
        ticker3 = exchange.fetch_ticker(pair3)

        if ticker1 is None or ticker2 is None or ticker3 is None:
            return

        # Calculer les prix de conversion
        price1 = Decimal(str(ticker1['ask']))  # Prix d'achat BTC/USDC
        price2 = Decimal(str(ticker2['ask']))  # Prix d'achat ETH/USDC
        price3 = Decimal(str(ticker3['bid']))  # Prix de vente LTC/USDC
        
        # Logguer chaque analyse du marché
        logging.info(f"Market Analysis: {pair1} price1: {price1}, {pair2} price2: {price2}, {pair3} price3: {price3}")
        
        # Vérifier si le volume est suffisant pour chaque paire avant d'exécuter l'arbitrage
        if ticker1['quoteVolume'] < float(amount_to_invest) or ticker2['quoteVolume'] < float(amount_to_invest) or ticker3['quoteVolume'] < float(amount_to_invest):
            logging.info(f"Insufficient volume for arbitrage: {pair1}, {pair2}, {pair3}")
            return  # Si le volume est insuffisant, arrêter ici     
        
        # Récupérer les frais spécifiques pour chaque paire
        fees_pair1 = get_trading_fees(exchange, pair1)
        fees_pair2 = get_trading_fees(exchange, pair2)
        fees_pair3 = get_trading_fees(exchange, pair3)
        
        fee1 = Decimal(fees_pair1['taker']) if fees_pair1 else Decimal('0.001')  # Frais pour l'ordre d'achat
        fee2 = Decimal(fees_pair2['taker']) if fees_pair2 else Decimal('0.001')  # Frais pour l'ordre d'achat
        fee3 = Decimal(fees_pair3['taker']) if fees_pair3 else Decimal('0.001')  # Frais pour l'ordre d'achat
        
        # Calcul de l'opportunité d'arbitrage
        arbitrage_profit = (price1 * price2 * price3).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)
        
        if arbitrage_profit > Decimal(1):
            logging.info(f"Arbitrage Opportunity Found: {pair1} -> {pair2} -> {pair3} with profit {arbitrage_profit}")
            send_telegram_message(f"Arbitrage Opportunity: {pair1} -> {pair2} -> {pair3} | Profit: {arbitrage_profit}")
            
            # Simuler ou exécuter l'ordre avec 10 USDC
            execute_trade(exchange, pair1, pair2, pair3, amount_to_invest, tick_size1=0.000001, tick_size2=0.000001, tick_size3=0.000001)
        else:
            logging.info(f"No arbitrage opportunity for {pair1} -> {pair2} -> {pair3}")
    except Exception as e:
        logging.error(f"Error in triangular_arbitrage: {str(e)}")
        send_telegram_message(f"Error in triangular_arbitrage: {str(e)}")

# Fonction pour exécuter le trade en tenant compte des frais et des tailles de ticks
def execute_trade(exchange, pair1, pair2, pair3, amount_to_invest, tick_size1, tick_size2, tick_size3):
    try:
        # Étape 1: Récupérer les frais pour chaque paire
        fees_pair1 = get_trading_fees(exchange, pair1)
        fees_pair2 = get_trading_fees(exchange, pair2)
        fees_pair3 = get_trading_fees(exchange, pair3)
        
        # Assumer que les frais taker sont appliqués (dans le cas d'un ordre au marché)
        fee1 = fees_pair1['taker'] if fees_pair1 else 0.001  # Appliquer un frais par défaut si non récupérable
        fee2 = fees_pair2['taker'] if fees_pair2 else 0.001
        fee3 = fees_pair3['taker'] if fees_pair3 else 0.001

        # Étape 2: Calculer la quantité à acheter pour la première paire, ajustée par les frais
        ticker1 = exchange.fetch_ticker(pair1)
        price1 = ticker1['ask']  # Prix d'achat
        amount_base_currency = (amount_to_invest / price1) * (1 - Decimal(fee1))
        amount_base_currency = amount_base_currency.quantize(Decimal(str(tick_size1)), rounding=ROUND_DOWN)

        # Passer le premier ordre (achat)
        logging.info(f'Placing first order: {amount_base_currency} {pair1}')
        order1 = exchange.create_order(pair1, 'market', 'buy', float(amount_base_currency))
        order_id1 = order1['id']
        
        # Vérifier que l'ordre est rempli
        while True:
            order_status = exchange.fetch_order(order_id1, pair1)
            if order_status['status'] == 'closed':
                amount_base_currency = Decimal(order_status['filled'])
                break
            time.sleep(1)

        # Étape 3: Calculer la quantité pour la deuxième paire
        ticker2 = exchange.fetch_ticker(pair2)
        price2 = ticker2['bid']
        amount_second_currency = amount_base_currency * price2 * (1 - Decimal(fee2))
        amount_second_currency = amount_second_currency.quantize(Decimal(str(tick_size2)), rounding=ROUND_DOWN)

        # Passer le deuxième ordre (vente)
        logging.info(f'Placing second order: {amount_second_currency} {pair2}')
        order2 = exchange.create_order(pair2, 'market', 'sell', float(amount_second_currency))
        order_id2 = order2['id']
        
        # Vérifier que l'ordre est rempli
        while True:
            order_status = exchange.fetch_order(order_id2, pair2)
            if order_status['status'] == 'closed':
                amount_second_currency = Decimal(order_status['cost'])
                break
            time.sleep(1)

        # Étape 4: Calculer la quantité pour la troisième paire
        ticker3 = exchange.fetch_ticker(pair3)
        price3 = ticker3['bid']
        amount_third_currency = amount_second_currency * price3 * (1 - Decimal(fee3))
        amount_third_currency = amount_third_currency.quantize(Decimal(str(tick_size3)), rounding=ROUND_DOWN)

        # Passer le troisième ordre (vente)
        logging.info(f'Placing third order: {amount_third_currency} {pair3}')
        order3 = exchange.create_order(pair3, 'market', 'sell', float(amount_third_currency))
        order_id3 = order3['id']

        # Vérifier que l'ordre est rempli
        while True:
            order_status = exchange.fetch_order(order_id3, pair3)
            if order_status['status'] == 'closed':
                logging.info(f'Triangular arbitrage completed: {pair1} -> {pair2} -> {pair3}')
                break
            time.sleep(1)

        # Message Telegram avec les détails de l'arbitrage terminé et les profits
        arbitrage_profit = (price1 * price2 * price3).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN)  # Recalcule ou récupère le profit si nécessaire
        send_telegram_message(f"Executed triangular trade: {pair1}, {pair2}, {pair3} with {amount_to_invest} USDC and profit: {arbitrage_profit}")
        
        logging.info(f"Executed triangular trade: {pair1}, {pair2}, {pair3} with {amount_to_invest} USDC")
        
        logging.info(f"Fees for {pair1}: Maker: {fees_pair1['maker']}, Taker: {fees_pair1['taker']}")
        logging.info(f"Fees for {pair2}: Maker: {fees_pair2['maker']}, Taker: {fees_pair2['taker']}")
        logging.info(f"Fees for {pair3}: Maker: {fees_pair3['maker']}, Taker: {fees_pair3['taker']}")
    
    except Exception as e:
        logging.error(f"Error executing trade: {str(e)}")
        send_telegram_message(f"Error executing trade: {str(e)}")

# Liste des paires à surveiller pour l'arbitrage triangulaire
pairs_to_watch = [
    ('BTC/USDC', 'ETH/USDC', 'LTC/USDC'),  # Exemple de trio
]

# Fonction pour surveiller les opportunités d'arbitrage triangulaire
def monitor_arbitrage_opportunities():
    while True:
        try:
            for pair1, pair2, pair3 in pairs_to_watch:
                # Vérifier si chaque exchange est connecté avant d'exécuter l'arbitrage
                if binance is not None:
                    try:
                        triangular_arbitrage(binance, pair1, pair2, pair3)
                    except Exception as e:
                        logging.error(f"Error in triangular_arbitrage for Binance: {str(e)}")
                
                if kucoin is not None:
                    try:
                        triangular_arbitrage(kucoin, pair1, pair2, pair3)
                    except Exception as e:
                        logging.error(f"Error in triangular_arbitrage for KuCoin: {str(e)}")
                
                if kraken is not None:
                    try:
                        triangular_arbitrage(kraken, pair1, pair2, pair3)
                    except Exception as e:
                        logging.error(f"Error in triangular_arbitrage for Kraken: {str(e)}")
            
            time.sleep(10)  # Pause de 10 secondes entre chaque vérification
        except Exception as e:
            logging.error(f"Error in monitor_arbitrage_opportunities: {str(e)}")
            send_telegram_message(f"Error in monitor_arbitrage_opportunities: {str(e)}")
            time.sleep(60)  # Attendre 60 secondes avant de réessayer en cas d'erreur

# Lancer la surveillance des opportunités d'arbitrage
monitor_arbitrage_opportunities()
