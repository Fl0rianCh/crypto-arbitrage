import ccxt
import time
import logging
from decimal import Decimal
from telegram import Bot
from logging.handlers import TimedRotatingFileHandler
import math  # Import nécessaire pour la fonction check_if_float_zero
import signal
import sys

# Configuration des clés API Binance
BINANCE_API_KEY = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
BINANCE_SECRET_KEY = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration de l'API Telegram pour les notifications
TELEGRAM_TOKEN = '7501427979:AAE-r03vaNZjuATvSL5FUdAHqn2BjwV0Gok'
TELEGRAM_CHAT_ID = '1887133385'
bot = Bot(token=TELEGRAM_TOKEN)

# Paramètres dynamiques
initial_investment = Decimal('40')  # Montant investi
transaction_brokerage = Decimal('0.075')  # Frais sur Binance 0.075%
min_profit_threshold = initial_investment * Decimal('0.005')  # 0,5% de l'investissement initial
min_profit = initial_investment * Decimal('0.005')  # 0,5% de l'investissement initial

DEFAULT_FEES = {
    'binance': Decimal('0.00075')  # Frais fixes par défaut : 0,075%
}

# Fonction d'envoi de notifications sur Telegram
def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        logging.error(f"Erreur lors de l'envoi d'un message Telegram: {str(e)}")

def send_telegram_message_if_critical(message, critical=False):
    if critical:
        send_telegram_message(message)

# Fonction pour vérifier si une valeur flottante est proche de zéro
def check_if_float_zero(value):
    return math.isclose(value, 0.0, abs_tol=1e-3)

# Configuration de la journalisation avec rotation des logs
log_file = "arbitrage.log"
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7)
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
handler.suffix = "%Y-%m-%d"
logging.basicConfig(level=logging.INFO, handlers=[handler])

logging.info("Système de journalisation initialisé avec rotation quotidienne")

# Connexion à l'API Binance via ccxt
def connect_to_binance_with_retry(retries=5, delay=5):
    attempt = 0
    while attempt < retries:
        try:
            binance = ccxt.binance({
                'apiKey': BINANCE_API_KEY,
                'secret': BINANCE_SECRET_KEY,
                'enableRateLimit': True
            })
            # Test d'une requête simple pour s'assurer que la connexion est établie
            binance.load_markets()
            logging.info("Connexion à l'API Binance réussie.")
            return binance
        except Exception as e:
            attempt += 1
            logging.error(f"Erreur de connexion à l'API Binance (Tentative {attempt}/{retries}): {str(e)}")
            send_telegram_message(f"Erreur de connexion à l'API Binance, tentative {attempt}/{retries}.")
            if attempt < retries:
                logging.info(f"Nouvelle tentative dans {delay} secondes.")
                time.sleep(delay)
            else:
                logging.error("Toutes les tentatives de connexion à l'API Binance ont échoué.")
                send_telegram_message_if_critical("Impossible de se connecter à l'API Binance après plusieurs tentatives. Bot arrêté.", critical=True)
                return None

binance = connect_to_binance_with_retry()

def ensure_binance_connection():
    global binance
    if binance is None:
        logging.info("Tentative de reconnexion à l'API Binance.")
        binance = connect_to_binance_with_retry()
    return binance

# Fonction pour envoyer un message Telegram lors de l'arrêt du bot
def send_shutdown_message(signum, frame):
    send_telegram_message("Bot arrêté (Signal reçu : {}).".format(signal.Signals(signum).name))
    logging.info(f"Bot arrêté suite à la réception du signal {signal.Signals(signum).name}.")
    sys.exit(0)

# Fonction pour récupérer le prix actuel d'une paire de trading
def fetch_current_ticker_price(ticker):
    binance = ensure_binance_connection()  # Vérifier et reconnecter si nécessaire
    if binance:
        try:
            current_ticker_details = binance.fetch_ticker(ticker)
            ticker_price = current_ticker_details['close'] if current_ticker_details is not None else None
            return ticker_price
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des prix pour {ticker}: {str(e)}")
            return None
    else:
        logging.error(f"Impossible de se connecter à Binance pour récupérer les prix de {ticker}.")
        return None

