import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.replay import router

app = FastAPI(title="DANGER MARK+ Demo Replay", version="0.1.0",
              description="Synthetic demo data only. No real flood modelling or message delivery.")
origins = os.getenv("CORS_ORIGINS", ",".join([
    "http://localhost:8443", "http://127.0.0.1:8443",
    "http://localhost:8444", "http://127.0.0.1:8444",
])).split(",")
app.add_middleware(CORSMiddleware, allow_origins=[value.strip() for value in origins if value.strip()],
                   allow_methods=["GET"], allow_headers=["Accept"], allow_credentials=False)
app.include_router(router)
