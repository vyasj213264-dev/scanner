import sys
import pandas as pd
import yfinance as yf
import requests

def main():
    print("Fetching from Nasdaq...", flush=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    url = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true'
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        rows = data['data']['rows']
        print(f"Got {len(rows)} raw rows", flush=True)
        
        valid_tickers = []
        for row in rows:
            try:
                price_str = str(row['lastsale']).replace('$', '').replace(',', '').strip()
                if price_str and float(price_str) >= 5.0:
                    symbol = str(row['symbol']).replace('.', '-').upper().strip()
                    if '^' not in symbol and '/' not in symbol and '~' not in symbol:
                        if len(symbol) <= 10 and symbol not in ('-', 'CASH', 'OTHER', 'USD'):
                            valid_tickers.append(symbol)
            except:
                pass
                
        print(f"Filtered to {len(valid_tickers)} tickers.", flush=True)
        
        test_chunk = valid_tickers[:10]
        print(f"Testing yfinance on {test_chunk}...", flush=True)
        
        # Test download
        temp_data = yf.download(test_chunk, period='2y', group_by='ticker', progress=False, threads=False)
        print(f"Yfinance download complete. Data shape: {temp_data.shape}", flush=True)
        
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == '__main__':
    main()