# Fonction pour récupérer les frais de trading réels via l'API Binance
def get_binance_fees():
    try:
        # Récupérer les frais de trading via l'API Binance
        fees_info = binance.fetch_trading_fees()
        
        # Vérifier si les frais pour une paire spécifique sont disponibles
        if 'ETH/USDC' in fees_info:
            return {
                'binance': Decimal(fees_info['ETH/USDC']['maker'])  # Frais réels récupérés pour ETH/USDC
            }
        else:
            logging.error("Frais pour ETH/USDC non disponibles via l'API, utilisation des frais par défaut.")
            return DEFAULT_FEES  # Retour aux frais fixes par défaut
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des frais de Binance : {str(e)}")
        return DEFAULT_FEES  # Utiliser les frais fixes par défaut en cas d'échec

fees = get_binance_fees()  # Récupérer les frais réels ou appliquer des frais fixes

def check_market_status():
    binance = ensure_binance_connection()  # Vérifier la connexion
    if binance:
        try:
            status = binance.fetch_status()  # Récupérer l'état global du marché
            if status['status'] == 'ok':
                logging.info("Le marché Binance est ouvert et opérationnel.")
                return True
            else:
                logging.warning(f"Le marché est fermé : {status['status']}")
                send_telegram_message("Le marché Binance est actuellement fermé.")
                return False
        except Exception as e:
            logging.error(f"Erreur lors de la vérification de l'état du marché: {str(e)}")
            send_telegram_message(f"Erreur lors de la vérification de l'état du marché: {str(e)}")
            return False
    else:
        return False

def check_market_status_for_pair(pair):
    binance = ensure_binance_connection()  # Vérifier la connexion
    if binance:
        try:
            market = binance.market(pair)
            if market['active']:
                logging.info(f"Le marché pour {pair} est ouvert.")
                return True
            else:
                logging.warning(f"Le marché pour {pair} est fermé.")
                send_telegram_message(f"Le marché pour {pair} est actuellement fermé.")
                return False
        except Exception as e:
            logging.error(f"Erreur lors de la vérification du marché pour {pair}: {str(e)}")
            send_telegram_message(f"Erreur lors de la vérification du marché pour {pair}: {str(e)}")
            return False
    else:
        return False

def generate_valid_pair(crypto):
    btc_pair = f'{crypto}/BTC'
    eth_pair = f'{crypto}/ETH'

    # Éviter de générer des paires identiques comme ETH/ETH
    if crypto == 'BTC':
        return eth_pair  # Utiliser ETH si la crypto est BTC
    elif crypto == 'ETH':
        return btc_pair  # Utiliser BTC si la crypto est ETH
    else:
        # Vérifier si les paires existent sur Binance
        btc_price = fetch_current_ticker_price(btc_pair)
        eth_price = fetch_current_ticker_price(eth_pair)
        
        if btc_price:
            return btc_pair
        elif eth_price:
            return eth_pair
        else:
            logging.error(f"Aucune paire BTC ou ETH disponible pour {crypto}")
            return None

def get_min_order_size(symbol):
    binance = ensure_binance_connection()
    if binance:
        try:
            market = binance.market(symbol)
            return market['limits']['amount']['min']  # Taille minimale d'ordre pour la paire
        except Exception as e:
            logging.error(f"Erreur lors de la récupération de la taille minimale d'ordre pour {symbol}: {str(e)}")
            return None
    else:
        logging.error(f"Impossible de se connecter à Binance pour récupérer les informations sur {symbol}.")
        return None
    
