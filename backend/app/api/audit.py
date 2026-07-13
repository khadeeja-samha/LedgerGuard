"""
Audit routes — matches PRD §10 layout:
  GET /api/audit/{contract_id}/graph
  GET /api/audit/{contract_id}/findings    (Week 4 stub)
  GET /api/audit/{contract_id}/agent-log   (Week 4 stub)
"""

import hashlib
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.neo4j_client import NeoClient
from app.db.postgres_client import get_db, AgentAction
from app.models.schemas import UploadRequest
from app.parser.solidity_parser import parse_solidity, SolidityParseError
from app.parser.graph_builder import build_graph
from blockchain.deploy_interface import deploy_contract
from app.agents.orchestrator import run_audit_agents

router = APIRouter()

_neo_client = NeoClient()


@router.get("/{contract_id}/graph")
def get_audit_graph(contract_id: str):
    """Return the persisted graph for a given contract_id."""
    graph = _neo_client.read_graph(contract_id)
    return graph


@router.get("/{contract_id}/findings")
def get_audit_findings(contract_id: str):
    """Week 4 stub — will return LLM-generated findings."""
    return []


@router.post("/start")
def start_audit(request: UploadRequest, db: Session = Depends(get_db)):
    """
    Trigger the full pipeline end-to-end: parse → Neo4j write → Hardhat deploy → orchestrator
    """
    source_code = request.source_code
    try:
        tree = parse_solidity(source_code)
    except SolidityParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    graph = build_graph(tree, source_code.encode("utf-8"))

    # Derive contract_id identically to contracts.py
    normalized = source_code.strip().replace("\r\n", "\n")
    contract_id = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    # Generate fresh audit_run_id
    audit_run_id = str(uuid.uuid4())

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

    return {
        "contract_id": contract_id,
        "audit_run_id": audit_run_id,
        "status": "completed"
    }

@router.get("/{audit_run_id}/agent-log")
def get_audit_agent_log(audit_run_id: str, db: Session = Depends(get_db)):
    """Return the ordered list of agent_actions for a given audit_run_id."""
    actions = db.query(AgentAction).filter(AgentAction.audit_run_id == audit_run_id).order_by(AgentAction.timestamp).all()
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
