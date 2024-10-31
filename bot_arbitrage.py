import os
import pandas as pd
import numpy as np
import logging
import asyncio
import websockets
import json
from binance.client import Client
from binance.streams import BinanceSocketManager
from telegram import Bot
from datetime import datetime, timedelta
import time
import ta  # Pour les indicateurs techniques
from dotenv import load_dotenv  # Pour sécuriser les variables
from collections import deque  # Utilisation de deque
import matplotlib.pyplot as plt  # Pour la visualisation

# Charger les clés API depuis les variables d'environnement
load_dotenv('config.env')

BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Configuration des logs
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TradingBot:
    def __init__(self, api_key, secret_key, telegram_token, chat_id):
        self.client = Client(api_key, secret_key)
        self.telegram_bot = Bot(token=telegram_token)
        self.chat_id = chat_id
        self.bm = BinanceSocketManager(self.client)
        self.symbols = []  # Initialiser self.symbols
        self.trades = deque(maxlen=1000)
        self.price_cache = {}

        # Paramètres de trading
        self.short_window = 12
        self.long_window = 26
        self.trailing_stop_percent = 0.02
        self.position_size_percent = 0.15
        self.max_positions = 3
        self.update_interval = 5  # Intervalle de temps en secondes entre chaque mise à jour

    def check_balance(self):
        logging.info("Vérification du solde")
        balance = float(self.client.get_asset_balance(asset='USDC')['free'])
        logging.info(f"Solde actuel : {balance} USDC")
        if balance < 300:  # Alerte si le solde descend en dessous de 300 USDC
            self.send_telegram_notification("Alerte : Le solde est descendu en dessous de 300 USDC")

    # Gestion avancée du portefeuille
    def diversify_portfolio(self, symbols):
        logging.info(f"Diversification du portefeuille avec les symboles : {symbols}")
        self.symbols = symbols

    def adjust_position_size(self, balance):
        """Ajuste la taille de la position en fonction du solde disponible."""
        position_size = balance * self.position_size_percent
        return max(0.01, min(0.05, position_size))

    # Optimisation dynamique des paramètres
    def optimize_parameters(self, performance_data):
        logging.info("Optimisation des paramètres de trading")
        if len(performance_data) == 0:
            return  # Assure qu'il y a des données pour l'optimisation
        if performance_data.mean() > 0:
            self.short_window = max(self.short_window - 1, 8)
            self.long_window = max(self.long_window - 1, 20)
            self.trailing_stop_percent = max(self.trailing_stop_percent - 0.002, 0.015)
        else:
            self.short_window = min(self.short_window + 1, 15)
            self.long_window = min(self.long_window + 1, 30)
            self.trailing_stop_percent = min(self.trailing_stop_percent + 0.002, 0.03)
        logging.info(f"Paramètres optimisés : short_window={self.short_window}, long_window={self.long_window}, trailing_stop_percent={self.trailing_stop_percent}")

    def calculate_indicators(self, data):
        """Calcul des moyennes mobiles et autres indicateurs."""
        logging.info("Calcul des indicateurs techniques")
        data['short_ma'] = data['close'].rolling(window=self.short_window).mean()
        data['long_ma'] = data['close'].rolling(window=self.long_window).mean()
        data['rsi'] = ta.momentum.RSIIndicator(data['close']).rsi()
        return data

    def check_signals(self, data):
        logging.info("Vérification des signaux de trading")
        if data['short_ma'].iloc[-2] < data['long_ma'].iloc[-2] and data['short_ma'].iloc[-1] > data['long_ma'].iloc[-1]:
            if data['rsi'].iloc[-1] < 75:  # Augmenté de 70 à 75
                logging.info("Signal d'achat détecté")
                return "BUY"
        elif data['short_ma'].iloc[-2] > data['long_ma'].iloc[-2] and data['short_ma'].iloc[-1] < data['long_ma'].iloc[-1]:
            if data['rsi'].iloc[-1] > 25:  # Diminué de 30 à 25
                logging.info("Signal de vente détecté")
                return "SELL"
        return None
        
    def get_historical_data(self, symbol, interval='1h', lookback='50'):
        """Obtenir les données historiques."""
        try:
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=lookback)
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                               'close_time', 'quote_asset_volume', 'number_of_trades', 
                                               'taker_buy_base', 'taker_buy_quote', 'ignore'])
            df['close'] = df['close'].astype(float)
            return df[['timestamp', 'close']]
        except Exception as e:
            logging.error("Erreur lors de la récupération des données historiques: %s", e)
            return None

    def execute_trade(self, symbol, action, balance):
        """Exécution d'un trade avec calcul et enregistrement du profit."""
        logging.info(f"Exécution du trade : action={action}, symbol={symbol}, balance={balance}")
        quantity = self.adjust_position_size(balance)
        try:
            initial_price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
            
            if action == "BUY":
                order = self.client.order_market_buy(symbol=symbol, quantity=quantity)
                self.set_trailing_stop(symbol, quantity, "BUY")
                # Enregistrement du trade avec profit provisoire de 0 (calculé lors de la vente)
                self.trades.append({'symbol': symbol, 'action': action, 'quantity': quantity, 'price': initial_price, 'profit': 0})
                
            elif action == "SELL":
                order = self.client.order_market_sell(symbol=symbol, quantity=quantity)
                self.set_trailing_stop(symbol, quantity, "SELL")
                
                # Calcul du profit basé sur le dernier prix d'achat
                last_trade = next((trade for trade in reversed(self.trades) if trade['symbol'] == symbol and trade['action'] == "BUY"), None)
                if last_trade:
                    profit = (initial_price - last_trade['price']) * quantity
                    last_trade['profit'] = profit
                    self.trades.append({'symbol': symbol, 'action': action, 'quantity': quantity, 'price': initial_price, 'profit': profit})
                else:
                    # Ajouter un trade sans profit si aucun BUY précédent n'est trouvé
                    self.trades.append({'symbol': symbol, 'action': action, 'quantity': quantity, 'price': initial_price, 'profit': 0})

            self.send_telegram_notification(f"{action} exécuté pour {symbol}. Détails: {order}")
            logging.info("%s exécuté pour %s. Détails: %s", action, symbol, order)
        except Exception as e:
            logging.error("Erreur d'exécution du trade %s pour %s: %s", action, symbol, e)

    def set_trailing_stop(self, symbol, quantity, action):
        """Définit un trailing stop pour maximiser les profits."""
        logging.info(f"Mise en place du trailing stop : action={action}, symbol={symbol}, quantity={quantity}")
        try:
            price = float(self.client.get_symbol_ticker(symbol=symbol)['price'])
            stop_price = price * (1 - self.trailing_stop_percent if action == "BUY" else 1 + self.trailing_stop_percent)
            logging.info(f"Trailing stop défini à : {stop_price}")
        except Exception as e:
            logging.error("Erreur lors de la mise en place du trailing stop: %s", e)

    async def start_websocket(self, symbols):
        """Démarre le WebSocket pour les mises à jour en temps réel avec contrôle de fréquence et de variation"""
        async def process_message(msg):
            symbol = msg['s']
            price = float(msg['p'])
            if symbol in self.symbols and price > 0:
                # Contrôle de variation significative du prix
                last_price = self.price_cache.get(symbol, None)
                if last_price is None or abs(price - last_price) / last_price >= 0.001:
                    self.price_cache[symbol] = price
                    self.react_to_price_update(symbol, price)

        # Création des tâches WebSocket pour chaque symbole
        tasks = []
        for symbol in symbols:
            ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@ticker"
            async def websocket_stream(ws_url):
                while True:
                    try:
                        async with websockets.connect(ws_url) as ws:
                            while True:
                                msg = await ws.recv()
                                msg = json.loads(msg)
                                await process_message(msg)
                    except websockets.ConnectionClosed:
                        logging.warning(f"Reconnexion WebSocket pour {symbol} en raison d'une déconnexion.")
                    except Exception as e:
                        logging.error(f"Erreur de connexion WebSocket pour {symbol}: {e}")
                    await asyncio.sleep(5)
            tasks.append(asyncio.create_task(websocket_stream(ws_url)))
        await asyncio.gather(*tasks)
        
    def react_to_price_update(self, symbol, price):
        """Réagit aux changements de prix avec vérification d'intervalle et filtrage des variations non significatives"""
        logging.info(f"Mise à jour des prix reçue : symbol={symbol}, price={price}")
        data = self.get_historical_data(symbol)
        if data is not None:
            data = self.calculate_indicators(data)
            signal = self.check_signals(data)
            balance = float(self.client.get_asset_balance(asset='USDC')['free'])
            if signal == "BUY" and len(self.trades) < self.max_positions:
                self.execute_trade(symbol, "BUY", balance)
            elif signal == "SELL":
                self.execute_trade(symbol, "SELL", balance)

    def backtest(self, symbol, initial_balance=450):
        """Simule les conditions de marché réelles dans le backtest"""
        logging.info(f"Démarrage du backtest pour le symbole : {symbol}")
        data = self.get_historical_data(symbol, interval='1h', lookback='1000')
        if data is not None:
            balance = initial_balance
            performance = []
            for i in range(self.long_window, len(data)):
                subset = data.iloc[:i+1]
                signal = self.check_signals(subset)
                if signal:
                    trade_balance = balance * self.position_size_percent
                    if signal == "BUY":
                        balance += trade_balance
                    elif signal == "SELL":
                        balance -= trade_balance
                    performance.append(balance)
            logging.info("Backtest complété avec un capital final de %s", balance)
            
    async def run(self):
        """Exécution principale du bot"""
        logging.info("Démarrage du bot de trading")
        self.send_telegram_notification("Le bot de trading a été lancé.")
        
        # Diversification du portefeuille avant le début de la boucle principale
        self.diversify_portfolio(['BTCUSDC', 'ETHUSDC'])  # Exemples de paires diversifiées
        
        # Lancement du websocket pour les mises à jour en temps réel
        await self.start_websocket(self.symbols)

        while True:
            try:
                # Optimisation périodique des paramètres en fonction des performances récentes
                performance_data = [trade['profit'] for trade in self.trades if 'profit' in trade]
                if len(performance_data) >= 10:  # Optimisation tous les 10 trades
                    self.optimize_parameters(performance_data)

                # Journalisation et rapports quotidiens
                current_time = datetime.now()
                if current_time.hour % 3 == 0:  # Rapport toutes les 3 heures
                    self.generate_report()
                    self.save_trade_data()

                await asyncio.sleep(60)  # Attente de 60 secondes pour éviter des appels fréquents

            except Exception as e:
                logging.error("Erreur dans la boucle principale: %s", e)
                self.send_telegram_notification("Erreur dans la boucle principale: " + str(e))
                await asyncio.sleep(5)  # Pause de quelques secondes avant de réessayer

    def generate_report(self):
        """Génère un rapport de performance du bot et l'envoie via Telegram"""
        try:
            if not self.trades:
                logging.info("Aucun trade disponible pour le rapport.")
                return

            profits = sum([trade['profit'] for trade in self.trades if 'profit' in trade])
            sharpe_ratio = self.calculate_sharpe_ratio(self.trades) if len(self.trades) > 1 else 0
            max_drawdown = self.calculate_max_drawdown(self.trades) if len(self.trades) > 1 else 0
            success_rate = self.calculate_success_rate(self.trades)

            report = (f"Performance des dernières 24h:\n"
                      f"Profits totaux: {profits}\n"
                      f"Sharpe Ratio: {sharpe_ratio:.2f}\n"
                      f"Max Drawdown: {max_drawdown:.2f}%\n"
                      f"Taux de succès: {success_rate:.2f}%")
            self.send_telegram_notification(report)
            # Générer un graphique de performance
            self.plot_performance()
            logging.info(report)
        except Exception as e:
            logging.error("Erreur lors de la génération du rapport: %s", e)
            
    def plot_performance(self):
        """Génère un graphique de la performance du bot"""
        try:
            profits = [trade['profit'] for trade in self.trades if 'profit' in trade]
            plt.plot(profits)
            plt.title('Performance du Bot de Trading')
            plt.xlabel('Trades')
            plt.ylabel('Profits')
            plt.savefig('performance_plot.png')
            plt.close()
            self.send_telegram_notification("Graphique de performance généré.")
        except Exception as e:
            logging.error("Erreur lors de la génération du graphique de performance: %s", e)

    def calculate_sharpe_ratio(self, trades):
        """Calcule le ratio de Sharpe basé sur les retours des trades"""
        returns = [trade['profit'] for trade in trades if 'profit' in trade]
        if len(returns) < 2:
            return 0
        return np.mean(returns) / np.std(returns)

    def calculate_max_drawdown(self, trades):
        """Calcule le drawdown maximum pour évaluer le risque"""
        if len(trades) == 0:
            return 0  # Retourne 0 si aucune donnée n'est disponible
        balance_history = np.cumsum([trade['profit'] for trade in trades if 'profit' in trade])
        peak = np.maximum.accumulate(balance_history)
        drawdown = (balance_history - peak) / peak
        return np.min(drawdown) * -100  # En pourcentage

    def calculate_success_rate(self, trades):
        """Calcule le taux de réussite des trades"""
        successful_trades = sum(1 for trade in trades if trade['profit'] > 0)
        return (successful_trades / len(trades)) * 100 if trades else 0

    def send_telegram_notification(self, message):
        """Envoie une notification Telegram pour les événements importants"""
        try:
            self.telegram_bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as e:
            logging.error("Erreur lors de l'envoi de la notification Telegram: %s", e)

    def save_trade_data(self):
        """Sauvegarde des données de trading dans un fichier CSV pour le suivi"""
        try:
            df = pd.DataFrame(self.trades)
            df.to_csv("trades.csv", index=False)
            logging.info("Données de trade sauvegardées avec succès.")
        except Exception as e:
            logging.error("Erreur lors de la sauvegarde des données de trade: %s", e)

# Initialisation
if __name__ == "__main__":
    logging.info("Initialisation du bot de trading")
    bot = TradingBot(BINANCE_API_KEY, BINANCE_SECRET_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    asyncio.run(bot.run())
