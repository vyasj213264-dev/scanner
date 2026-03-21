import sqlite3

def run_test():
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA strict=ON") # Enforce strict typing in latest SQLite to simulate Postgres natively
    
    # Try creating table with strict Postgres-like types
    cursor.execute('''
        CREATE TABLE screen_data (
            Ticker TEXT,
            Date TEXT,
            Close REAL,
            Volume REAL,
            SMA_5 REAL,
            SMA_9 REAL,
            SMA_10 REAL,
            SMA_20 REAL,
            SMA_21 REAL,
            SMA_50 REAL,
            SMA_100 REAL,
            SMA_200 REAL,
            RVOL REAL,
            ADR_20 REAL,
            Pct_From_52W_High REAL,
            In_Stage_2 INTEGER,
            Tight_Setup INTEGER,
            Near_Horizontal_Resistance INTEGER,
            RS_Raw REAL,
            Inside_Bar INTEGER,
            Golden_Crossover INTEGER,
            Gap_Up INTEGER,
            Gap_Down INTEGER,
            VCP_Approximation INTEGER,
            Momentum_1D REAL,
            Momentum_1W REAL,
            Momentum_1M REAL,
            Momentum_3M REAL,
            Momentum_6M REAL,
            Momentum_1Y REAL,
            RS_Rating REAL,
            Sector TEXT,
            Industry TEXT,
            Market_Cap REAL,
            Stage INTEGER,
            Market TEXT
        ) STRICT
    ''')
    
    # Fake single tuple formatted EXACTLY like all_data[0]
    dummy_record = (
        'AAPL',           # Ticker
        '2026-03-20',     # Date
        150.5,            # Close
        5451392,          # Volume
        140.0,            # SMA_5
        141.0,            # SMA_9
        142.0,            # SMA_10
        143.0,            # SMA_20
        144.0,            # SMA_21
        145.0,            # SMA_50
        146.0,            # SMA_100
        147.0,            # SMA_200
        1.274,            # RVOL
        3.5,              # ADR_20
        -6.806,           # Pct_From_52W_High
        0,                # In_Stage_2 (False matches to INT in SQLite)
        0,                # Tight_Setup
        0,                # Near_Horizontal_Resistance
        98.5,             # RS_Raw
        0,                # Inside_Bar
        0,                # Golden_Crossover
        0,                # Gap_Up
        0,                # Gap_Down
        0,                # VCP_Approximation
        0.05,             # Momentum_1D
        0.10,             # Momentum_1W
        0.15,             # Momentum_1M
        0.20,             # Momentum_3M
        0.25,             # Momentum_6M
        0.30,             # Momentum_1Y
        0.0,              # RS_Rating
        'Technology',     # Sector
        'Consumer Elec',  # Industry
        2000000.0,        # Market_Cap
        2,                # Stage
        'US'              # Market appended dynamically
    )
    
    full_placeholders = ', '.join(['?'] * 36)
    
    try:
        cursor.execute(f'''
            INSERT INTO screen_data (
                Ticker, Date, Close, Volume, SMA_5, SMA_9, SMA_10, SMA_20, SMA_21, SMA_50, SMA_100, SMA_200,
                RVOL, ADR_20, Pct_From_52W_High, In_Stage_2, Tight_Setup, Near_Horizontal_Resistance, 
                RS_Raw, Inside_Bar, Golden_Crossover, Gap_Up, Gap_Down, VCP_Approximation, 
                Momentum_1D, Momentum_1W, Momentum_1M, Momentum_3M, Momentum_6M, Momentum_1Y, RS_Rating,
                Sector, Industry, Market_Cap, Stage, Market
            ) VALUES ({full_placeholders})
        ''', dummy_record)
        print("MOCK TEST SUCCESSFUL: Schema completely aligns with tuple indexing.")
    except Exception as e:
        print(f"MOCK TEST FAILED: {e}")

run_test()
