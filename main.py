"""
TradersChart API — application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.config import APP_DESCRIPTION, APP_TITLE, APP_VERSION, CORS_ORIGINS
from api.routers import health, scanner, themes, auth, watchlists, analytics
from api.routers import breadth
from api.routers import screener
from api.services.auth_service import init_user_tables
from api.routers.screener import init_screener_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀  {APP_TITLE} v{APP_VERSION} — starting up")
    init_user_tables()
    init_screener_tables()
    yield
    print(f"🛑  {APP_TITLE} — shutting down")


app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(scanner.router)
app.include_router(themes.router)
app.include_router(auth.router)
app.include_router(watchlists.router)
app.include_router(analytics.router)
app.include_router(breadth.router)
app.include_router(screener.router)


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("index.html")

@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    return FileResponse("manifest.json", media_type="application/json")

@app.get("/sw.js", include_in_schema=False)
def serve_sw():
    return FileResponse("sw.js", media_type="application/javascript")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
