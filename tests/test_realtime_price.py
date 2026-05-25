import sys
import os
sys.path.insert(0, os.getcwd())
from paper_trading.data_fetcher import fetch_realtime_price

ticker = "BTC-USD"
price = fetch_realtime_price(ticker)
print(f"Realtime price for {ticker}: {price}")
