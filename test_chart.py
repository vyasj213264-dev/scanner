import asyncio
from api.database import get_db
from api.routers.chart import get_chart_data

async def test():
    try:
        data = await get_chart_data("AAPL")
        print(f"Got {len(data)} rows for AAPL")
        if data:
            print("First row:", data[0])
            print("Last row:", data[-1])
            
        proxy = await get_chart_data("(AAPL+MSFT)/2")
        print(f"\nGot {len(proxy)} rows for Proxy")
        if proxy:
            print("First proxy row:", proxy[0])
            print("Last proxy row:", proxy[-1])
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
