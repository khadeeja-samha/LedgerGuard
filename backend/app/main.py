from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import contracts
from app.api import audit

app = FastAPI(title="Ledgerguard Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])


@app.get("/")
def root():
    return {"message": "Ledgerguard API is running"}
