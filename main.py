"""
StockScans API — application entry point.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.config import APP_DESCRIPTION, APP_TITLE, APP_VERSION, CORS_ORIGINS
from api.routers import health, scanner


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀  {APP_TITLE} v{APP_VERSION} — starting up")
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


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse("index.html")
