from pydantic import BaseModel, Field, ConfigDict

class TestModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    ticker: str = Field(..., validation_alias="Ticker")
    rs_rating: float = Field(None, validation_alias="RS_Rating")

data2 = {"ticker": "AAPL", "rs_rating": 99.5}
obj2 = TestModel.model_validate(data2)
print("Test 2:", obj2)
