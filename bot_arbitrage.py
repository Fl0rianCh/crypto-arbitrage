import ccxt
import time
import logging
from decimal import Decimal
from telegram import Bot
from logging.handlers import TimedRotatingFileHandler
import math  # Import nécessaire pour la fonction check_if_float_zero

# Configuration des clés API Binance
BINANCE_API_KEY = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
BINANCE_SECRET_KEY = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration de l'API Telegram pour les notifications
TELEGRAM_TOKEN = '7501427979:AAE-r03vaNZjuATvSL5FUdAHqn2BjwV0Gok'
TELEGRAM_CHAT_ID = '1887133385'
bot = Bot(token=TELEGRAM_TOKEN)

# Paramètres dynamiques
initial_investment = Decimal('20')  # Montant investi
transaction_brokerage = Decimal('0.075')  # Frais sur Binance 0.075%
min_profit = min_profit = initial_investment * Decimal('0.01') # Profit minimum attendu en %

# Montant minimum de profit pour déclencher l'arbitrage (par exemple 0,1% de profit)
min_profit_threshold = Decimal('0.001')  # Seuil de profit minimum de 0,1%

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
def connect_to_binance():
    try:
        binance = ccxt.binance({
            'apiKey': BINANCE_API_KEY,
            'secret': BINANCE_SECRET_KEY,
            'enableRateLimit': True
        })
        return binance
    except Exception as e:
        logging.error(f"Erreur lors de la connexion à Binance: {str(e)}")
        send_telegram_message(f"Erreur de connexion à Binance: {str(e)}")
        return None

binance = connect_to_binance()

# Fonction pour récupérer les frais de trading réels via l'API Binance
def get_binance_fees():
    try:
        fees_info = binance.fetch_trading_fees()
        if 'ETH/USDC' in fees_info:
            return {
                'binance': Decimal(fees_info['ETH/USDC']['maker'])  # Par exemple récupérer le maker fee
            }
        else:
            logging.error("Frais pour ETH/USDC non disponibles via l'API, utilisation des frais par défaut.")
            return fees  # Retour aux frais par défaut
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des frais de Binance : {str(e)}")
        return fees  # Utiliser les frais définis manuellement

# Fonction pour récupérer le prix actuel d'une paire de trading
def fetch_current_ticker_price(ticker):
    current_ticker_details = binance.fetch_ticker(ticker)
    ticker_price = current_ticker_details['close'] if current_ticker_details is not None else None
    return ticker_price
    
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
        
def execute_order_with_retry(symbol, side, amount, retries=3):
    attempt = 0
    while attempt < retries:
        order = execute_order(symbol, side, amount)  # Appel correct
        if check_order_filled(order):
            return order
        attempt += 1
        time.sleep(0.1)  # Attendre 100ms avant de réessayer
    logging.error(f"Erreur : L'ordre {side} pour {symbol} n'a pas été rempli après {retries} tentatives.")
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

# Fonction pour calculer le profit net après les frais
def check_profit_loss(total_price_after_sell, initial_investment, transaction_brokerage, min_profit):
    apprx_brokerage = transaction_brokerage * initial_investment / 100 * 3  # Frais sur 3 transactions
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
        # Récupérer les prix des paires ETH/USDC, ETH/BTC, BTC/USDC
        eth_usdc_price = fetch_current_ticker_price('ETH/USDC')
        eth_btc_price = fetch_current_ticker_price('ETH/BTC')
        btc_usdc_price = fetch_current_ticker_price('BTC/USDC')

        # Calcul du profit net
        net_profit = (1 / Decimal(eth_usdc_price)) * Decimal(eth_btc_price) * Decimal(btc_usdc_price) - Decimal(1)

        if net_profit > min_profit_threshold:
            logging.info(f"Arbitrage trouvé ! Profit potentiel après frais : {net_profit}")
            send_telegram_message(f"Arbitrage trouvé ! Profit potentiel : {net_profit}")
            return True
        else:
            logging.info(f"Pas d'opportunité rentable. Profit potentiel : {net_profit}")
            return False
    except Exception as e:
        logging.error(f"Erreur lors du calcul de l'arbitrage: {str(e)}")
        send_telegram_message(f"Erreur lors du calcul de l'arbitrage: {str(e)}")
        return False

# Fonction pour choisir et exécuter la stratégie la plus rentable
def execute_if_profitable():
    # Simuler les stratégies
    final_price_buy_sell_buy = simulate_buy_sell_buy()
    final_price_buy_buy_sell = simulate_buy_buy_sell()
    final_price_buy_sell_sell = simulate_buy_sell_sell()

    # Calculer les profits pour les trois stratégies
    if final_price_buy_buy_sell and final_price_buy_sell_sell and final_price_buy_sell_buy:
        profit_loss_buy_buy_sell = check_profit_loss(final_price_buy_buy_sell, initial_investment, transaction_brokerage, min_profit)
        profit_loss_buy_sell_sell = check_profit_loss(final_price_buy_sell_sell, initial_investment, transaction_brokerage, min_profit)
        profit_loss_buy_sell_buy = check_profit_loss(final_price_buy_sell_buy, initial_investment, transaction_brokerage, min_profit)

        logging.info(f"Profit Achat-Achat-Vente: {profit_loss_buy_buy_sell}")
        logging.info(f"Profit Achat-Vente-Vente: {profit_loss_buy_sell_sell}")
        logging.info(f"Profit Achat-Vente-Achat: {profit_loss_buy_sell_buy}")

        # Comparer les trois stratégies et exécuter la plus rentable
        if profit_loss_buy_buy_sell > min_profit_threshold and profit_loss_buy_buy_sell > profit_loss_buy_sell_sell and profit_loss_buy_buy_sell > profit_loss_buy_sell_buy:
            logging.info(f"Exécution de la stratégie Achat-Achat-Vente avec un profit de : {profit_loss_buy_buy_sell}")
            execute_arbitrage_orders()  # Appel réel pour exécuter cette stratégie
        elif profit_loss_buy_sell_sell > min_profit_threshold and profit_loss_buy_sell_sell > profit_loss_buy_buy_sell and profit_loss_buy_sell_sell > profit_loss_buy_sell_buy:
            logging.info(f"Exécution de la stratégie Achat-Vente-Vente avec un profit de : {profit_loss_buy_sell_sell}")
            execute_arbitrage_orders()  # Appel réel pour exécuter cette stratégie
        elif profit_loss_buy_sell_buy > min_profit_threshold:
            logging.info(f"Exécution de la stratégie Achat-Vente-Achat avec un profit de : {profit_loss_buy_sell_buy}")
            execute_arbitrage_orders()  # Appel réel pour exécuter cette stratégie
        else:
            logging.info("Aucune stratégie rentable détectée.")
            send_telegram_message("Aucune stratégie rentable détectée.")
    else:
        logging.error("Erreur dans la simulation des stratégies.")

# Envoyer une notification Telegram pour indiquer le démarrage du bot
send_telegram_message("Ok lets go !")

# Boucle principale pour rechercher des opportunités d'arbitrage
while True:
    if find_arbitrage_opportunity():
        execute_if_profitable()  # Simuler et n'exécuter que si rentable
    time.sleep(2)  # Ajuster en fonction de la performance
