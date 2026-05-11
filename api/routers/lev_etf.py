"""
Leveraged ETF router — GET /api/v1/lev-etf/scan
                     — GET /api/v1/lev-etf/list

For scanner signals, uses the underlying ETF/stock data from screen_data.
The leveraged ETF ticker itself is only used for chart display.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter
from api.database import fetch_all

from api.routers.auth import require_user
from fastapi import Depends

router = APIRouter(prefix="/api/v1/lev-etf", tags=["Leveraged ETFs"], dependencies=[Depends(require_user)])

# ---------------------------------------------------------------------------
# Full Leveraged ETF List
# underlying = ticker to query in screen_data for scanner signals
# ---------------------------------------------------------------------------
LEV_ETF_LIST = [
    # ── Direxion / ProShares Broad Market ─────────────────────────────────
    {"ticker": "TQQQ",  "fund_name": "UltraPro QQQ",                "underlying": "QQQ",  "objective": "3x",   "asset_class": "Equity",       "net_assets": 24912249439},
    {"ticker": "QLD",   "fund_name": "Ultra QQQ",                   "underlying": "QQQ",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 9272966467},
    {"ticker": "SSO",   "fund_name": "Ultra S&P500",                "underlying": "SPY",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 6083483236},
    {"ticker": "UPRO",  "fund_name": "UltraPro S&P500",             "underlying": "SPY",  "objective": "3x",   "asset_class": "Equity",       "net_assets": 3954212272},
    {"ticker": "SQQQ",  "fund_name": "UltraPro Short QQQ",          "underlying": "QQQ",  "objective": "-3x",  "asset_class": "Equity",       "net_assets": 2657500784},
    {"ticker": "SH",    "fund_name": "Short S&P500",                "underlying": "SPY",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 1342152148},
    {"ticker": "PSQ",   "fund_name": "Short QQQ",                   "underlying": "QQQ",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 869524506},
    {"ticker": "UDOW",  "fund_name": "UltraPro Dow30",              "underlying": "DIA",  "objective": "3x",   "asset_class": "Equity",       "net_assets": 722905026},
    {"ticker": "SPXU",  "fund_name": "UltraPro Short S&P500",       "underlying": "SPY",  "objective": "-3x",  "asset_class": "Equity",       "net_assets": 534926444},
    {"ticker": "SDS",   "fund_name": "UltraShort S&P500",           "underlying": "SPY",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 504276300},
    {"ticker": "DDM",   "fund_name": "Ultra Dow30",                 "underlying": "DIA",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 439145789},
    {"ticker": "QID",   "fund_name": "UltraShort QQQ",              "underlying": "QQQ",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 339537002},
    {"ticker": "URTY",  "fund_name": "UltraPro Russell2000",        "underlying": "IWM",  "objective": "3x",   "asset_class": "Equity",       "net_assets": 283664622},
    {"ticker": "UWM",   "fund_name": "Ultra Russell2000",           "underlying": "IWM",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 220177008},
    {"ticker": "SDOW",  "fund_name": "UltraPro Short Dow30",        "underlying": "DIA",  "objective": "-3x",  "asset_class": "Equity",       "net_assets": 206590855},
    {"ticker": "RWM",   "fund_name": "Short Russell2000",           "underlying": "IWM",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 168527075},
    {"ticker": "DOG",   "fund_name": "Short Dow30",                 "underlying": "DIA",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 139995553},
    {"ticker": "MVV",   "fund_name": "Ultra MidCap400",             "underlying": "MDY",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 134528914},
    {"ticker": "SRTY",  "fund_name": "UltraPro Short Russell2000",  "underlying": "IWM",  "objective": "-3x",  "asset_class": "Equity",       "net_assets": 107659838},
    {"ticker": "TWM",   "fund_name": "UltraShort Russell2000",      "underlying": "IWM",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 75538722},
    {"ticker": "DXD",   "fund_name": "UltraShort Dow30",            "underlying": "DIA",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 62980995},
    {"ticker": "URSP",  "fund_name": "Ultra S&P 500 Equal Weight",  "underlying": "RSP",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 42268942},
    {"ticker": "UMDD",  "fund_name": "UltraPro MidCap 400",        "underlying": "MDY",  "objective": "3x",   "asset_class": "Equity",       "net_assets": 26835812},
    {"ticker": "QQUP",  "fund_name": "Ultra QQQ Mega",              "underlying": "QQQ",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 25135082},
    {"ticker": "SAA",   "fund_name": "Ultra SmallCap600",           "underlying": "SLY",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 22121246},
    {"ticker": "MYY",   "fund_name": "Short MidCap400",             "underlying": "MDY",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 3777462},
    {"ticker": "SMDD",  "fund_name": "UltraPro Short MidCap400",   "underlying": "MDY",  "objective": "-3x",  "asset_class": "Equity",       "net_assets": 2889592},
    {"ticker": "SBB",   "fund_name": "Short SmallCap600",           "underlying": "SLY",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 4885158},
    {"ticker": "SDD",   "fund_name": "UltraShort SmallCap600",      "underlying": "SLY",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 1601555},
    {"ticker": "MZZ",   "fund_name": "UltraShort MidCap400",        "underlying": "MDY",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 865068},
    {"ticker": "QQXL",  "fund_name": "Ultra QQQ Top 30",            "underlying": "QQQ",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 4697651},
    {"ticker": "QQDN",  "fund_name": "UltraShort QQQ Mega",         "underlying": "QQQ",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 1544876},
    # ── Sector ─────────────────────────────────────────────────────────────
    {"ticker": "USD",   "fund_name": "Ultra Semiconductors",        "underlying": "SOXX", "objective": "2x",   "asset_class": "Equity",       "net_assets": 1600939779},
    {"ticker": "ROM",   "fund_name": "Ultra Technology",            "underlying": "XLK",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 719581012},
    {"ticker": "UYG",   "fund_name": "Ultra Financials",            "underlying": "XLF",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 635005107},
    {"ticker": "DIG",   "fund_name": "Ultra Energy",                "underlying": "XLE",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 106031302},
    {"ticker": "BIB",   "fund_name": "Ultra Nasdaq Biotechnology",  "underlying": "IBB",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 78549135},
    {"ticker": "RXL",   "fund_name": "Ultra Health Care",           "underlying": "XLV",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 75511957},
    {"ticker": "URE",   "fund_name": "Ultra Real Estate",           "underlying": "XLRE", "objective": "2x",   "asset_class": "Equity",       "net_assets": 53659313},
    {"ticker": "UYM",   "fund_name": "Ultra Materials",             "underlying": "XLB",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 37138687},
    {"ticker": "UXI",   "fund_name": "Ultra Industrials",           "underlying": "XLI",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 28489328},
    {"ticker": "UCC",   "fund_name": "Ultra Consumer Discretionary","underlying": "XLY",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 11884612},
    {"ticker": "UGE",   "fund_name": "Ultra Consumer Staples",      "underlying": "XLP",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 11710121},
    {"ticker": "LTL",   "fund_name": "Ultra Communication Services","underlying": "XLC",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 8513718},
    {"ticker": "UPW",   "fund_name": "Ultra Utilities",             "underlying": "XLU",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 20784261},
    {"ticker": "SKF",   "fund_name": "UltraShort Financials",       "underlying": "XLF",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 19650780},
    {"ticker": "SRS",   "fund_name": "UltraShort Real Estate",      "underlying": "XLRE", "objective": "-2x",  "asset_class": "Equity",       "net_assets": 19287099},
    {"ticker": "SSG",   "fund_name": "UltraShort Semiconductors",   "underlying": "SOXX", "objective": "-2x",  "asset_class": "Equity",       "net_assets": 18930451},
    {"ticker": "SEF",   "fund_name": "Short Financials",            "underlying": "XLF",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 17931440},
    {"ticker": "UCYB",  "fund_name": "Ultra Nasdaq Cybersecurity",  "underlying": "CIBR", "objective": "2x",   "asset_class": "Equity",       "net_assets": 3836671},
    {"ticker": "SCC",   "fund_name": "UltraShort Consumer Disc.",   "underlying": "XLY",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 6786332},
    {"ticker": "SIJ",   "fund_name": "UltraShort Industrials",      "underlying": "XLI",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 6379612},
    {"ticker": "REW",   "fund_name": "UltraShort Technology",       "underlying": "XLK",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 5836656},
    {"ticker": "REK",   "fund_name": "Short Real Estate",           "underlying": "XLRE", "objective": "-1x",  "asset_class": "Equity",       "net_assets": 11792793},
    {"ticker": "SZK",   "fund_name": "UltraShort Consumer Staples", "underlying": "XLP",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 4170808},
    {"ticker": "SDP",   "fund_name": "UltraShort Utilities",        "underlying": "XLU",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 3982285},
    {"ticker": "RXD",   "fund_name": "UltraShort Health Care",      "underlying": "XLV",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 3271026},
    {"ticker": "SMN",   "fund_name": "UltraShort Materials",        "underlying": "XLB",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 2715776},
    {"ticker": "BIS",   "fund_name": "UltraShort Nasdaq Biotech",   "underlying": "IBB",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 2653528},
    {"ticker": "DUG",   "fund_name": "UltraShort Energy",           "underlying": "XLE",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 12979204},
    {"ticker": "EMTY",  "fund_name": "Decline of Retail Store ETF", "underlying": "XRT",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 2759472},
    {"ticker": "SKYU",  "fund_name": "Ultra Nasdaq Cloud Computing","underlying": "SKYY", "objective": "2x",   "asset_class": "Equity",       "net_assets": 1495326},
    # ── Commodity ──────────────────────────────────────────────────────────
    {"ticker": "AGQ",   "fund_name": "Ultra Silver",                "underlying": "SLV",  "objective": "2x",   "asset_class": "Commodity",    "net_assets": 1687507953},
    {"ticker": "UGL",   "fund_name": "Ultra Gold",                  "underlying": "GLD",  "objective": "2x",   "asset_class": "Commodity",    "net_assets": 1011905057},
    {"ticker": "SCO",   "fund_name": "UltraShort Bloomberg Crude",  "underlying": "USO",  "objective": "-2x",  "asset_class": "Commodity",    "net_assets": 721212669},
    {"ticker": "UCO",   "fund_name": "Ultra Bloomberg Crude Oil",   "underlying": "USO",  "objective": "2x",   "asset_class": "Commodity",    "net_assets": 673996089},
    {"ticker": "BOIL",  "fund_name": "Ultra Bloomberg Nat Gas",     "underlying": "UNG",  "objective": "2x",   "asset_class": "Commodity",    "net_assets": 464451990},
    {"ticker": "ZSL",   "fund_name": "UltraShort Silver",           "underlying": "SLV",  "objective": "-2x",  "asset_class": "Commodity",    "net_assets": 238085116},
    {"ticker": "KOLD",  "fund_name": "UltraShort Bloomberg Nat Gas","underlying": "UNG",  "objective": "-2x",  "asset_class": "Commodity",    "net_assets": 219781247},
    {"ticker": "GLL",   "fund_name": "UltraShort Gold",             "underlying": "GLD",  "objective": "-2x",  "asset_class": "Commodity",    "net_assets": 118226408},
    # ── Fixed Income ───────────────────────────────────────────────────────
    {"ticker": "TBT",   "fund_name": "UltraShort 20+ Year Treasury","underlying": "TLT",  "objective": "-2x",  "asset_class": "Fixed Income", "net_assets": 252188515},
    {"ticker": "TBF",   "fund_name": "Short 20+ Year Treasury",     "underlying": "TLT",  "objective": "-1x",  "asset_class": "Fixed Income", "net_assets": 88661490},
    {"ticker": "UBT",   "fund_name": "Ultra 20+ Year Treasury",     "underlying": "TLT",  "objective": "2x",   "asset_class": "Fixed Income", "net_assets": 74177297},
    {"ticker": "SJB",   "fund_name": "Short High Yield",            "underlying": "HYG",  "objective": "-1x",  "asset_class": "Fixed Income", "net_assets": 127100361},
    {"ticker": "TTT",   "fund_name": "UltraPro Short 20+ Yr Treas", "underlying": "TLT",  "objective": "-3x",  "asset_class": "Fixed Income", "net_assets": 18608974},
    {"ticker": "UST",   "fund_name": "Ultra 7-10 Year Treasury",    "underlying": "IEF",  "objective": "2x",   "asset_class": "Fixed Income", "net_assets": 25449897},
    {"ticker": "TBX",   "fund_name": "Short 7-10 Year Treasury",    "underlying": "IEF",  "objective": "-1x",  "asset_class": "Fixed Income", "net_assets": 13335136},
    {"ticker": "PST",   "fund_name": "UltraShort 7-10 Yr Treasury", "underlying": "IEF",  "objective": "-2x",  "asset_class": "Fixed Income", "net_assets": 11193394},
    {"ticker": "UJB",   "fund_name": "Ultra High Yield",            "underlying": "HYG",  "objective": "2x",   "asset_class": "Fixed Income", "net_assets": 4675400},
    # ── Crypto-Linked ──────────────────────────────────────────────────────
    {"ticker": "BITU",  "fund_name": "Ultra Bitcoin ETF",           "underlying": "IBIT", "objective": "2x",   "asset_class": "Crypto",       "net_assets": 414276784},
    {"ticker": "SBIT",  "fund_name": "UltraShort Bitcoin ETF",      "underlying": "IBIT", "objective": "-2x",  "asset_class": "Crypto",       "net_assets": 196856918},
    {"ticker": "BITI",  "fund_name": "Short Bitcoin ETF",           "underlying": "IBIT", "objective": "-1x",  "asset_class": "Crypto",       "net_assets": 148915776},
    {"ticker": "ETHT",  "fund_name": "Ultra Ether ETF",             "underlying": "ETHA", "objective": "2x",   "asset_class": "Crypto",       "net_assets": 218022178},
    {"ticker": "ETHD",  "fund_name": "UltraShort Ether ETF",        "underlying": "ETHA", "objective": "-2x",  "asset_class": "Crypto",       "net_assets": 95951913},
    {"ticker": "SETH",  "fund_name": "Short Ether ETF",             "underlying": "ETHA", "objective": "-1x",  "asset_class": "Crypto",       "net_assets": 15568264},
    {"ticker": "UXRP",  "fund_name": "Ultra XRP ETF",               "underlying": "XRPF", "objective": "2x",   "asset_class": "Crypto",       "net_assets": 40914811},
    {"ticker": "SLON",  "fund_name": "Ultra Solana ETF",            "underlying": "SOLZ", "objective": "2x",   "asset_class": "Crypto",       "net_assets": 21686033},
    # ── International ──────────────────────────────────────────────────────
    {"ticker": "EET",   "fund_name": "Ultra MSCI Emerging Markets", "underlying": "EEM",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 36585228},
    {"ticker": "EFO",   "fund_name": "Ultra MSCI EAFE",             "underlying": "EFA",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 29430829},
    {"ticker": "XPP",   "fund_name": "Ultra FTSE China 50",         "underlying": "FXI",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 12489547},
    {"ticker": "UPV",   "fund_name": "Ultra FTSE Europe",           "underlying": "EFA",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 11479521},
    {"ticker": "EZJ",   "fund_name": "Ultra MSCI Japan",            "underlying": "EWJ",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 14819872},
    {"ticker": "UBR",   "fund_name": "Ultra MSCI Brazil Capped",    "underlying": "EWZ",  "objective": "2x",   "asset_class": "Equity",       "net_assets": 3763557},
    {"ticker": "EFZ",   "fund_name": "Short MSCI EAFE",             "underlying": "EFA",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 18855197},
    {"ticker": "EUM",   "fund_name": "Short MSCI Emerging Markets", "underlying": "EEM",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 15923750},
    {"ticker": "EEV",   "fund_name": "UltraShort MSCI Emerg Mkts",  "underlying": "EEM",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 14417973},
    {"ticker": "EPV",   "fund_name": "UltraShort FTSE Europe",      "underlying": "EFA",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 13231223},
    {"ticker": "FXP",   "fund_name": "UltraShort FTSE China 50",    "underlying": "FXI",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 7008795},
    {"ticker": "EWV",   "fund_name": "UltraShort MSCI Japan",       "underlying": "EWJ",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 6924121},
    {"ticker": "BZQ",   "fund_name": "UltraShort MSCI Brazil",      "underlying": "EWZ",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 3968648},
    {"ticker": "YXI",   "fund_name": "Short FTSE China 50",         "underlying": "FXI",  "objective": "-1x",  "asset_class": "Equity",       "net_assets": 4430481},
    {"ticker": "EFU",   "fund_name": "UltraShort MSCI EAFE",        "underlying": "EFA",  "objective": "-2x",  "asset_class": "Equity",       "net_assets": 1509715},
    # ── Currency ───────────────────────────────────────────────────────────
    {"ticker": "YCL",   "fund_name": "Ultra Yen",                   "underlying": "FXY",  "objective": "2x",   "asset_class": "Currency",     "net_assets": 47552450},
    {"ticker": "EUO",   "fund_name": "UltraShort Euro",             "underlying": "FXE",  "objective": "-2x",  "asset_class": "Currency",     "net_assets": 36763707},
    {"ticker": "YCS",   "fund_name": "UltraShort Yen",              "underlying": "FXY",  "objective": "-2x",  "asset_class": "Currency",     "net_assets": 31181284},
    {"ticker": "ULE",   "fund_name": "Ultra Euro",                  "underlying": "FXE",  "objective": "2x",   "asset_class": "Currency",     "net_assets": 6381453},
    # ── Single Stock (ProShares) ─────────────────────────────────────────
    {"ticker": "NVDB",  "fund_name": "Ultra NVDA",                  "underlying": "NVDA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 9295145},
    {"ticker": "TSLI",  "fund_name": "Ultra TSLA",                  "underlying": "TSLA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 3621941},
    {"ticker": "PLTA",  "fund_name": "Ultra PLTR",                  "underlying": "PLTR", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 6177453},
    {"ticker": "COIA",  "fund_name": "Ultra COIN",                  "underlying": "COIN", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 2455232},
    {"ticker": "CRCA",  "fund_name": "Ultra CRCL",                  "underlying": "CRCL", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 262223139},
    # ── GraniteShares 2x Long ─────────────────────────────────────────────
    {"ticker": "TSL",   "fund_name": "GS 1.25x Long TSLA",          "underlying": "TSLA", "objective": "1.25x","asset_class": "Single Stock", "net_assets": 42478921},
    {"ticker": "AAPB",  "fund_name": "GS 2x Long AAPL",             "underlying": "AAPL", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 15025117},
    {"ticker": "AMDL",  "fund_name": "GS 2x Long AMD",              "underlying": "AMD",  "objective": "2x",   "asset_class": "Single Stock", "net_assets": 518715230},
    {"ticker": "AMZZ",  "fund_name": "GS 2x Long AMZN",             "underlying": "AMZN", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 45408315},
    {"ticker": "AVGU",  "fund_name": "GS 2x Long AVGO",             "underlying": "AVGO", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 17509277},
    {"ticker": "BABX",  "fund_name": "GS 2x Long BABA",             "underlying": "BABA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 115503138},
    {"ticker": "CONL",  "fund_name": "GS 2x Long COIN",             "underlying": "COIN", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 577152742},
    {"ticker": "CRWL",  "fund_name": "GS 2x Long CRWD",             "underlying": "CRWD", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 40217453},
    {"ticker": "DLLL",  "fund_name": "GS 2x Long DELL",             "underlying": "DELL", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 15066557},
    {"ticker": "GOU",   "fund_name": "GS 2x Long GOOGL",            "underlying": "GOOGL","objective": "2x",   "asset_class": "Single Stock", "net_assets": 5247248},
    {"ticker": "INTW",  "fund_name": "GS 2x Long INTC",             "underlying": "INTC", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 98039329},
    {"ticker": "IONL",  "fund_name": "GS 2x Long IONQ",             "underlying": "IONQ", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 38838206},
    {"ticker": "ISUL",  "fund_name": "GS 2x Long ISRG",             "underlying": "ISRG", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 3114356},
    {"ticker": "LCDL",  "fund_name": "GS 2x Long LCID",             "underlying": "LCID", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 4245352},
    {"ticker": "MRAL",  "fund_name": "GS 2x Long MARA",             "underlying": "MARA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 47468151},
    {"ticker": "FBL",   "fund_name": "GS 2x Long META",             "underlying": "META", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 206132348},
    {"ticker": "MVLL",  "fund_name": "GS 2x Long MRVL",             "underlying": "MRVL", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 54146927},
    {"ticker": "MSFL",  "fund_name": "GS 2x Long MSFT",             "underlying": "MSFT", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 88941711},
    {"ticker": "MSTP",  "fund_name": "GS 2x Long MSTR",             "underlying": "MSTR", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 8387982},
    {"ticker": "MULL",  "fund_name": "GS 2x Long MU",               "underlying": "MU",   "objective": "2x",   "asset_class": "Single Stock", "net_assets": 338745948},
    {"ticker": "NBIL",  "fund_name": "GS 2x Long NBIS",             "underlying": "NBIS", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 63741089},
    {"ticker": "NOWL",  "fund_name": "GS 2x Long NOW",              "underlying": "NOW",  "objective": "2x",   "asset_class": "Single Stock", "net_assets": 35594378},
    {"ticker": "NVDL",  "fund_name": "GS 2x Long NVDA",             "underlying": "NVDA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 3944012102},
    {"ticker": "PDDL",  "fund_name": "GS 2x Long PDD",              "underlying": "PDD",  "objective": "2x",   "asset_class": "Single Stock", "net_assets": 8328465},
    {"ticker": "PTIR",  "fund_name": "GS 2x Long PLTR",             "underlying": "PLTR", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 482729077},
    {"ticker": "QCML",  "fund_name": "GS 2x Long QCOM",             "underlying": "QCOM", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 9627740},
    {"ticker": "RDTL",  "fund_name": "GS 2x Long RDDT",             "underlying": "RDDT", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 47908522},
    {"ticker": "RVNL",  "fund_name": "GS 2x Long RIVN",             "underlying": "RIVN", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 8361030},
    {"ticker": "SMCL",  "fund_name": "GS 2x Long SMCI",             "underlying": "SMCI", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 40933222},
    {"ticker": "TSLR",  "fund_name": "GS 2x Long TSLA",             "underlying": "TSLA", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 144531665},
    {"ticker": "TSMU",  "fund_name": "GS 2x Long TSM",              "underlying": "TSM",  "objective": "2x",   "asset_class": "Single Stock", "net_assets": 36690365},
    {"ticker": "UBRL",  "fund_name": "GS 2x Long Uber",             "underlying": "UBER", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 18709590},
    {"ticker": "VRTL",  "fund_name": "GS 2x Long VRT",              "underlying": "VRT",  "objective": "2x",   "asset_class": "Single Stock", "net_assets": 33892587},
    {"ticker": "BULX",  "fund_name": "GS 2x Long BULL",             "underlying": "BULL", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 879066},
    {"ticker": "ETRL",  "fund_name": "GS 2x Long ETOR",             "underlying": "ETOR", "objective": "2x",   "asset_class": "Single Stock", "net_assets": 1129053},
    # ── GraniteShares 2x Short ────────────────────────────────────────────
    {"ticker": "CONI",  "fund_name": "GS 2x Short COIN",            "underlying": "COIN", "objective": "-2x",  "asset_class": "Single Stock", "net_assets": 12986718},
    {"ticker": "MSDD",  "fund_name": "GS 2x Short MSTR",            "underlying": "MSTR", "objective": "-2x",  "asset_class": "Single Stock", "net_assets": 2204968},
    {"ticker": "NVD",   "fund_name": "GS 2x Short NVDA",            "underlying": "NVDA", "objective": "-2x",  "asset_class": "Single Stock", "net_assets": 84258655},
    # ── Direxion 3x/2x Index & Sector (User Expansion) ─────────────────
    {"ticker": "SOXL",   "fund_name": "Direxion Daily Semiconductor Bull 3X ETF",                      "underlying": "SOXX",   "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "TECL",   "fund_name": "Direxion Daily Technology Bull 3X ETF",                         "underlying": "XLK",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "SPXL",   "fund_name": "Direxion Daily S&P 500 Bull 3X ETF",                            "underlying": "SPY",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "TNA",    "fund_name": "Direxion Daily Small Cap Bull 3X ETF",                          "underlying": "IWM",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "HIBL",   "fund_name": "Direxion Daily S&P 500 High Beta Bull 3X ETF",                  "underlying": "SPHB",   "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "LABU",   "fund_name": "Direxion Daily S&P Biotech Bull 3X ETF",                        "underlying": "XBI",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "MIDU",   "fund_name": "Direxion Daily Mid Cap Bull 3X ETF",                            "underlying": "MDY",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "DPST",   "fund_name": "Direxion Daily Regional Banks Bull 3X ETF",                     "underlying": "KRE",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "DFEN",   "fund_name": "Direxion Daily Aerospace & Defense Bull 3X ETF",                "underlying": "ITA",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "DUSL",   "fund_name": "Direxion Daily Industrials Bull 3X ETF",                        "underlying": "XLI",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "NAIL",   "fund_name": "Direxion Daily Homebuilders & Supplies Bull 3X ETF",            "underlying": "XHB",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "RETL",   "fund_name": "Direxion Daily Retail Bull 3X ETF",                             "underlying": "XRT",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "WANT",   "fund_name": "Direxion Daily Consumer Discretionary Bull 3X ETF",             "underlying": "XLY",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "UTSL",   "fund_name": "Direxion Daily Utilities Bull 3X ETF",                          "underlying": "XLU",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "CURE",   "fund_name": "Direxion Daily Healthcare Bull 3X ETF",                         "underlying": "XLV",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "DRN",    "fund_name": "Direxion Daily Real Estate Bull 3X ETF",                        "underlying": "XLRE",   "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "PILL",   "fund_name": "Direxion Daily Pharmaceutical & Medical Bull 3X ETF",           "underlying": "PPH",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "WEBL",   "fund_name": "Direxion Daily Dow Jones Internet Bull 3X ETF",                 "underlying": "FDN",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "FAS",    "fund_name": "Direxion Daily Financial Bull 3X ETF",                          "underlying": "XLF",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "NUGT",   "fund_name": "Direxion Daily Gold Miners Index Bull 2X ETF",                  "underlying": "GDX",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "JNUG",   "fund_name": "Direxion Daily Junior Gold Miners Idx Bull 2X ETF",             "underlying": "GDXJ",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "EDC",    "fund_name": "Direxion Daily MSCI Emerging Markets Bull 3X ETF",              "underlying": "EEM",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "KORU",   "fund_name": "Direxion Daily MSCI South Korea Bull 3X ETF",                   "underlying": "EWY",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "EURL",   "fund_name": "Direxion Daily FTSE Europe Bull 3X ETF",                        "underlying": "VGK",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "BRZU",   "fund_name": "Direxion Daily MSCI Brazil Bull 2X ETF",                        "underlying": "EWZ",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "MEXX",   "fund_name": "Direxion Daily MSCI Mexico Bull 3X ETF",                        "underlying": "EWW",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "INDL",   "fund_name": "Direxion Daily MSCI India Bull 2X ETF",                         "underlying": "INDA",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "CHAU",   "fund_name": "Direxion Daily CSI 300 China A Share Bull 2X ETF",              "underlying": "ASHR",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "YINN",   "fund_name": "Direxion Daily FTSE China Bull 3X ETF",                         "underlying": "FXI",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "CWEB",   "fund_name": "Direxion Daily CSI China Internet Idx Bull 2X ETF",             "underlying": "KWEB",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "ERX",    "fund_name": "Direxion Daily Energy Bull 2X ETF",                             "underlying": "XLE",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "GUSH",   "fund_name": "Direxion Daily S&P Oil & Gas Exp & Prod Bull 2X ETF",           "underlying": "XOP",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "TPOR",   "fund_name": "Direxion Daily Transportation Bull 3X ETF",                     "underlying": "IYT",    "objective": "3x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "URAA",   "fund_name": "Direxion Daily Uranium Industry Bull 2X ETF",                   "underlying": "URNM",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "GGLL",   "fund_name": "Direxion Daily GOOGL Bull 2X ETF",                              "underlying": "GOOGL",  "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AMUU",   "fund_name": "Direxion Daily AMD Bull 2X ETF",                                "underlying": "AMD",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NVDU",   "fund_name": "Direxion Daily NVDA Bull 2X ETF",                               "underlying": "NVDA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AMZU",   "fund_name": "Direxion Daily AMZN Bull 2X ETF",                               "underlying": "AMZN",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "FNGG",   "fund_name": "Direxion Daily NYSE FANG+ Bull 2X ETF",                         "underlying": "FNGS",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "QQQU",   "fund_name": "Direxion Daily Magnificent 7 Bull 2X ETF",                      "underlying": "MAGS",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "SPUU",   "fund_name": "Direxion Daily S&P 500 Bull 2X ETF",                            "underlying": "SPY",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "MUU",    "fund_name": "Direxion Daily MU Bull 2X ETF",                                 "underlying": "MU",     "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSMX",   "fund_name": "Direxion Daily TSM Bull 2X ETF",                                "underlying": "TSM",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "METU",   "fund_name": "Direxion Daily META Bull 2X ETF",                               "underlying": "META",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AAPU",   "fund_name": "Direxion Daily AAPL Bull 2X ETF",                               "underlying": "AAPL",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "MSFU",   "fund_name": "Direxion Daily MSFT Bull 2X ETF",                               "underlying": "MSFT",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NFXL",   "fund_name": "Direxion Daily NFLX Bull 2X ETF",                               "underlying": "NFLX",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PALU",   "fund_name": "Direxion Daily PANW Bull 2X ETF",                               "underlying": "PANW",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PLTU",   "fund_name": "Direxion Daily PLTR Bull 2X ETF",                               "underlying": "PLTR",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSLL",   "fund_name": "Direxion Daily TSLA Bull 2X ETF",                               "underlying": "TSLA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "XOMX",   "fund_name": "Direxion Daily XOM Bull 2X ETF",                                "underlying": "XOM",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "BOEU",   "fund_name": "Direxion Daily BA Bull 2X ETF",                                 "underlying": "BA",     "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "BRKU",   "fund_name": "Direxion Daily BRKB Bull 2X ETF",                               "underlying": "BRK-B",  "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ELIL",   "fund_name": "Direxion Daily LLY Bull 2X ETF",                                "underlying": "LLY",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AIBU",   "fund_name": "Direxion Daily AI and Big Data Bull 2X ETF",                    "underlying": "ROBT",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "UBOT",   "fund_name": "Direxion Daily Robo AI & Automation Ix Bull 2X ETF",            "underlying": "ROBT",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "NVDX",   "fund_name": "T-REX 2X Long NVIDIA Daily Target ETF",                         "underlying": "NVDA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AAPX",   "fund_name": "T-REX 2X Long Apple Daily Target ETF",                          "underlying": "AAPL",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "MSFX",   "fund_name": "T-REX 2X Long Microsoft Daily Target ETF",                      "underlying": "MSFT",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "GOOX",   "fund_name": "T-REX 2X Long Alphabet Daily Target ETF",                       "underlying": "GOOGL",  "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSLT",   "fund_name": "T-REX 2X Long TESLA Daily Target ETF",                          "underlying": "TSLA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NFLU",   "fund_name": "T-REX 2X Long NFLX Daily Target ETF",                           "underlying": "NFLX",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "MSTU",   "fund_name": "T-REX 2X Long MSTR Daily Target ETF",                           "underlying": "MSTR",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "GMEU",   "fund_name": "T-REX 2X Long GME Daily Target ETF",                            "underlying": "GME",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ROBN",   "fund_name": "T-REX 2X Long HOOD Daily Target ETF",                           "underlying": "HOOD",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "RBLU",   "fund_name": "T-REX 2X Long RBLX Daily Target ETF",                           "underlying": "RBLX",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "SNOU",   "fund_name": "T-REX 2X Long SNOW Daily Target ETF",                           "underlying": "SNOW",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "DJTU",   "fund_name": "T-REX 2X Long DJT Daily Target ETF",                            "underlying": "DJT",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AVGX",   "fund_name": "Defiance Daily Target 2X Long AVGO ETF",                        "underlying": "AVGO",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AVL",    "fund_name": "Direxion Daily AVGO Bull 2X ETF",                               "underlying": "AVGO",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "RKLX",   "fund_name": "Defiance Daily Target 2X Long RKLB ETF",                        "underlying": "RKLB",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NVOX",   "fund_name": "Defiance Daily Target 2X Long NVO ETF",                         "underlying": "NVO",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "IONX",   "fund_name": "Defiance Daily Target 2X Long IONQ ETF",                        "underlying": "IONQ",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "SOFX",   "fund_name": "Defiance Daily Target 2X Long SOFI ETF",                        "underlying": "SOFI",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "RIOX",   "fund_name": "Defiance Daily Target 2X Long RIOT ETF",                        "underlying": "RIOT",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "HOOX",   "fund_name": "Defiance Daily Target 2X Long HOOD ETF",                        "underlying": "HOOD",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "SMCX",   "fund_name": "Defiance Daily Target 2X Long SMCI ETF",                        "underlying": "SMCI",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "MSTX",   "fund_name": "Defiance Daily Target 2X Long MSTR ETF",                        "underlying": "MSTR",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "LLYX",   "fund_name": "Defiance Daily Target 2X Long LLY ETF",                         "underlying": "LLY",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "HIMZ",   "fund_name": "Defiance Daily Target 2X Long HIMS ETF",                        "underlying": "HIMS",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ORCX",   "fund_name": "Defiance Daily Target 2X Long ORCL ETF",                        "underlying": "ORCL",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "RGTX",   "fund_name": "Defiance Daily Target 2X Long RGTI ETF",                        "underlying": "RGTI",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ARMG",   "fund_name": "Leverage Shares 2X Long ARM Daily ETF",                         "underlying": "ARM",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSMG",   "fund_name": "Leverage Shares 2X Long TSM Daily ETF",                         "underlying": "TSM",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AMDG",   "fund_name": "Leverage Shares 2X Long AMD Daily ETF",                         "underlying": "AMD",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ASMG",   "fund_name": "Leverage Shares 2X Long ASML Daily ETF",                        "underlying": "ASML",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NVDG",   "fund_name": "Leverage Shares 2X Long NVDA Daily ETF",                        "underlying": "NVDA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "XYZG",   "fund_name": "Leverage Shares 2X Long XYZ Daily ETF",                         "underlying": "XYZ",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "HOOG",   "fund_name": "Leverage Shares 2X Long HOOD Daily ETF",                        "underlying": "HOOD",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PANG",   "fund_name": "Leverage Shares 2X Long PANW Daily ETF",                        "underlying": "PANW",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "COIG",   "fund_name": "Leverage Shares 2X Long COIN Daily ETF",                        "underlying": "COIN",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSLG",   "fund_name": "Leverage Shares 2X Long TSLA Daily ETF",                        "underlying": "TSLA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PYPG",   "fund_name": "Leverage Shares 2X Long PYPL Daily ETF",                        "underlying": "PYPL",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PLTG",   "fund_name": "Leverage Shares 2X Long PLTR Daily ETF",                        "underlying": "PLTR",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "ADBG",   "fund_name": "Leverage Shares 2X Long ADBE Daily ETF",                        "underlying": "ADBE",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "CRMG",   "fund_name": "Leverage Shares 2X Long CRM Daily ETF",                         "underlying": "CRM",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "NVDW",   "fund_name": "Roundhill NVDA WeeklyPay ETF",                                  "underlying": "NVDA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "AAPW",   "fund_name": "Roundhill AAPL WeeklyPay ETF",                                  "underlying": "AAPL",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSLW",   "fund_name": "Roundhill TSLA WeeklyPay ETF",                                  "underlying": "TSLA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "COIW",   "fund_name": "Roundhill COIN WeeklyPay ETF",                                  "underlying": "COIN",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "PLTW",   "fund_name": "Roundhill PLTR WeeklyPay ETF",                                  "underlying": "PLTR",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "MAGX",   "fund_name": "Roundhill Daily 2X Long Magnificent Seven ETF",                 "underlying": "MAGS",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "MQQQ",   "fund_name": "Tradr 2X Long Innovation 100 Monthly ETF",                      "underlying": "QQQ",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "QQQP",   "fund_name": "Tradr 2X Long Innovation 100 Quarterly ETF",                    "underlying": "QQQ",    "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "TARK",   "fund_name": "Tradr 2X Long Innovation ETF",                                  "underlying": "ARKK",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "APPX",   "fund_name": "Tradr 2X Long APP Daily ETF",                                   "underlying": "APP",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "QBTX",   "fund_name": "Tradr 2X Long QBTS Daily ETF",                                  "underlying": "QBTS",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "TSYY",   "fund_name": "GraniteShares YieldBOOST TSLA ETF",                             "underlying": "TSLA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "KBAB",   "fund_name": "KraneShares 2x Long BABA Daily ETF",                            "underlying": "BABA",   "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "KPDD",   "fund_name": "KraneShares 2x Long PDD Daily ETF",                             "underlying": "PDD",    "objective": "2x",    "asset_class": "Single Stock", "net_assets": 0},
    {"ticker": "WXET",   "fund_name": "Teucrium 2x Daily Wheat ETF",                                   "underlying": "WEAT",   "objective": "2x",    "asset_class": "Commodity", "net_assets": 0},
    {"ticker": "CXRN",   "fund_name": "Teucrium 2x Daily Corn ETF",                                    "underlying": "CORN",   "objective": "2x",    "asset_class": "Commodity", "net_assets": 0},
    {"ticker": "UVXY",   "fund_name": "ProShares Ultra VIX Short-Term Futures ETF",                    "underlying": "VIXY",   "objective": "2x",    "asset_class": "Volatility", "net_assets": 0},
    {"ticker": "MSOX",   "fund_name": "AdvisorShares MSOS Daily Leveraged ETF",                        "underlying": "MSOS",   "objective": "2x",    "asset_class": "Equity", "net_assets": 0},
    {"ticker": "TSDD",  "fund_name": "GS 2x Short TSLA",            "underlying": "TSLA", "objective": "-2x",  "asset_class": "Single Stock", "net_assets": 49633910},
]

# Build a lookup dict: underlying_ticker -> list of lev ETFs that use it
_UNDERLYING_TO_LEV: Dict[str, List[Dict]] = {}
for etf in LEV_ETF_LIST:
    und = etf["underlying"]
    if und not in _UNDERLYING_TO_LEV:
        _UNDERLYING_TO_LEV[und] = []
    _UNDERLYING_TO_LEV[und].append(etf)


def _compute_signals(row: Dict[str, Any]) -> Dict[str, bool]:
    """Compute scanner signal flags from an underlying screen_data row."""
    close = row.get("Close") or 0
    sma_5 = row.get("SMA_5") or 0
    sma_9 = row.get("SMA_9") or 0
    sma_10 = row.get("SMA_10") or 0
    sma_20 = row.get("SMA_20") or 0
    sma_21 = row.get("SMA_21") or 0
    sma_50 = row.get("SMA_50") or 0
    rvol = row.get("RVOL") or 0
    adr_20 = row.get("ADR_20") or 0
    mom_3m = row.get("Momentum_3M")
    pct_high = row.get("Pct_From_52W_High")
    tight_setup = bool(row.get("Tight_Setup"))
    near_res = bool(row.get("Near_Horizontal_Resistance"))
    vcp = bool(row.get("VCP_Approximation"))

    def near(price, sma, pct=0.02):
        return sma > 0 and abs(price - sma) / sma <= pct

    pullback_5 = near(close, sma_5) if sma_5 else False
    pullback_10 = near(close, sma_10) if sma_10 else False
    pullback_21 = near(close, sma_21) if sma_21 else False
    pullback_50 = near(close, sma_50) if sma_50 else False

    htf = (
        mom_3m is not None and mom_3m > 0.90
        and pct_high is not None and -25 <= pct_high <= -2
        and rvol < 0.85
        and adr_20 >= 4.0
    )

    minervini_cheat = (
        vcp
        and rvol < 0.85
        and (near(close, sma_10, 0.03) or near(close, sma_20, 0.03))
    )

    return {
        "pullback_5": pullback_5,
        "pullback_10": pullback_10,
        "pullback_21": pullback_21,
        "pullback_50": pullback_50,
        "htf": htf,
        "tight_setup": tight_setup,
        "horizontal_resistance": near_res,
        "minervini_cheat": minervini_cheat,
    }


@router.get("/list", summary="Get full leveraged ETF list (no scan data)")
def get_lev_etf_list():
    """Returns the static list of all leveraged ETFs with metadata."""
    return {"count": len(LEV_ETF_LIST), "data": LEV_ETF_LIST}


@router.get("/underlying-map", summary="Get best long leveraged ETF per underlying ticker")
def get_underlying_map():
    """
    Returns a lightweight map: underlying_ticker → best matching long leveraged ETF.
    For each underlying, picks the long ETF with highest objective (prefer 2x > 1.25x),
    then by largest net_assets as tiebreaker.
    Used by the frontend to show leveraged ETF info on watchlist views.
    """
    def _parse_objective(obj_str: str) -> float:
        """Parse '2x', '3x', '-2x', '1.25x' → numeric float."""
        try:
            return float(obj_str.replace("x", ""))
        except (ValueError, TypeError):
            return 0.0

    result: Dict[str, Dict[str, Any]] = {}
    for und_ticker, etfs in _UNDERLYING_TO_LEV.items():
        # Filter to long-only ETFs (positive objective)
        long_etfs = [e for e in etfs if _parse_objective(e["objective"]) > 0]
        if not long_etfs:
            continue
        # Sort: highest objective first, then largest net_assets
        long_etfs.sort(key=lambda e: (-_parse_objective(e["objective"]), -(e.get("net_assets") or 0)))
        best = long_etfs[0]
        result[und_ticker] = {
            "ticker": best["ticker"],
            "fund_name": best["fund_name"],
            "objective": best["objective"],
        }
    return result


@router.get("/scan", summary="Get leveraged ETFs with scanner signals from underlying data")
def scan_lev_etfs():
    """
    Returns all leveraged ETFs enriched with scanner signals.
    Scanner signals (Stage, pullbacks, HTF, etc.) are computed from the
    UNDERLYING ticker's data in screen_data, not the leveraged ETF itself.
    """
    # Collect all unique underlying tickers we need
    underlying_tickers = list(_UNDERLYING_TO_LEV.keys())

    if not underlying_tickers:
        return {"count": 0, "data": []}

    # Batch fetch all underlying rows in one SQL query
    placeholders = ", ".join(["?" for _ in underlying_tickers])
    sql = f"""
        SELECT Ticker, Close, Stage, SMA_5, SMA_9, SMA_10, SMA_20, SMA_21, SMA_50,
               RVOL, ADR_20, Momentum_3M, Pct_From_52W_High, In_Stage_2,
               Tight_Setup, Near_Horizontal_Resistance, VCP_Approximation,
               RS_Rating, Momentum_1D, Momentum_1M
        FROM screen_data
        WHERE Ticker IN ({placeholders})
    """
    rows = fetch_all(sql, tuple(underlying_tickers))
    underlying_data: Dict[str, Dict] = {r["Ticker"]: dict(r) for r in rows}

    # Build enriched results
    results = []
    for etf in LEV_ETF_LIST:
        und_ticker = etf["underlying"]
        und_row = underlying_data.get(und_ticker, {})

        signals = _compute_signals(und_row) if und_row else {
            "pullback_5": False, "pullback_10": False, "pullback_21": False,
            "pullback_50": False, "htf": False, "tight_setup": False,
            "horizontal_resistance": False, "minervini_cheat": False,
        }

        results.append({
            "ticker": etf["ticker"],
            "fund_name": etf["fund_name"],
            "underlying": und_ticker,
            "objective": etf["objective"],
            "asset_class": etf["asset_class"],
            "net_assets": etf["net_assets"],
            # Underlying data fields
            "stage": und_row.get("Stage"),
            "close": und_row.get("Close"),
            "rs_rating": und_row.get("RS_Rating"),
            "rvol": und_row.get("RVOL"),
            "momentum_1d": und_row.get("Momentum_1D"),
            "momentum_1m": und_row.get("Momentum_1M"),
            "pct_from_52w_high": und_row.get("Pct_From_52W_High"),
            "adr_20": und_row.get("ADR_20"),
            "in_stage_2": bool(und_row.get("In_Stage_2")),
            # Scanner signals (all from underlying)
            **signals,
            # Active setup count for sorting
            "setup_count": sum(1 for v in signals.values() if v),
        })

    # Sort by setup_count desc, then by net_assets desc
    results.sort(key=lambda x: (-x["setup_count"], -(x["net_assets"] or 0)))

    return {"count": len(results), "data": results}


# ---------------------------------------------------------------------------
# EMA Structure Screeners — uses the leveraged ETF's OWN price data
# ---------------------------------------------------------------------------
_LEV_TICKERS = [etf["ticker"] for etf in LEV_ETF_LIST]
_LEV_META = {etf["ticker"]: etf for etf in LEV_ETF_LIST}


def _scan_ema_structure(period: int) -> Dict[str, Any]:
    """
    Shared logic for 8 EMA and 21 EMA structure screeners.

    Filter: EMA_Low(period) - ATR(14) <= Close <= EMA_High(period) + ATR(14)
    Structure Trend:
        Rising  = all 3 MAs (high/close/low) were rising (computed during ingest)
        Falling = all 3 MAs were falling
        Neutral = mixed

    Note: Since we only store the *latest* EMA values (not the previous bar),
    we approximate trend by comparing EMA_Close vs SMA_5 (short-term momentum proxy).
    A truly rising structure will have EMA_Close > SMA_5 when accelerating.
    But a better approach: compare close position within the band.
    Actually — we DO have the latest bar's EMA values. To get previous bar's EMAs
    we'd need OHLCV history. Instead, we use a practical approximation:
      - Rising:  close > ema_close AND ema_close > sma_21  (upward structure)
      - Falling: close < ema_close AND ema_close < sma_21  (downward structure)
      - Neutral: everything else
    """
    if not _LEV_TICKERS:
        return {"count": 0, "data": []}

    placeholders = ", ".join(["?" for _ in _LEV_TICKERS])

    if period == 8:
        ema_high_col = "EMA_8_High"
        ema_close_col = "EMA_8_Close"
        ema_low_col = "EMA_8_Low"
    else:
        ema_high_col = "EMA_21_High"
        ema_close_col = "EMA_21"  # EMA_21 of Close (the original column)
        ema_low_col = "EMA_21_Low"

    # Use aliases to normalize column names across SQLite (preserves case) and
    # Postgres (lowercases). After _map_row, unmapped keys keep the alias as-is.
    sql = f"""
        SELECT Ticker, Close, Stage,
               {ema_high_col} AS ema_h, {ema_close_col} AS ema_c, {ema_low_col} AS ema_l,
               ATR_14 AS atr14, ADR_20, SMA_21, SMA_50,
               Momentum_1D, RS_Rating, Pct_From_52W_High, RVOL
        FROM screen_data
        WHERE Ticker IN ({placeholders})
          AND {ema_high_col} IS NOT NULL
          AND {ema_low_col} IS NOT NULL
          AND ATR_14 IS NOT NULL
          AND ATR_14 > 0
          AND Close IS NOT NULL
    """
    rows = fetch_all(sql, tuple(_LEV_TICKERS))

    results = []
    for r in rows:
        row = dict(r)
        ticker = row.get("Ticker") or row.get("ticker")
        close = row.get("Close") or row.get("close")
        ema_high = row.get("ema_h")
        ema_close = row.get("ema_c")
        ema_low = row.get("ema_l")
        atr = row.get("atr14")
        sma_21 = row.get("SMA_21") or row.get("sma_21") or 0
        sma_50 = row.get("SMA_50") or row.get("sma_50") or 0

        upper_band = ema_high + atr
        lower_band = ema_low - atr

        # Filter: close must be within the band
        if close > upper_band or close < lower_band:
            continue

        # ATR distance from MA close
        atr_distance = (close - ema_close) / atr if atr else 0

        # Structure trend approximation
        if close > ema_close and ema_close > sma_21:
            trend = "Rising"
        elif close < ema_close and ema_close < sma_21:
            trend = "Falling"
        else:
            trend = "Neutral"

        meta = _LEV_META.get(ticker, {})

        results.append({
            "ticker": ticker,
            "fund_name": meta.get("fund_name", ""),
            "underlying": meta.get("underlying", ""),
            "objective": meta.get("objective", ""),
            "asset_class": meta.get("asset_class", ""),
            "close": round(close, 2),
            "ema_high": round(ema_high, 2),
            "ema_close": round(ema_close, 2),
            "ema_low": round(ema_low, 2),
            "atr_14": round(atr, 2),
            "atr_distance": round(atr_distance, 2),
            "upper_band": round(upper_band, 2),
            "lower_band": round(lower_band, 2),
            "structure_trend": trend,
            "stage": row.get("Stage"),
            "adr_20": round(row.get("ADR_20") or 0, 2),
            "momentum_1d": row.get("Momentum_1D"),
            "rs_rating": row.get("RS_Rating"),
            "pct_from_52w_high": row.get("Pct_From_52W_High"),
            "rvol": row.get("RVOL"),
        })

    # Sort by absolute ATR distance (closest to MA first)
    results.sort(key=lambda x: abs(x["atr_distance"]))

    return {"count": len(results), "data": results}


@router.get("/scan-8ema", summary="Lev ETFs near 8 EMA structure (±1 ATR)")
def scan_8ema():
    """
    Returns leveraged ETFs whose close is within the 8 EMA structure band.
    Band = [EMA(Low, 8) - ATR(14), EMA(High, 8) + ATR(14)]
    Uses the leveraged ETF's own price data (not underlying).
    """
    return _scan_ema_structure(8)


@router.get("/scan-21ema", summary="Lev ETFs near 21 EMA structure (±1 ATR)")
def scan_21ema():
    """
    Returns leveraged ETFs whose close is within the 21 EMA structure band.
    Band = [EMA(Low, 21) - ATR(14), EMA(High, 21) + ATR(14)]
    Uses the leveraged ETF's own price data (not underlying).
    """
    return _scan_ema_structure(21)
