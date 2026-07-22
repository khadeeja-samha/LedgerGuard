import datetime
import hashlib
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.neo4j_client import NeoClient
from app.db.postgres_client import get_db, AgentAction, AuditRun, Finding
from app.models.schemas import UploadRequest
from app.parser.solidity_parser import parse_solidity, SolidityParseError
from app.parser.graph_builder import build_graph
from blockchain.deploy_interface import deploy_contract
from app.agents.orchestrator import run_audit_agents
from app.utils import compute_contract_id
import threading
from fastapi import BackgroundTasks

pipeline_lock = threading.Lock()

logger = logging.getLogger(__name__)
router = APIRouter()

_neo_client = NeoClient()


@router.get("/{contract_id}/graph")
def get_audit_graph(contract_id: str):
    """Return the persisted graph for a given contract_id."""
    graph = _neo_client.read_graph(contract_id)
    return graph


@router.get("/{audit_run_id}/findings")
def get_audit_findings(audit_run_id: str, db: Session = Depends(get_db)):
    """Return the LLM-generated findings for a given audit_run_id."""
    findings = db.query(Finding).filter(Finding.audit_run_id == audit_run_id).all()
    return [
        {
            "id": f.id,
            "function_name": f.function_name,
            "risk_level": f.risk_level,
            "risk_score": f.risk_score,
            "description": f.description,
            "attack_type": f.attack_type
        }
        for f in findings
    ]


@router.get("/{audit_run_id}/status")
def get_audit_status(audit_run_id: str, db: Session = Depends(get_db)):
    """Return the status of a specific audit run."""
    audit_run = db.query(AuditRun).filter(AuditRun.id == audit_run_id).first()
    if not audit_run:
        raise HTTPException(status_code=404, detail="Audit run not found")
    return {"status": audit_run.status}

def _run_audit_pipeline(audit_run_id: str, contract_id: str, source_code: str):
    from app.db.postgres_client import SessionLocal
    db = SessionLocal()
    try:
        # ── Steps that do NOT touch Hardhat/filesystem: run outside the lock ──
        # Parse solidity and write graph to Neo4j.  These are pure CPU/DB work
        # and do not need to be serialized against other audit runs.
        tree = parse_solidity(source_code)
        graph = build_graph(tree, source_code.encode("utf-8"))
        _neo_client.write_graph(contract_id, graph)

        import re
        matches = re.findall(r'contract\s+([a-zA-Z0-9_]+)', source_code)
        if not matches:
            raise Exception("No contract found in source code")
        contract_name = matches[-1]

    except Exception as exc:
        logger.exception(f"Audit run {audit_run_id} failed during pre-lock parse/graph phase")
        db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({
            "status": "failed",
            "completed_at": datetime.datetime.utcnow()
        })
        error_action = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="system_error",
            action_description=f"Pipeline failed (parse/graph): {type(exc).__name__}",
            result={"error": str(exc)},
            tx_hash=None
        )
        db.add(error_action)
        db.commit()
        db.close()
        return

    # ── Acquire lock only around Hardhat deploy + agent execution ──────────────
    # While blocked here waiting for the lock, the run stays in "queued" status,
    # which AgentLogView renders as "Waiting for another audit to finish...".
    with pipeline_lock:
        try:
            db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({"status": "running"})
            db.commit()

            deployment_info = deploy_contract(contract_name, source_code)
            if not deployment_info.get("success"):
                raise Exception(f"Deployment failed: {deployment_info.get('error')}")

            # run_audit_agents contains NIM/LLM calls BUT also Hardhat subprocess calls.
            # The lock is needed for the subprocess calls (shared contracts_deploy/ directory).
            # The NIM calls inside are also serialized as a result — acceptable trade-off
            # because the filesystem isolation issue is the primary correctness constraint.
            run_audit_agents(contract_id, deployment_info, audit_run_id, source_code)

            db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({
                "status": "completed",
                "completed_at": datetime.datetime.utcnow()
            })
            db.commit()

        except Exception as exc:
            logger.exception(f"Audit run {audit_run_id} failed with exception")
            db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({
                "status": "failed",
                "completed_at": datetime.datetime.utcnow()
            })
            error_action = AgentAction(
                audit_run_id=audit_run_id,
                agent_type="system_error",
                action_description=f"Pipeline failed: {type(exc).__name__}",
                result={"error": str(exc)},
                tx_hash=None
            )
            db.add(error_action)
            db.commit()
        finally:
            db.close()


@router.post("/start")
def start_audit(request: UploadRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Trigger the full pipeline end-to-end: parse → Neo4j write → Hardhat deploy → orchestrator
    """
    source_code = request.source_code
    
    # Derive contract_id identically to contracts.py
    try:
        # We do this here simply to validate before saving
        parse_solidity(source_code)
    except SolidityParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
        
    contract_id = compute_contract_id(source_code)
    
    # Generate fresh audit_run_id
    audit_run_id = str(uuid.uuid4())

    # Create audit run record in postgres as "queued" BEFORE anything else
    audit_run = AuditRun(
        id=audit_run_id,
        contract_id=contract_id,
        status="queued",
        started_at=datetime.datetime.utcnow()
    )
    db.add(audit_run)
    db.commit()

    background_tasks.add_task(_run_audit_pipeline, audit_run_id, contract_id, source_code)

    return {
        "contract_id": contract_id,
        "audit_run_id": audit_run_id,
        "status": "queued"
    }


@router.get("/{audit_run_id}/agent-log")
def get_audit_agent_log(audit_run_id: str, db: Session = Depends(get_db)):
    """Return the ordered list of agent_actions for a given audit_run_id."""
    actions = (
        db.query(AgentAction)
        .join(AuditRun, AgentAction.audit_run_id == AuditRun.id)
        .filter(AuditRun.id == audit_run_id)
        .order_by(AgentAction.timestamp)
        .all()
    )
    return [
        {
            "id": a.id,
            "audit_run_id": a.audit_run_id,
            "agent_type": a.agent_type,
            "action_description": a.action_description,
            "tx_hash": a.tx_hash,
            "result": a.result,
            "timestamp": a.timestamp.isoformat()
        }
        for a in actions
    ]

