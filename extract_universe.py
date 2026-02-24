import requests
from bs4 import BeautifulSoup
import json
import re

def extract_tradingview_watchlist(url):
    """
    Extracts ticker symbols from a public TradingView watchlist URL.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        print(f"Fetching {url}...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # TradingView stores the list data in a JSON object inside a script tag
        html_content = response.text
        
        # Look for the specific window.initData object containing the symbols
        # This is a basic regex approach to find the raw ticker array
        pattern = r'"symbols":\[(.*?)\]'
        match = re.search(pattern, html_content)
        
        if match:
            raw_symbols = match.group(1)
            # Clean up the string to extract just the tickers (e.g., "NASDAQ:AAPL" -> "AAPL")
            # The raw data looks like: {"proName":"NASDAQ:TSLA"}, {"proName":"NYSE:PLTR"}
            tickers = []
            parts = html_content.split('"proName":"')
            for i in range(1, len(parts)):
                symbol_full = parts[i].split('"')[0]
                if ':' in symbol_full:
                    exchange, ticker = symbol_full.split(':', 1)
                    tickers.append(ticker)
                else:
                    tickers.append(symbol_full)
            
            # Remove duplicates while preserving order
            unique_tickers = list(dict.fromkeys(tickers))
            print(f"Successfully extracted {len(unique_tickers)} tickers.")
            
            # Save to a text file for our master list
            with open('master_universe.txt', 'w') as f:
                for ticker in unique_tickers:
                    f.write(f"{ticker}\n")
            print("Saved to master_universe.txt")
            
            return unique_tickers
        else:
            print("Could not find symbols data in the page source. TradingView might have changed their DOM structure or the list is private.")
            return []
            
    except Exception as e:
        print(f"Error fetching watchlist: {e}")
        return []

if __name__ == "__main__":
    url = "https://www.tradingview.com/watchlists/134637517/"
    extract_tradingview_watchlist(url)
