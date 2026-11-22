from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import auth, incidents, positions, rounds, shifts, sites


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="VigiRonde API",
    version="0.1.0",
    description=(
        "Gestion d'agents de sécurité : vacations géolocalisées, rondes à points de contrôle, "
        "rapports de ronde avec trajet GPS, incidents avec photos."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # à restreindre en production (phase 5)
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, sites.router, shifts.router, rounds.router, positions.router, incidents.router):
    app.include_router(r)


@app.get("/health", tags=["système"])
def health():
    return {"status": "ok", "service": "vigironde-api"}