# Simuler Achat-Vente-Achat
def simulate_buy_sell_buy(pair):
    try:
        crypto = pair.split('/')[0]  # Extraire la crypto (par exemple, ETH)
        valid_pair = generate_valid_pair(crypto)  # Générer une paire valide (éviter ETH/ETH)

        if valid_pair:
            intermediate_price = fetch_current_ticker_price(valid_pair)
        else:
            logging.error(f"Aucune paire valide disponible pour {pair}")
            return None

        # Récupérer le prix de la paire USDC/Crypto (ex: ADA/USDC, BNB/USDC)
        ticker_price_1 = fetch_current_ticker_price(pair)
        crypto_btc_pair = pair.split('/')[0] + '/BTC'  
        crypto_eth_pair = pair.split('/')[0] + '/ETH'  

        # Vérifier si les paires BTC et ETH sont disponibles
        crypto_btc_price = fetch_current_ticker_price(crypto_btc_pair)
        crypto_eth_price = fetch_current_ticker_price(crypto_eth_pair)

        # Choisir la deuxième crypto en fonction de la disponibilité
        if crypto_btc_price:
            intermediate_pair = 'BTC'
            intermediate_price = crypto_btc_price
            final_usdc_price = fetch_current_ticker_price('BTC/USDC')
        elif crypto_eth_price:
            intermediate_pair = 'ETH'
            intermediate_price = crypto_eth_price
            final_usdc_price = fetch_current_ticker_price('ETH/USDC')
        else:
            logging.error(f"Aucune paire BTC ou ETH disponible pour {pair}")
            return None

        # 1. Acheter la crypto avec 40 USDC
        crypto_amount = initial_investment / Decimal(ticker_price_1)

        # 2. Vendre la crypto contre BTC ou ETH
        intermediate_amount = crypto_amount * Decimal(intermediate_price) * (1 - fees['binance'])

        # 3. Vendre BTC/ETH contre USDC
        final_usdc_amount = intermediate_amount * Decimal(final_usdc_price) * (1 - fees['binance'])

        # Vérification du montant final en USDC
        if final_usdc_amount < 0.01 or final_usdc_amount > initial_investment * 100:
            logging.error(f"Montant final en USDC non réaliste : {final_usdc_amount}")
            return None

        logging.info(f"Simulation Achat-Vente-Achat pour {pair} via {intermediate_pair} : Montant final en USDC : {final_usdc_amount}")
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Vente-Achat pour {pair}: {str(e)}")
        return None

# Simuler Achat-Achat-Vente
def simulate_buy_buy_sell(pair):
    try:
        ticker_price_1 = fetch_current_ticker_price(pair)
        crypto_btc_pair = pair.split('/')[0] + '/BTC'  
        crypto_eth_pair = pair.split('/')[0] + '/ETH'  

        # Vérifier si les paires BTC et ETH sont disponibles
        crypto_btc_price = fetch_current_ticker_price(crypto_btc_pair)
        crypto_eth_price = fetch_current_ticker_price(crypto_eth_pair)

        # Choisir la deuxième crypto
        if crypto_btc_price:
            intermediate_pair = 'BTC'
            intermediate_price = crypto_btc_price
            final_usdc_price = fetch_current_ticker_price('BTC/USDC')
        elif crypto_eth_price:
            intermediate_pair = 'ETH'
            intermediate_price = crypto_eth_price
            final_usdc_price = fetch_current_ticker_price('ETH/USDC')
        else:
            logging.error(f"Aucune paire BTC ou ETH disponible pour {pair}")
            return None

        # 1. Acheter la crypto avec 40 USDC
        crypto_amount = initial_investment / Decimal(ticker_price_1)

        # 2. Vendre la crypto contre BTC ou ETH
        intermediate_amount = crypto_amount * Decimal(intermediate_price) * (1 - fees['binance'])

        # 3. Vendre BTC/ETH contre USDC
        final_usdc_amount = intermediate_amount * Decimal(final_usdc_price) * (1 - fees['binance'])

        # Vérification du montant final en USDC
        if final_usdc_amount < 0.01 or final_usdc_amount > initial_investment * 100:
            logging.error(f"Montant final en USDC non réaliste : {final_usdc_amount}")
            return None

        logging.info(f"Simulation Achat-Achat-Vente pour {pair} via {intermediate_pair} : Montant final en USDC : {final_usdc_amount}")
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Achat-Vente pour {pair}: {str(e)}")
        return None

