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
    
# Simuler Achat-Vente-Achat
def simulate_buy_sell_buy():
    try:
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        eth_btc_price = fetch_current_ticker_price('ETH/BTC')
        btc_usdc_price = fetch_current_ticker_price('BTC/USDC')

        eth_amount = initial_investment / Decimal(eth_usdc_price)
        btc_amount = eth_amount * Decimal(eth_btc_price)
        final_eth_amount = btc_amount / Decimal(btc_usdc_price)

        logging.info(f"Simulation Achat-Vente-Achat : Final ETH amount: {final_eth_amount}")
        return final_eth_amount  # Retourne le montant final en ETH
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Vente-Achat : {str(e)}")
        return None

# Simuler Achat-Achat-Vente
def simulate_buy_buy_sell():
    try:
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        eth_btc_price = fetch_current_ticker_price('ETH/BTC')
        btc_usdc_price = fetch_current_ticker_price('BTC/USDC')

        eth_amount = initial_investment / Decimal(eth_usdc_price)
        btc_amount = eth_amount * Decimal(eth_btc_price)
        final_usdc_amount = btc_amount * Decimal(btc_usdc_price)

        logging.info(f"Simulation Achat-Achat-Vente : Final USDC amount: {final_usdc_amount}")
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Achat-Vente : {str(e)}")
        return None

# Simuler Achat-Vente-Vente
def simulate_buy_sell_sell():
    try:
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        eth_btc_price = fetch_current_ticker_price('ETH/BTC')
        btc_usdc_price = fetch_current_ticker_price('BTC/USDC')

        eth_amount = initial_investment / Decimal(eth_usdc_price)
        btc_amount = eth_amount * Decimal(eth_btc_price)
        final_usdc_amount = btc_amount * Decimal(btc_usdc_price)

        logging.info(f"Simulation Achat-Vente-Vente : Final USDC amount: {final_usdc_amount}")
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de la simulation Achat-Vente-Vente : {str(e)}")
        return None

# Fonction pour exécuter les ordres d'achat et vente
def execute_order(symbol, side, amount):
    binance = ensure_binance_connection()  # Vérifier et reconnecter si nécessaire
    if binance:
        try:
            if side == 'buy':
                order = binance.create_market_buy_order(symbol, amount)
            else:
                order = binance.create_market_sell_order(symbol, amount)
            return order
        except Exception as e:
            logging.error(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            send_telegram_message(f"Erreur lors de l'exécution de l'ordre {side} pour {symbol}: {str(e)}")
            return None
    else:
        logging.error(f"Impossible de se connecter à Binance pour exécuter un ordre sur {symbol}.")
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
def execute_arbitrage_orders():
    try:
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        eth_amount = initial_investment / Decimal(eth_usdc_price)
        
        # Exécuter les ordres
        order1 = execute_order_with_retry('ETH/USDC', 'buy', eth_amount)
        if not check_order_filled(order1):
            logging.error("L'ordre 1 n'a pas été rempli, arrêt de l'arbitrage.")
            return None
        
        order2 = execute_order_with_retry('ETH/BTC', 'sell', eth_amount)
        if not check_order_filled(order2):
            logging.error("L'ordre 2 n'a pas été rempli, arrêt de l'arbitrage.")
            return None
        
        btc_amount = eth_amount * Decimal(fetch_current_ticker_price('ETH/BTC'))
        order3 = execute_order_with_retry('BTC/USDC', 'sell', btc_amount)
        if not check_order_filled(order3):
            logging.error("L'ordre 3 n'a pas été rempli, arrêt de l'arbitrage.")
            return None
        
        # Vérifier que tous les ordres sont remplis
        final_usdc_amount = btc_amount * Decimal(fetch_current_ticker_price('BTC/USDC'))
        return final_usdc_amount
    except Exception as e:
        logging.error(f"Erreur lors de l'exécution des ordres d'arbitrage: {str(e)}")
        send_telegram_message(f"Erreur lors de l'exécution des ordres d'arbitrage: {str(e)}")
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
        sui_usdc_price = fetch_current_ticker_price('SUI/USDC')
        pepe_usdc_price = fetch_current_ticker_price('PEPE/USDC')

        # Vérifier que tous les prix sont bien récupérés
        if None in [usdc_usdt_price, btc_usdc_price, eth_usdc_price, sol_usdc_price, 
                    arb_usdc_price, matic_usdc_price, bnb_usdc_price, xrp_usdc_price, 
                    sui_usdc_price, pepe_usdc_price]:
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
        net_profits['SUI'] = ((investment / Decimal(sui_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment
        net_profits['PEPE'] = ((investment / Decimal(pepe_usdc_price)) * Decimal(btc_usdc_price)) * (1 - total_fees) - investment

        # Trouver la paire la plus rentable
        best_pair = max(net_profits, key=net_profits.get)
        best_profit = net_profits[best_pair]

        # Comparaison avec le min_profit attendu
        if best_profit > min_profit:
            logging.info(f"Arbitrage trouvé avec la paire {best_pair}/USDC ! Profit potentiel après frais : {best_profit}")
            send_telegram_message(f"Arbitrage trouvé avec la paire {best_pair}/USDC ! Profit potentiel : {best_profit}")
            return True
        else:
            logging.info(f"Pas d'opportunité rentable. Meilleur profit potentiel ({best_pair}/USDC) : {best_profit}")
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
        pairs_to_monitor = ['ETH/USDC', 'SOL/USDC', 'ARB/USDC', 'MATIC/USDC', 'BNB/USDC', 'XRP/USDC', 'SUI/USDC', 'PEPE/USDC']

        # Stocker les profits pour chaque paire
        net_profits = {}

        # Boucle pour simuler et calculer les profits pour chaque paire
        for pair in pairs_to_monitor:
            buy_sell_buy_profit = simulate_buy_sell_buy(pair)
            buy_buy_sell_profit = simulate_buy_buy_sell(pair)
            buy_sell_sell_profit = simulate_buy_sell_sell(pair)

            # Vérifier que toutes les simulations ont bien fonctionné pour cette paire
            if buy_sell_buy_profit and buy_buy_sell_profit and buy_sell_sell_profit:
                # Calculer les profits pour chaque stratégie
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
        best_profit = 0

        for pair, profits in net_profits.items():
            for strategy, profit in profits.items():
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
