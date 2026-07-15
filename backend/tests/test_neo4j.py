"""Tests for Neo4j write/read roundtrip and idempotency.

These tests require a live Neo4j instance (docker compose up).
They use a dedicated test contract_id and clean up after themselves.
"""

import hashlib
import os

import pytest

from app.db.neo4j_client import NeoClient
from app.parser.solidity_parser import parse_solidity
from app.parser.graph_builder import build_graph
from app.utils import compute_contract_id

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> str:
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _derive_contract_id(source_code: str) -> str:
    return compute_contract_id(source_code)


@pytest.fixture(scope="module")
def neo_client():
    """Provide a NeoClient instance for the test module."""
    client = NeoClient()
    yield client
    client.close()


@pytest.fixture()
def vulnerable_graph():
    """Parse vulnerable_bank.sol and return (contract_id, graph)."""
    source = _load_fixture("vulnerable_bank.sol")
    tree = parse_solidity(source)
    graph = build_graph(tree, source.encode("utf-8"))
    contract_id = _derive_contract_id(source)
    return contract_id, graph


@pytest.fixture(autouse=True)
def cleanup(neo_client, vulnerable_graph):
    """Clean up the test contract before and after each test."""
    contract_id, _ = vulnerable_graph
    neo_client.delete_graph(contract_id)
    yield
    neo_client.delete_graph(contract_id)


# ---------------------------------------------------------------------------
# Roundtrip test
# ---------------------------------------------------------------------------

class TestWriteAndReadRoundtrip:
    def test_roundtrip(self, neo_client, vulnerable_graph):
        contract_id, graph = vulnerable_graph

        # Write
        neo_client.write_graph(contract_id, graph)

        # Read back
        result = neo_client.read_graph(contract_id)

        # Verify structure
        assert "functions" in result
        assert "state_variables" in result
        assert "edges" in result

        # Verify function names
        func_names = {f["name"] for f in result["functions"]}
        assert func_names == {"deposit", "withdraw"}

        # Verify state variables
        sv_names = {sv["name"] for sv in result["state_variables"]}
        assert sv_names == {"balances"}

        # Verify the reentrancy edge survived the roundtrip
        reentrancy_edges = [
            e for e in result["edges"]
            if e["type"] == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"
        ]
        assert len(reentrancy_edges) == 1
        assert reentrancy_edges[0]["from"] == "withdraw"
        assert reentrancy_edges[0]["to"] == "balances"

    def test_function_properties(self, neo_client, vulnerable_graph):
        contract_id, graph = vulnerable_graph
        neo_client.write_graph(contract_id, graph)
        result = neo_client.read_graph(contract_id)

        withdraw = next(f for f in result["functions"] if f["name"] == "withdraw")
        assert withdraw["visibility"] == "public"
        assert withdraw["is_payable"] is False
        assert withdraw["has_external_call"] is True
        assert "balances" in withdraw["reads"]
        assert "balances" in withdraw["writes"]

        deposit = next(f for f in result["functions"] if f["name"] == "deposit")
        assert deposit["visibility"] == "public"
        assert deposit["is_payable"] is True
        assert deposit["has_external_call"] is False


# ---------------------------------------------------------------------------
# Idempotency test
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_no_duplicates_on_double_write(self, neo_client, vulnerable_graph):
        contract_id, graph = vulnerable_graph

        # Write twice
        neo_client.write_graph(contract_id, graph)
        neo_client.write_graph(contract_id, graph)

        # Count nodes
        with neo_client.driver.session() as session:
            result = session.run(
                "MATCH (n {contract_id: $cid}) RETURN count(n) AS cnt",
                cid=contract_id,
            )
            node_count = result.single()["cnt"]

        # vulnerable_bank has 2 functions + 1 state variable = 3 nodes
        assert node_count == 3, f"Expected 3 nodes, got {node_count} (duplicates!)"

    def test_no_duplicate_relationships(self, neo_client, vulnerable_graph):
        contract_id, graph = vulnerable_graph

        # Write twice
        neo_client.write_graph(contract_id, graph)
        neo_client.write_graph(contract_id, graph)

        # Count relationships
        with neo_client.driver.session() as session:
            result = session.run(
                "MATCH (a {contract_id: $cid})-[r]->(b) RETURN count(r) AS cnt",
                cid=contract_id,
            )
            rel_count = result.single()["cnt"]

        # 2 READS + 2 WRITES + 1 MAKES_EXTERNAL_CALL = 5 relationships
        assert rel_count == 5, f"Expected 5 relationships, got {rel_count} (duplicates!)"


# ---------------------------------------------------------------------------
# Nonexistent contract test
# ---------------------------------------------------------------------------

class TestReadNonexistent:
    def test_returns_empty_graph(self, neo_client):
        result = neo_client.read_graph("nonexistent_hash_that_does_not_exist")
        assert result == {
            "functions": [],
            "state_variables": [],
            "edges": [],
        }