# Simuler Achat-Vente-Vente
def simulate_buy_sell_sell(pair):
    try:
        crypto = pair.split('/')[0]  # Extraire la crypto (par exemple, ETH)
        valid_pair = generate_valid_pair(crypto)  # Générer une paire valide (éviter ETH/ETH)

        if valid_pair:
            intermediate_price = fetch_current_ticker_price(valid_pair)
        else:
            logging.error(f"Aucune paire valide disponible pour {pair}")
            return None

        # Récupérer le prix de la paire USDC/Crypto (ex: PEPE/USDC, BNB/USDC)
        ticker_price_1 = fetch_current_ticker_price(pair)
        crypto_btc_pair = pair.split('/')[0] + '/BTC'  
        crypto_eth_pair = pair.split('/')[0] + '/ETH'  

        # Vérifier si les paires BTC et ETH sont disponibles
        crypto_btc_price = fetch_current_ticker_price(crypto_btc_pair)
        crypto_eth_price = fetch_current_ticker_price(crypto_eth_pair)

        # Choisir la deuxième crypto en fonction de la disponibilité
        if crypto_btc_price:
            intermediate_pair = 'BTC'
            intermediate_price = crypto_btc_price
            final_usdc_price = fetch_current_ticker_price('BTC/USDC')
        elif crypto_eth_price:
            intermediate_pair = 'ETH'
            intermediate_price = crypto_eth_price
            final_usdc_price = fetch_current_ticker_price('ETH/USDC')
        else:
            logging.error(f"Aucune paire BTC ou ETH disponible pour {pair}")
            return None

        # 1. Acheter la crypto avec 40 USDC
        crypto_amount = initial_investment / Decimal(ticker_price_1)

        # 2. Vendre la crypto contre BTC ou ETH
        intermediate_amount = crypto_amount * Decimal(intermediate_price) * (1 - fees['binance'])

        # 3. Vendre BTC/ETH contre USDC
        final_usdc_amount = intermediate_amount * Decimal(final_usdc_price) * (1 - fees['binance'])

        # Vérification du montant final en USDC
        if final_usdc_amount < 0.01 or final_usdc_amount > initial_investment * 100:
            logging.error(f"Montant final en USDC non réaliste : {final_usdc_amount}")
            return None

        logging.info(f"Simulation Achat-Vente-Vente pour {pair} via {intermediate_pair} : Montant final en USDC : {final_usdc_amount}")
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Vente-Vente pour {pair}: {str(e)}")
        return None

