import os
import datetime
import uuid
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

POSTGRES_USER = os.getenv("POSTGRES_USER", "ledgerguard")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ledgerguard_pass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ledgerguard")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Default to localhost for local dev if not set
DATABASE_URL = os.environ.get("POSTGRES_URI", f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_run_id = Column(String, index=True)
    agent_type = Column(String)
    action_description = Column(String)
    tx_hash = Column(String, nullable=True)
    result = Column(JSON)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Create the tables if they don't exist
Base.metadata.create_all(bind=engine)

def get_db():
    """Returns a new DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
