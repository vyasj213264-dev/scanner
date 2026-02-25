"""
Pydantic response models for the StockScans API.
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
    ticker: str = Field(..., validation_alias="Ticker")
    date: Optional[str] = Field(None, validation_alias="Date")
    close: Optional[float] = Field(None, validation_alias="Close")
    volume: Optional[float] = Field(None, validation_alias="Volume")
    rs_rating: Optional[float] = Field(None, validation_alias="RS_Rating")
    rvol: Optional[float] = Field(None, validation_alias="RVOL")
    adr_20: Optional[float] = Field(None, validation_alias="ADR_20")
    pct_from_52w_high: Optional[float] = Field(None, validation_alias="Pct_From_52W_High")
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
    momentum_1d: Optional[float] = Field(None, validation_alias="Momentum_1D")
    momentum_1w: Optional[float] = Field(None, validation_alias="Momentum_1W")
    momentum_1m: Optional[float] = Field(None, validation_alias="Momentum_1M")
    momentum_3m: Optional[float] = Field(None, validation_alias="Momentum_3M")
    momentum_6m: Optional[float] = Field(None, validation_alias="Momentum_6M")
    momentum_1y: Optional[float] = Field(None, validation_alias="Momentum_1Y")
    
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
