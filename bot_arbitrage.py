import ccxt
import time

# Clés API de Binance
binance_api_key = 'TA_CLE_API_BINANCE'
binance_secret_key = 'TON_SECRET_API_BINANCE'

# Clés API de KuCoin (facultatif si tu ne l'utilises pas pour l'instant)
kucoin_api_key = 'TA_CLE_API_KUCOIN'
kucoin_secret_key = 'TON_SECRET_API_KUCOIN'

# Connexion à Binance
binance = ccxt.binance({
    'apiKey': binance_api_key,
    'secret': binance_secret_key,
})

# Connexion à KuCoin
kucoin = ccxt.kucoin({
    'apiKey': kucoin_api_key,
    'secret': kucoin_secret_key,
})

def fetch_prices():
    # Récupérer les prix sur Binance
    binance_price = binance.fetch_ticker('BTC/USDT')['last']

    # Récupérer les prix sur KuCoin
    kucoin_price = kucoin.fetch_ticker('BTC/USDT')['last']

    return binance_price, kucoin_price

def arbitrage():
    while True:
        try:
            # Récupérer les prix des deux exchanges
            binance_price, kucoin_price = fetch_prices()

            # Calculer l'écart de prix
            if binance_price > kucoin_price:
                print(f"Acheter sur KuCoin à {kucoin_price} et vendre sur Binance à {binance_price}")
            elif kucoin_price > binance_price:
                print(f"Acheter sur Binance à {binance_price} et vendre sur KuCoin à {kucoin_price}")
            else:
                print("Pas d'opportunités d'arbitrage pour l'instant.")

            # Attendre 10 secondes avant de vérifier à nouveau
            time.sleep(10)

        except Exception as e:
            print(f"Erreur : {e}")

# Lancer l'arbitrage
arbitrage()
