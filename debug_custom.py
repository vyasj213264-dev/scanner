import sys, os
sys.path.append(os.getcwd())
from api.database import fetch_all
import json

def debug():
    path = os.path.join(os.getcwd(), 'api', 'custom_indices_in.json')
    if not os.path.exists(path):
        print("File does not exist:", path)
        return
        
    with open(path, 'r') as f:
        custom_indices = json.load(f)

    sql = "SELECT Ticker, Momentum_1D, Momentum_1Y FROM screen_data WHERE Market = ?"
    rows = fetch_all(sql, ('IN',))
    print(f"Found {len(rows)} IN rows in DB.")
    stock_dict = {r['Ticker']: r for r in rows}
    
    for idx_id, data in list(custom_indices.items())[:2]:
        print("Checking", idx_id)
        valid = 0
        for t in data['constituents']:
            if t in stock_dict:
                valid += 1
            else:
                print(f"  Missing: {t}")
        print(f"  Found {valid} / {len(data['constituents'])}")

debug()