# Fonction pour exécuter les ordres d'achat et vente
def execute_order(symbol, side, amount):
    binance = ensure_binance_connection()  # Vérifier et reconnecter si nécessaire
    if binance:
        try:
            # Récupérer la taille minimale d'ordre pour cette paire
            min_order_size = get_min_order_size(symbol)
            if min_order_size is None or amount < min_order_size:
                logging.error(f"Montant {amount} pour {symbol} inférieur à la taille minimale {min_order_size}.")
                send_telegram_message(f"Erreur : montant {amount} pour {symbol} inférieur à la taille minimale de {min_order_size}.")
                return None

            # Exécuter l'ordre en fonction de l'action (achat ou vente)
            if side == 'buy':
                logging.info(f"Tentative d'achat de {amount} {symbol}")
                order = binance.create_market_buy_order(symbol, amount)
            else:
                logging.info(f"Tentative de vente de {amount} {symbol}")
                order = binance.create_market_sell_order(symbol, amount)
            
            # Vérifier si l'ordre est rempli
            if check_order_filled(order):
                logging.info(f"Ordre {side} exécuté avec succès pour {symbol}: {amount}")
                send_telegram_message(f"Succès de l'ordre {side} pour {symbol}: {amount} {symbol} exécutés.")
            else:
                logging.warning(f"L'ordre {side} pour {symbol} n'a pas été totalement rempli.")
                send_telegram_message(f"L'ordre {side} pour {symbol} n'a pas été totalement rempli.")
            
            return order  # Retourner l'ordre exécuté
        except Exception as e:
            # Log d'erreur et notification en cas de problème lors de l'exécution de l'ordre
            logging.error(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            send_telegram_message(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            return None
    else:
        # Si la connexion à Binance échoue, on log et on envoie une notification Telegram
        logging.error(f"Impossible de se connecter à Binance pour exécuter un ordre sur {symbol}.")
        send_telegram_message(f"Erreur de connexion : Impossible de se connecter à Binance pour exécuter un ordre sur {symbol}.")
        return None
        
def execute_order_with_retry(symbol, side, amount, retries=3):
    attempt = 0
    while attempt < retries:
        order = execute_order(symbol, side, amount)  # Appel correct
        if check_order_filled(order):
            return order
        attempt += 1
        time.sleep(0.1)  # Attendre 100ms avant de réessayer
    logging.error(f"Erreur : L'ordre {side} pour {symbol} n'a pas été rempli après {retries} tentatives.")
    send_telegram_message_if_critical(f"Échec de l'ordre {side} pour {symbol} après {retries} tentatives. Bot arrêté.", critical=True)
    return None

# Fonction pour vérifier si les ordres sont remplis
def check_order_filled(order):
    return order and order['status'] == 'closed'

# Fonction pour exécuter les trois ordres en simultané et vérifier qu'ils sont remplis
def execute_arbitrage_orders(pair, strategy):
    try:
        # Vérifier l'état du marché avant chaque ordre
        if not check_market_status_for_pair(pair):
            logging.warning(f"Le marché pour {pair} est fermé.")
            return None
 
        # Récupérer les prix de la paire USDC/Crypto
        crypto_usdc_price = fetch_current_ticker_price(pair)
        crypto_amount = initial_investment / Decimal(crypto_usdc_price)

        # Vérifier si les paires intermédiaires BTC ou ETH sont disponibles
        crypto_btc_pair = pair.split('/')[0] + '/BTC'
        crypto_eth_pair = pair.split('/')[0] + '/ETH'

        crypto_btc_price = fetch_current_ticker_price(crypto_btc_pair)
        crypto_eth_price = fetch_current_ticker_price(crypto_eth_pair)

        # Choisir entre BTC ou ETH comme crypto intermédiaire
        if crypto_btc_price:
            intermediate_pair = 'BTC'
            intermediate_price = crypto_btc_price
            final_usdc_price = fetch_current_ticker_price('BTC/USDC')
        elif crypto_eth_price:
            intermediate_pair = 'ETH'
            intermediate_price = crypto_eth_price
            final_usdc_price = fetch_current_ticker_price('ETH/USDC')
        else:
            logging.error(f"Aucune paire BTC ou ETH disponible pour {pair}")
            return None

        # Gérer les stratégies ici
        if strategy == 'buy_sell_buy':
            # Acheter crypto avec USDC
            if not check_market_status_for_pair(pair):  # Vérification
                return None
            order1 = execute_order_with_retry(pair, 'buy', crypto_amount)
            if not check_order_filled(order1):
                return None

            # Vendre crypto pour BTC ou ETH
            if not check_market_status_for_pair(f'{pair.split("/")[0]}/{intermediate_pair}'):  # Vérification
                return None
            order2 = execute_order_with_retry(f'{pair.split("/")[0]}/{intermediate_pair}', 'sell', crypto_amount)
            if not check_order_filled(order2):
                return None

            intermediate_amount = crypto_amount * Decimal(intermediate_price)

            # Vendre BTC/ETH pour USDC
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order3 = execute_order_with_retry(f'{intermediate_pair}/USDC', 'sell', intermediate_amount)
            if not check_order_filled(order3):
                return None


        elif strategy == 'buy_buy_sell':
            # Acheter crypto avec USDC
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order1 = execute_order_with_retry(pair, 'buy', crypto_amount)
            if not check_order_filled(order1):
                return None

            # Acheter BTC ou ETH avec la crypto
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order2 = execute_order_with_retry(f'{pair.split("/")[0]}/{intermediate_pair}', 'buy', crypto_amount)
            if not check_order_filled(order2):
                return None

            intermediate_amount = crypto_amount * Decimal(intermediate_price)

            # Vendre BTC/ETH pour USDC
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order3 = execute_order_with_retry(f'{intermediate_pair}/USDC', 'sell', intermediate_amount)
            if not check_order_filled(order3):
                return None

        elif strategy == 'sell_sell_buy':
            # Vendre crypto contre USDC
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order1 = execute_order_with_retry(pair, 'sell', crypto_amount)
            if not check_order_filled(order1):
                return None

            # Vendre BTC ou ETH contre une autre crypto
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order2 = execute_order_with_retry(f'{pair.split("/")[0]}/{intermediate_pair}', 'sell', crypto_amount)
            if not check_order_filled(order2):
                return None

            intermediate_amount = crypto_amount * Decimal(intermediate_price)

            # Acheter crypto contre USDC
            if not check_market_status_for_pair(f'{intermediate_pair}/USDC'):  # Vérification
                return None
            order3 = execute_order_with_retry(f'{intermediate_pair}/USDC', 'buy', intermediate_amount)
            if not check_order_filled(order3):
                return None

        # Calculer le montant final en USDC après les transactions
        final_usdc_amount = intermediate_amount * Decimal(final_usdc_price)
        logging.info(f"Ordres d'arbitrage exécutés avec succès pour {pair} via {intermediate_pair}. Montant final en USDC : {final_usdc_amount}")
        return final_usdc_amount

    except Exception as e:
        logging.error(f"Erreur lors de l'exécution des ordres d'arbitrage pour {pair} et la stratégie {strategy}: {str(e)}")
        send_telegram_message(f"Erreur lors de l'exécution des ordres d'arbitrage pour {pair} et la stratégie {strategy}: {str(e)}")
        return None

# Calcul du profit net en utilisant les frais récupérés ou par défaut
def check_profit_loss(total_price_after_sell, initial_investment, fees, min_profit):
    apprx_brokerage = fees['binance'] * initial_investment * 3  # Frais sur 3 transactions
    min_profitable_price = initial_investment + apprx_brokerage + min_profit
    profit_loss = round(total_price_after_sell - min_profitable_price, 3)
    return profit_loss
    
# Simuler Achat-Achat-Vente
def check_buy_buy_sell():
    final_usdc_amount = execute_arbitrage_orders()  # Exécuter les ordres
    return final_usdc_amount

# Simuler Achat-Vente-Vente
def check_buy_sell_sell():
    final_usdc_amount = execute_arbitrage_orders()  # Exécuter les ordres
    return final_usdc_amount

# Fonction pour détecter une opportunité d'arbitrage triangulaire
def find_arbitrage_opportunity():
    try:
        # Récupérer les prix des paires pour les différentes cryptomonnaies
        usdc_usdt_price = fetch_current_ticker_price('USDC/USDT')
        btc_usdc_price = fetch_current_ticker_price('BTC/USDC')
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        sol_usdc_price = fetch_current_ticker_price('SOL/USDC')
        arb_usdc_price = fetch_current_ticker_price('ARB/USDC')
        matic_usdc_price = fetch_current_ticker_price('MATIC/USDC')
        bnb_usdc_price = fetch_current_ticker_price('BNB/USDC')
        xrp_usdc_price = fetch_current_ticker_price('XRP/USDC')
        doge_usdc_price = fetch_current_ticker_price('DOGE/USDC')
        ada_usdc_price = fetch_current_ticker_price('ADA/USDC')

        # Vérifier que tous les prix sont bien récupérés
        if None in [usdc_usdt_price, btc_usdc_price, eth_usdc_price, sol_usdc_price, 
                    arb_usdc_price, matic_usdc_price, bnb_usdc_price, xrp_usdc_price, 
                    doge_usdc_price, ada_usdc_price]:
            logging.error("Erreur dans la récupération des prix, impossible de calculer l'arbitrage.")
            return False

        # Prendre en compte l'investissement initial de 40 USDC
        investment = initial_investment  # 40 USDC dans ton cas

        # Prendre en compte les frais sur les trois transactions
        total_fees = fees['binance'] * 3  # Frais sur 3 transactions

        # Calcul du profit net pour chaque paire, en incluant les frais et l'investissement
        net_profits = {}
        
        net_profits['ETH'] = ((investment / Decimal(eth_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['SOL'] = ((investment / Decimal(sol_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['ARB'] = ((investment / Decimal(arb_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['MATIC'] = ((investment / Decimal(matic_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['BNB'] = ((investment / Decimal(bnb_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['XRP'] = ((investment / Decimal(xrp_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['DOGE'] = ((investment / Decimal(doge_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['ADA'] = ((investment / Decimal(ada_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment

        # Trouver la paire la plus rentable
        best_pair = max(net_profits, key=net_profits.get)
        best_profit = net_profits[best_pair]

        # Comparaison avec le min_profit attendu
        if best_profit > min_profit:
            logging.info(f"Arbitrage trouvé avec la paire {best_pair}/USDC ! Profit potentiel après frais : {best_profit} USDC")
            send_telegram_message(f"Arbitrage trouvé avec la paire {best_pair}/USDC ! Profit potentiel : {best_profit} USDC")
            return True
        else:
            logging.info(f"Pas d'opportunité rentable. Meilleur profit potentiel ({best_pair}/USDC) : {best_profit} USDC")
            return False
    except Exception as e:
        logging.error(f"Erreur lors du calcul de l'arbitrage: {str(e)}")
        send_telegram_message(f"Erreur lors du calcul de l'arbitrage: {str(e)}")
        return False

# Fonction pour exécuter les ordres d'achat et vente avec logs et notifications Telegram
def execute_order(symbol, side, amount):
    """
    Exécute un ordre d'achat ou de vente sur Binance, en envoyant des logs et des notifications Telegram.
    
    :param symbol: La paire de trading (par ex. 'ETH/USDC')
    :param side: 'buy' pour achat, 'sell' pour vente
    :param amount: Montant de la crypto à acheter ou vendre
    :return: Détails de l'ordre exécuté ou None en cas d'erreur
    """
    binance = ensure_binance_connection()  # Vérifier et reconnecter si nécessaire
    if binance:
        try:
            # Exécuter l'ordre en fonction de l'action (achat ou vente)
            if side == 'buy':
                logging.info(f"Tentative d'achat de {amount} {symbol}")
                order = binance.create_market_buy_order(symbol, amount)
            else:
                logging.info(f"Tentative de vente de {amount} {symbol}")
                order = binance.create_market_sell_order(symbol, amount)
            
            # Vérifier si l'ordre est rempli
            if check_order_filled(order):
                logging.info(f"Ordre {side} exécuté avec succès pour {symbol}: {amount}")
                send_telegram_message(f"Succès de l'ordre {side} pour {symbol}: {amount} {symbol} exécutés.")
            else:
                logging.warning(f"L'ordre {side} pour {symbol} n'a pas été totalement rempli.")
                send_telegram_message(f"L'ordre {side} pour {symbol} n'a pas été totalement rempli.")
            
            return order  # Retourner l'ordre exécuté
        except Exception as e:
            # Log d'erreur et notification en cas de problème lors de l'exécution de l'ordre
            logging.error(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            send_telegram_message(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            return None
    else:
        # Si la connexion à Binance échoue, on log et on envoie une notification Telegram
        logging.error(f"Impossible de se connecter à Binance pour exécuter un ordre sur {symbol}.")
        send_telegram_message(f"Erreur de connexion : Impossible de se connecter à Binance pour exécuter un ordre sur {symbol}.")
        return None

# Fonction pour vérifier si les ordres sont remplis
def check_order_filled(order):
    """
    Vérifie si l'ordre a été complètement exécuté.
    
    :param order: Détails de l'ordre
    :return: True si l'ordre est rempli, sinon False
    """
    return order and order['status'] == 'closed'

# Fonction pour choisir et exécuter la stratégie la plus rentable
def execute_if_profitable():
    try:
        # Liste des paires à surveiller
        pairs_to_monitor = ['ETH/USDC', 'SOL/USDC', 'ARB/USDC', 'MATIC/USDC', 'BNB/USDC', 'XRP/USDC', 'DOGE/USDC', 'ADA/USDC']

        # Stocker les profits pour chaque paire et chaque stratégie
        net_profits = {}

        # Boucle pour simuler et calculer les profits pour chaque paire
        for pair in pairs_to_monitor:
            # Simuler les trois stratégies (Achat-Vente-Achat, Achat-Achat-Vente, et Achat-Vente-Vente)
            buy_sell_buy_profit = simulate_buy_sell_buy(pair)
            buy_buy_sell_profit = simulate_buy_buy_sell(pair)
            buy_sell_sell_profit = simulate_buy_sell_sell(pair)

            # Vérifier que toutes les simulations ont bien fonctionné pour cette paire
            if buy_sell_buy_profit is not None and buy_buy_sell_profit is not None and buy_sell_sell_profit is not None:
                # Calculer les profits pour chaque stratégie avec les frais inclus
                profit_loss_buy_sell_buy = check_profit_loss(buy_sell_buy_profit, initial_investment, fees, min_profit)
                profit_loss_buy_buy_sell = check_profit_loss(buy_buy_sell_profit, initial_investment, fees, min_profit)
                profit_loss_buy_sell_sell = check_profit_loss(buy_sell_sell_profit, initial_investment, fees, min_profit)

                # Enregistrer les profits de chaque stratégie pour cette paire
                net_profits[pair] = {
                    'buy_sell_buy': profit_loss_buy_sell_buy,
                    'buy_buy_sell': profit_loss_buy_buy_sell,
                    'buy_sell_sell': profit_loss_buy_sell_sell
                }
            else:
                logging.warning(f"Simulation échouée pour la paire {pair}.")
                continue

        # Trouver la meilleure opportunité
        best_pair = None
        best_strategy = None
        best_profit = Decimal('0')  # Utiliser Decimal pour les comparaisons précises des montants

        for pair, profits in net_profits.items():
            for strategy, profit in profits.items():
                # Sélectionner la meilleure stratégie qui dépasse le seuil de profit minimum
                if profit > best_profit and profit > min_profit_threshold:
                    best_profit = profit
                    best_pair = pair
                    best_strategy = strategy

        # Exécuter la stratégie la plus rentable si elle dépasse le seuil de profit minimal
        if best_pair and best_strategy:
            logging.info(f"Exécution de la stratégie {best_strategy} pour la paire {best_pair} avec un profit de : {best_profit}")
            send_telegram_message(f"Arbitrage trouvé : {best_pair} - Stratégie {best_strategy} avec un profit de : {best_profit}")

            # Exécuter les ordres réels pour cette stratégie et paire
            if best_strategy == 'buy_sell_buy':
                execute_arbitrage_orders(best_pair, 'buy_sell_buy')
            elif best_strategy == 'buy_buy_sell':
                execute_arbitrage_orders(best_pair, 'buy_buy_sell')
            elif best_strategy == 'buy_sell_sell':
                execute_arbitrage_orders(best_pair, 'buy_sell_sell')
        else:
            logging.info("Aucune stratégie rentable détectée.")
            send_telegram_message("Aucune stratégie rentable détectée.")
    except Exception as e:
        logging.error(f"Erreur dans l'exécution des stratégies : {str(e)}")
        send_telegram_message(f"Erreur dans l'exécution des stratégies : {str(e)}")

# Envoyer une notification Telegram pour indiquer le démarrage du bot
send_telegram_message("Ok lets go !")

# Enregistrer les signaux d'arrêt
signal.signal(signal.SIGINT, send_shutdown_message)  # Interruption (Ctrl+C)
signal.signal(signal.SIGTERM, send_shutdown_message)  # Arrêt du serveur

# Boucle principale pour rechercher des opportunités d'arbitrage
while True:
    try:
        if find_arbitrage_opportunity():
            execute_if_profitable()  # Simuler et n'exécuter que si rentable
        time.sleep(1)  # Ajuster en fonction de la performance
    except Exception as e:
        logging.error(f"Erreur dans la boucle principale : {str(e)}")
        send_telegram_message(f"Erreur dans la boucle principale : {str(e)}")
        time.sleep(10)  # Attendre avant de réessayer
