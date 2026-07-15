import hashlib
import uuid

from fastapi import APIRouter
from app.models.schemas import UploadRequest
from app.parser.solidity_parser import parse_solidity, SolidityParseError
from app.parser.graph_builder import build_graph
from app.db.neo4j_client import NeoClient
from app.utils import compute_contract_id

router = APIRouter()

_neo_client = NeoClient()


def _derive_contract_id(source_code: str) -> str:
    """Derive a stable contract_id from the normalized source code."""
    return compute_contract_id(source_code)


@router.post("/upload")
def upload_contract(request: UploadRequest):
    source_code = request.source_code
    try:
        tree = parse_solidity(source_code)
    except SolidityParseError as exc:
        return {"error": str(exc)}

    graph = build_graph(tree, source_code.encode("utf-8"))

    contract_id = _derive_contract_id(source_code)
    audit_run_id = str(uuid.uuid4())

    _neo_client.write_graph(contract_id, graph)

    return {
        "contract_id": contract_id,
        "audit_run_id": audit_run_id,
        **graph,
    }
