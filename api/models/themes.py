from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field

class ThemeRankRecord(BaseModel):
    """
    A single sector or industry ranking record.
    Includes absolute rank and rank momentum compared to the previous day.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    category: str = Field(..., validation_alias="Category")
    name: str = Field(..., validation_alias="Name")
    stock_count: int = Field(..., validation_alias="Stock_Count")
    
    # Absolute Current Ranks
    rank_1d: int = Field(..., validation_alias="Rank_1D")
    rank_1w: int = Field(..., validation_alias="Rank_1W")
    rank_1m: int = Field(..., validation_alias="Rank_1M")
    rank_3m: int = Field(..., validation_alias="Rank_3M")
    rank_6m: int = Field(..., validation_alias="Rank_6M")
    rank_1y: int = Field(..., validation_alias="Rank_1Y")
    
    # Rank Changes (Positive = Better rotation)
    change_1d: Optional[int] = None
    change_1w: Optional[int] = None
    change_1m: Optional[int] = None
    change_3m: Optional[int] = None
    change_6m: Optional[int] = None
    change_1y: Optional[int] = None

class ThemeResponse(BaseModel):
    """Standard envelope for the thematic groupings."""
    as_of_date: str
    data: List[ThemeRankRecord]
    sector_industry_map: Dict[str, List[str]] = {}
