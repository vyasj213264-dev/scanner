import sys
import re

def main():
    # Read existing
    with open('master_universe.txt', 'r') as f:
        existing = set(line.strip() for line in f if line.strip())

    # User provided string (third batch)
    new_str = "ADBE, AMD, ABNB, ALNY, GOOGL, GOOG, AMZN, AEP, AMGN, ADI, AAPL, AMAT, APP, ARM, ASML, TEAM, ADSK, ADP, AXON, BKR, BKNG, AVGO, CDNS, CHTR, CTAS, CSCO, CCEP, CTSH, CMCSA, CEG, CPRT, CSGP, COST, CRWD, CSX, DDOG, DXCM, FANG, DASH, EA, EXC, FAST, FER, FTNT, GEHC, GILD, HON, IDXX, INSM, INTC, INTU, ISRG, KDP, KLAC, KHC, LRCX, LIN, MAR, MRVL, MELI, META, MCHP, MU, MSFT, MDLZ, MPWR, MNST, NFLX, NVDA, NXPI, ORLY, ODFL, PCAR, PLTR, PANW, PAYX, PYPL, PDD, PEP, QCOM, REGN, ROP, ROST, STX, SHOP, SBUX, MSTR, SNPS, TMUS, TTWO, TSLA, TXN, TRI, VRSK, VRTX, WMT, WDC, WDAY, WBD, XEL, ZS"

    # Split and clean
    new_symbols = set()
    for s in new_str.split(','):
        s = s.strip().upper()
        s = s.replace(' ', '')
        if s:
            new_symbols.add(s)

    # Union
    union_set = existing.union(new_symbols)
    # Sort
    sorted_union = sorted(list(union_set))

    # Write back
    with open('master_universe.txt', 'w') as f:
        for s in sorted_union:
            f.write(f"{s}\n")

    print(f"Old count: {len(existing)}")
    print(f"New symbols provided: {len(new_symbols)}")
    print(f"New union count: {len(sorted_union)}")

if __name__ == '__main__':
    main()
