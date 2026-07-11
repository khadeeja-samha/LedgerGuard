"""Tests for the Solidity parser and graph builder."""

import os
import pytest

from app.parser.solidity_parser import parse_solidity, SolidityParseError
from app.parser.graph_builder import build_graph

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(filename: str) -> str:
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _build_graph_for(filename: str) -> dict:
    source = _load_fixture(filename)
    tree = parse_solidity(source)
    return build_graph(tree, source.encode("utf-8"))


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestSolidityParser:
    def test_parse_valid_contract(self):
        source = _load_fixture("vulnerable_bank.sol")
        tree = parse_solidity(source)
        assert tree.root_node.type == "source_file"
        assert not tree.root_node.has_error

    def test_parse_invalid_source(self):
        with pytest.raises(SolidityParseError):
            parse_solidity("this is not valid solidity {{{")


# ---------------------------------------------------------------------------
# State variable extraction tests
# ---------------------------------------------------------------------------

class TestStateVariables:
    def test_extracts_balances_mapping(self):
        graph = _build_graph_for("vulnerable_bank.sol")
        assert len(graph["state_variables"]) == 1
        sv = graph["state_variables"][0]
        assert sv["name"] == "balances"
        assert "mapping" in sv["type"]
        assert "address" in sv["type"]
        assert "uint256" in sv["type"]


# ---------------------------------------------------------------------------
# Vulnerable bank tests
# ---------------------------------------------------------------------------

class TestVulnerableBank:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.graph = _build_graph_for("vulnerable_bank.sol")

    def test_function_count(self):
        assert len(self.graph["functions"]) == 2

    def test_deposit_function(self):
        deposit = next(f for f in self.graph["functions"] if f["name"] == "deposit")
        assert deposit["visibility"] == "public"
        assert deposit["is_payable"] is True
        assert "balances" in deposit["reads"]
        assert "balances" in deposit["writes"]
        assert deposit["external_calls"] == []

    def test_withdraw_function_metadata(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        assert withdraw["visibility"] == "public"
        assert withdraw["is_payable"] is False

    def test_withdraw_reads_balances(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        assert "balances" in withdraw["reads"]

    def test_withdraw_writes_balances(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        assert "balances" in withdraw["writes"]

    def test_withdraw_has_external_call(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        assert len(withdraw["external_calls"]) == 1

    def test_withdraw_external_call_target(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        ext_call = withdraw["external_calls"][0]
        assert "msg.sender" in ext_call["target"]

    def test_withdraw_before_state_write_is_true(self):
        """The critical assertion: external call happens BEFORE the
        state write to balances, so before_state_write must be True."""
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        ext_call = withdraw["external_calls"][0]
        assert ext_call["before_state_write"] is True

    def test_has_reentrancy_edge(self):
        edges = [
            e for e in self.graph["edges"]
            if e["type"] == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"
        ]
        assert len(edges) >= 1
        edge = edges[0]
        assert edge["from"] == "withdraw"
        assert edge["to"] == "balances"


# ---------------------------------------------------------------------------
# Safe bank tests
# ---------------------------------------------------------------------------

class TestSafeBank:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.graph = _build_graph_for("safe_bank.sol")

    def test_function_count(self):
        assert len(self.graph["functions"]) == 2

    def test_deposit_function(self):
        deposit = next(f for f in self.graph["functions"] if f["name"] == "deposit")
        assert deposit["is_payable"] is True
        assert deposit["external_calls"] == []

    def test_withdraw_has_external_call(self):
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        assert len(withdraw["external_calls"]) == 1

    def test_withdraw_before_state_write_is_false(self):
        """The critical assertion: state write happens BEFORE the
        external call, so before_state_write must be False."""
        withdraw = next(f for f in self.graph["functions"] if f["name"] == "withdraw")
        ext_call = withdraw["external_calls"][0]
        assert ext_call["before_state_write"] is False

    def test_no_reentrancy_edge(self):
        """Safe contract should produce NO reentrancy edges."""
        edges = [
            e for e in self.graph["edges"]
            if e["type"] == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"
        ]
        assert len(edges) == 0
