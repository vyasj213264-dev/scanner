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
