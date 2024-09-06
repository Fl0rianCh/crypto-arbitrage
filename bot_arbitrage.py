import ccxt
import time

# Clés API de Binance
binance_api_key = 'job6FqJN3HZ0ekXO7uZ245FwCwbLbFIrz0Zrlq4pflUgXoCPw0ehmscdzNv0PGIA'
binance_secret_key = 'pGUCIqZpKF25EBDZCokGFJbU6aI051wJEPjj0f3TkQWsiKiW2nEgN9nV7Op4D1Ns'

# Clés API de KuCoin (facultatif si tu ne l'utilises pas pour l'instant)
kucoin_api_key = '66db75000a48170001a2a302'
kucoin_secret_key = '958f9568-57c4-4804-8a43-dacfdcf07591'

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
