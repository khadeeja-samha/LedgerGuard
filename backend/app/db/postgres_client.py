import os
import datetime
import uuid
from sqlalchemy import create_engine, Column, String, JSON, DateTime, ForeignKey, Integer, inspect, text
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

class AuditRun(Base):
    __tablename__ = "audit_runs"

    id = Column(String, primary_key=True)
    contract_id = Column(String, index=True, nullable=False)
    status = Column(String, nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_run_id = Column(String, ForeignKey("audit_runs.id"), nullable=False, index=True)
    agent_type = Column(String)
    action_description = Column(String)
    tx_hash = Column(String, nullable=True)
    result = Column(JSON)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Finding(Base):
    __tablename__ = "findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    audit_run_id = Column(String, ForeignKey("audit_runs.id"), nullable=False, index=True)
    function_name = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
    risk_score = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    attack_type = Column(String, nullable=False)

# Check if audit_runs exists, if not migrate
inspector = inspect(engine)
if not inspector.has_table("audit_runs"):
    # 1. Create audit_runs and findings first
    Base.metadata.create_all(bind=engine, tables=[AuditRun.__table__, Finding.__table__])
    
    # 2. Backfill existing audit_runs
    if inspector.has_table("agent_actions"):
        with engine.begin() as conn:
            # Query existing run_ids and metadata
            result = conn.execute(text("""
                SELECT 
                    audit_run_id,
                    MIN(timestamp) as started_at,
                    MAX(timestamp) as completed_at,
                    MAX(CASE WHEN agent_type = 'attacker_agent' THEN (result->>'contract_id') ELSE NULL END) as contract_id
                FROM agent_actions
                WHERE audit_run_id IS NOT NULL
                GROUP BY audit_run_id
            """))
            for row in result:
                cid = row.contract_id or "unknown_migrated_from_week3"
                conn.execute(
                    text("""
                        INSERT INTO audit_runs (id, contract_id, status, started_at, completed_at)
                        VALUES (:id, :cid, :status, :started_at, :completed_at)
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "id": row.audit_run_id,
                        "cid": cid,
                        "status": "completed",
                        "started_at": row.started_at,
                        "completed_at": row.completed_at
                    }
                )
            
            # 3. Apply ALTER TABLE to add FK constraint
            conn.execute(text("""
                ALTER TABLE agent_actions 
                ADD CONSTRAINT fk_agent_actions_audit_runs 
                FOREIGN KEY (audit_run_id) REFERENCES audit_runs(id)
            """))

# Create the remaining tables (agent_actions) if they don't exist
Base.metadata.create_all(bind=engine)

def get_db():
    """Returns a new DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

