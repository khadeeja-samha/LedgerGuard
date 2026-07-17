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


@router.post("/start")
def start_audit(request: UploadRequest, db: Session = Depends(get_db)):
    """
    Trigger the full pipeline end-to-end: parse → Neo4j write → Hardhat deploy → orchestrator
    """
    source_code = request.source_code
    
    # Derive contract_id identically to contracts.py
    contract_id = compute_contract_id(source_code)
    
    # Generate fresh audit_run_id
    audit_run_id = str(uuid.uuid4())

    # Create audit run record in postgres as "running" BEFORE anything else
    audit_run = AuditRun(
        id=audit_run_id,
        contract_id=contract_id,
        status="running",
        started_at=datetime.datetime.utcnow()
    )
    db.add(audit_run)
    db.commit()

    try:
        # Parse solidity
        try:
            tree = parse_solidity(source_code)
        except SolidityParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        graph = build_graph(tree, source_code.encode("utf-8"))

        # Write graph to Neo4j
        _neo_client.write_graph(contract_id, graph)

        # Extract the contract name using regex (find the last defined contract)
        import re
        matches = re.findall(r'contract\s+([a-zA-Z0-9_]+)', source_code)
        if not matches:
            raise HTTPException(status_code=400, detail="No contract found in source code")
        contract_name = matches[-1]

        deployment_info = deploy_contract(contract_name, source_code)
        if not deployment_info.get("success"):
            raise HTTPException(status_code=500, detail=f"Deployment failed: {deployment_info.get('error')}")

        # Run orchestrator
        run_audit_agents(contract_id, deployment_info, audit_run_id, source_code)

        # Update status to "completed" using an explicit update query to avoid detached instance issues
        db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({
            "status": "completed",
            "completed_at": datetime.datetime.utcnow()
        })
        db.commit()

    except Exception as exc:
        logger.exception(f"Audit run {audit_run_id} failed with exception")
        
        # Use a fresh DB session for cleanup to prevent errors if outer `db` connection timed out
        from app.db.postgres_client import SessionLocal
        cleanup_db = SessionLocal()
        try:
            cleanup_db.query(AuditRun).filter(AuditRun.id == audit_run_id).update({
                "status": "failed",
                "completed_at": datetime.datetime.utcnow()
            })
            
            # Log the error in agent_actions table so it is visible in the DB
            error_action = AgentAction(
                audit_run_id=audit_run_id,
                agent_type="system_error",
                action_description=f"Pipeline failed: {type(exc).__name__}",
                result={"error": str(exc)},
                tx_hash=None
            )
            cleanup_db.add(error_action)
            cleanup_db.commit()
        except Exception as inner_exc:
            logger.error(f"Failed to update audit run status to failed: {inner_exc}")
        finally:
            cleanup_db.close()
            
        # If it is already an HTTPException, reraise it
        if isinstance(exc, HTTPException):
            raise exc
        # Otherwise raise 500
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "contract_id": contract_id,
        "audit_run_id": audit_run_id,
        "status": "completed"
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

