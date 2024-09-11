import ccxt
import time
import logging
from logging.handlers import TimedRotatingFileHandler

# Configuration API Binance
binance_api_key = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
binance_secret_key = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Configuration API KuCoin
kucoin_api_key = '66dffc92e72ff9000190a3ae'
kucoin_secret_key = '786adb6d-03a4-464e-8ed3-15330dc48fc5'
kucoin_password = 'yD13A5fc18102023$'

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

# Configuration du bot
min_price_difference = 10  # Seuil minimum de différence de prix en USDT pour arbitrage
trading_pairs = ['ETH/USDT', 'XRP/USDT', 'SOL/USDT', 'DOT/USDT', 'AVAX/USDT', 'MATIC/USDT']

# Logger pour enregistrer les activités
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler = TimedRotatingFileHandler("arbitrage_analysis.log", when="midnight", interval=1, backupCount=2)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Fonction pour récupérer les prix sur Binance et KuCoin
def get_prices(trading_pair):
    try:
        binance_price = binance.fetch_ticker(trading_pair)['last']
        kucoin_price = kucoin.fetch_ticker(trading_pair)['last']
        return binance_price, kucoin_price
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des prix pour {trading_pair} : {e}")
        return None, None

# Fonction pour analyser les opportunités d'arbitrage
def analyze_arbitrage_opportunities():
    while True:
        logger.info("Analyse des opportunités d'arbitrage en cours...")
        for pair in trading_pairs:
            binance_price, kucoin_price = get_prices(pair)
            if binance_price and kucoin_price:
                logger.info(f"Prix Binance pour {pair} : {binance_price}")
                logger.info(f"Prix KuCoin pour {pair} : {kucoin_price}")

                price_diff = abs(binance_price - kucoin_price)
                if price_diff > min_price_difference:
                    if binance_price > kucoin_price:
                        logger.info(f"Opportunité d'arbitrage : acheter sur KuCoin à {kucoin_price} et vendre sur Binance à {binance_price}")
                    else:
                        logger.info(f"Opportunité d'arbitrage : acheter sur Binance à {binance_price} et vendre sur KuCoin à {kucoin_price}")
                else:
                    logger.info(f"Pas d'opportunité d'arbitrage pour {pair}, différence trop faible.")
        time.sleep(60)

# Lancer l'analyse
analyze_arbitrage_opportunities()
