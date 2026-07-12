"""
Audit routes — matches PRD §10 layout:
  GET /api/audit/{contract_id}/graph
  GET /api/audit/{contract_id}/findings    (Week 4 stub)
  GET /api/audit/{contract_id}/agent-log   (Week 4 stub)
"""

from fastapi import APIRouter
from app.db.neo4j_client import NeoClient

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


@router.get("/{contract_id}/agent-log")
def get_audit_agent_log(contract_id: str):
    """Week 4 stub — will return agent execution log."""
    return []
