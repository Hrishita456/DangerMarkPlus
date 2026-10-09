import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.replay import router
from app.api.consequences import router as consequences_router

app = FastAPI(title="DANGER MARK+ Demo Replay", version="0.1.0",
              description="Synthetic replay and separate assumption-labelled flood consequences. Not operationally validated.")
origins = os.getenv("CORS_ORIGINS", ",".join([
    "http://localhost:8443", "http://127.0.0.1:8443",
    "http://localhost:8444", "http://127.0.0.1:8444",
])).split(",")
app.add_middleware(CORSMiddleware, allow_origins=[value.strip() for value in origins if value.strip()],
                   allow_methods=["GET", "POST"], allow_headers=["Accept", "Content-Type"], allow_credentials=False)
app.include_router(router)
app.include_router(consequences_router)
