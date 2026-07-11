from fastapi import APIRouter
from app.models.schemas import UploadRequest
from app.parser.solidity_parser import parse_solidity, SolidityParseError
from app.parser.graph_builder import build_graph

router = APIRouter()


@router.post("/upload")
def upload_contract(request: UploadRequest):
    source_code = request.source_code
    try:
        tree = parse_solidity(source_code)
    except SolidityParseError as exc:
        return {"error": str(exc)}
    graph = build_graph(tree, source_code.encode("utf-8"))
    return graph
