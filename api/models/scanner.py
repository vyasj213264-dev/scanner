"""
Pydantic response models for the TradersChart API.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic import ConfigDict
from pydantic.alias_generators import to_pascal


class StockResult(BaseModel):
    """
    A single stock record returned by any scanner.

    Fields use lowercase snake_case in JSON output (for the frontend JS),
    but accept uppercase column names from SQLite via validation_alias.
    """
    model_config = ConfigDict(populate_by_name=True)
    ticker: str = Field(..., validation_alias="Ticker")
    date: Optional[str] = Field(None, validation_alias="Date")
    close: Optional[float] = Field(None, validation_alias="Close")
    volume: Optional[float] = Field(None, validation_alias="Volume")
    rs_rating: Optional[float] = Field(None, validation_alias="RS_Rating")
    rvol: Optional[float] = Field(None, validation_alias="RVOL")
    adr_20: Optional[float] = Field(None, validation_alias="ADR_20")
    pct_from_52w_high: Optional[float] = Field(None, validation_alias="Pct_From_52W_High")
    sma_5: Optional[float] = Field(None, validation_alias="SMA_5")
    sma_9: Optional[float] = Field(None, validation_alias="SMA_9")
    sma_10: Optional[float] = Field(None, validation_alias="SMA_10")
    sma_20: Optional[float] = Field(None, validation_alias="SMA_20")
    sma_21: Optional[float] = Field(None, validation_alias="SMA_21")
    sma_50: Optional[float] = Field(None, validation_alias="SMA_50")
    sma_200: Optional[float] = Field(None, validation_alias="SMA_200")
    momentum_1d: Optional[float] = Field(None, validation_alias="Momentum_1D")
    momentum_1w: Optional[float] = Field(None, validation_alias="Momentum_1W")
    momentum_1m: Optional[float] = Field(None, validation_alias="Momentum_1M")
    momentum_3m: Optional[float] = Field(None, validation_alias="Momentum_3M")
    momentum_6m: Optional[float] = Field(None, validation_alias="Momentum_6M")
    momentum_1y: Optional[float] = Field(None, validation_alias="Momentum_1Y")
    in_stage_2: Optional[bool] = Field(None, validation_alias="In_Stage_2")
    tight_setup: Optional[bool] = Field(None, validation_alias="Tight_Setup")
    near_horizontal_resistance: Optional[bool] = Field(None, validation_alias="Near_Horizontal_Resistance")
    inside_bar: Optional[bool] = Field(None, validation_alias="Inside_Bar")
    golden_crossover: Optional[bool] = Field(None, validation_alias="Golden_Crossover")
    gap_up: Optional[bool] = Field(None, validation_alias="Gap_Up")
    gap_down: Optional[bool] = Field(None, validation_alias="Gap_Down")
    vcp_approximation: Optional[bool] = Field(None, validation_alias="VCP_Approximation")
    market_cap: Optional[float] = Field(None, validation_alias="Market_Cap")
    sector: Optional[str] = Field(None, validation_alias="Sector")
    industry: Optional[str] = Field(None, validation_alias="Industry")
    sector_rank_1d: Optional[int] = Field(None, validation_alias="Sector_Rank_1D")
    sector_rank_1w: Optional[int] = Field(None, validation_alias="Sector_Rank_1W")
    sector_rank_1m: Optional[int] = Field(None, validation_alias="Sector_Rank_1M")
    sector_rank_3m: Optional[int] = Field(None, validation_alias="Sector_Rank_3M")
    sector_rank_6m: Optional[int] = Field(None, validation_alias="Sector_Rank_6M")
    industry_rank_1d: Optional[int] = Field(None, validation_alias="Industry_Rank_1D")
    industry_rank_1w: Optional[int] = Field(None, validation_alias="Industry_Rank_1W")
    industry_rank_1m: Optional[int] = Field(None, validation_alias="Industry_Rank_1M")
    industry_rank_3m: Optional[int] = Field(None, validation_alias="Industry_Rank_3M")
    industry_rank_6m: Optional[int] = Field(None, validation_alias="Industry_Rank_6M")
    stage: Optional[int] = Field(None, validation_alias="Stage")
    peg_ratio: Optional[float] = Field(None, validation_alias="peg_ratio")
    revenue_growth_3y: Optional[float] = Field(None, validation_alias="revenue_growth_3y")

    # Serialize with field names (lowercase snake_case), NOT validation aliases
    model_config = ConfigDict(populate_by_name=True)


class ScanResponse(BaseModel):
    """Standard envelope for all scan results."""
    scanner: str
    label: str
    category: str
    count: int
    total_universe: int
    as_of_date: Optional[str]
    data: List[StockResult]


class ScannerMeta(BaseModel):
    """Metadata for a single scanner, used in the catalogue endpoint."""
    id: str
    label: str
    description: str
    category: str


class ScannerCatalogueResponse(BaseModel):
    """Full catalogue of available scanners, grouped by category."""
    scanners: List[ScannerMeta]


class UniverseStockResult(BaseModel):
    """
    Lightweight model for the full universe table.
    Excludes technical indicator booleans to keep the payload size under 200kb for 3000 rows.
    """
    ticker: str = Field(..., validation_alias="Ticker")
    close: Optional[float] = Field(None, validation_alias="Close")
    sector: Optional[str] = Field(None, validation_alias="Sector")
    industry: Optional[str] = Field(None, validation_alias="Industry")
    market_cap: Optional[float] = Field(None, validation_alias="Market_Cap")
    adr_20: Optional[float] = Field(None, validation_alias="ADR_20")
    rvol: Optional[float] = Field(None, validation_alias="RVOL")
    pct_from_52w_high: Optional[float] = Field(None, validation_alias="Pct_From_52W_High")
    peg_ratio: Optional[float] = Field(None, validation_alias="peg_ratio")
    revenue_growth_3y: Optional[float] = Field(None, validation_alias="revenue_growth_3y")
    rs_rating: Optional[float] = Field(None, validation_alias="RS_Rating")
    stage: Optional[int] = Field(None, validation_alias="Stage")
    momentum_1d: Optional[float] = Field(None, validation_alias="Momentum_1D")
    momentum_1w: Optional[float] = Field(None, validation_alias="Momentum_1W")
    momentum_1m: Optional[float] = Field(None, validation_alias="Momentum_1M")
    momentum_3m: Optional[float] = Field(None, validation_alias="Momentum_3M")
    momentum_6m: Optional[float] = Field(None, validation_alias="Momentum_6M")
    momentum_1y: Optional[float] = Field(None, validation_alias="Momentum_1Y")
    sector_rank_1d: Optional[int] = Field(None, validation_alias="Sector_Rank_1D")
    sector_rank_1w: Optional[int] = Field(None, validation_alias="Sector_Rank_1W")
    sector_rank_1m: Optional[int] = Field(None, validation_alias="Sector_Rank_1M")
    sector_rank_3m: Optional[int] = Field(None, validation_alias="Sector_Rank_3M")
    sector_rank_6m: Optional[int] = Field(None, validation_alias="Sector_Rank_6M")
    industry_rank_1d: Optional[int] = Field(None, validation_alias="Industry_Rank_1D")
    industry_rank_1w: Optional[int] = Field(None, validation_alias="Industry_Rank_1W")
    industry_rank_1m: Optional[int] = Field(None, validation_alias="Industry_Rank_1M")
    industry_rank_3m: Optional[int] = Field(None, validation_alias="Industry_Rank_3M")
    industry_rank_6m: Optional[int] = Field(None, validation_alias="Industry_Rank_6M")
    
    model_config = ConfigDict(populate_by_name=True)


class UniverseResponse(BaseModel):
    """Response envelope for the full universe performance view."""
    total_universe: int
    as_of_date: Optional[str]
    data: List[UniverseStockResult]


class HealthResponse(BaseModel):
    """System health check response."""
    status: str
    db_ok: bool
    universe_size: int
    last_updated: Optional[str]
    version: str
