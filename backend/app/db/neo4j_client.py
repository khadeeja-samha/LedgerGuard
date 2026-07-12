"""
Neo4j client for LedgerGuard.

Provides write_graph(), read_graph(), delete_graph(), and health_check()
against a live Neo4j instance.  All graph nodes are keyed by
(contract_id, name) where contract_id is a SHA-256 hash of the normalized
source code, ensuring idempotent writes via MERGE.
"""

import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables from .env file
load_dotenv()


class NeoClient:
    def __init__(self):
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "ledgerguard_pass")

        # Real driver connection
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_graph(self, contract_id: str, graph: dict) -> None:
        """Persist the graph builder output to Neo4j.

        Uses MERGE keyed on (contract_id, name) so re-uploading
        identical source code is a no-op (true idempotency).

        Args:
            contract_id: SHA-256 hex digest of the normalized source.
            graph: The dict produced by ``graph_builder.build_graph()``,
                   with keys ``functions``, ``state_variables``, ``edges``.
        """
        with self.driver.session() as session:
            session.execute_write(
                self._write_graph_tx, contract_id, graph
            )

    @staticmethod
    def _write_graph_tx(tx, contract_id: str, graph: dict) -> None:
        """Run all 5 MERGE steps inside a single write transaction."""
        functions = graph.get("functions", [])
        state_variables = graph.get("state_variables", [])
        edges = graph.get("edges", [])

        # Step 1 — Function nodes
        if functions:
            tx.run(
                """
                UNWIND $functions AS f
                MERGE (fn:Function {contract_id: $contract_id, name: f.name})
                SET fn.visibility = f.visibility,
                    fn.is_payable = f.is_payable,
                    fn.has_external_call = size(f.external_calls) > 0
                """,
                contract_id=contract_id,
                functions=functions,
            )

        # Step 2 — StateVariable nodes
        if state_variables:
            tx.run(
                """
                UNWIND $state_variables AS sv
                MERGE (s:StateVariable {contract_id: $contract_id, name: sv.name})
                SET s.type = sv.type
                """,
                contract_id=contract_id,
                state_variables=state_variables,
            )

        # Step 3 — READS relationships
        reads_params = [
            {"func_name": f["name"], "var_name": r}
            for f in functions
            for r in f.get("reads", [])
        ]
        if reads_params:
            tx.run(
                """
                UNWIND $pairs AS p
                MATCH (fn:Function {contract_id: $contract_id, name: p.func_name})
                MATCH (sv:StateVariable {contract_id: $contract_id, name: p.var_name})
                MERGE (fn)-[:READS]->(sv)
                """,
                contract_id=contract_id,
                pairs=reads_params,
            )

        # Step 4 — WRITES relationships
        writes_params = [
            {"func_name": f["name"], "var_name": w}
            for f in functions
            for w in f.get("writes", [])
        ]
        if writes_params:
            tx.run(
                """
                UNWIND $pairs AS p
                MATCH (fn:Function {contract_id: $contract_id, name: p.func_name})
                MATCH (sv:StateVariable {contract_id: $contract_id, name: p.var_name})
                MERGE (fn)-[:WRITES]->(sv)
                """,
                contract_id=contract_id,
                pairs=writes_params,
            )

        # Step 5 — MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE edges
        if edges:
            edge_params = [
                {"func_name": e["from"], "var_name": e["to"]}
                for e in edges
                if e.get("type") == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"
            ]
            if edge_params:
                tx.run(
                    """
                    UNWIND $pairs AS p
                    MATCH (fn:Function {contract_id: $contract_id, name: p.func_name})
                    MATCH (sv:StateVariable {contract_id: $contract_id, name: p.var_name})
                    MERGE (fn)-[:MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE]->(sv)
                    """,
                    contract_id=contract_id,
                    pairs=edge_params,
                )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_graph(self, contract_id: str) -> dict:
        """Query Neo4j and return the graph in the same JSON shape
        the frontend expects from the graph builder.

        Args:
            contract_id: SHA-256 hex digest to look up.

        Returns:
            ``{"functions": [...], "state_variables": [...], "edges": [...]}``
        """
        with self.driver.session() as session:
            return session.execute_read(
                self._read_graph_tx, contract_id
            )

    @staticmethod
    def _read_graph_tx(tx, contract_id: str) -> dict:
        """Reconstruct the graph builder JSON shape from Neo4j."""

        # Query 1 — Functions with reads/writes
        func_result = tx.run(
            """
            MATCH (fn:Function {contract_id: $contract_id})
            OPTIONAL MATCH (fn)-[:READS]->(r:StateVariable)
            OPTIONAL MATCH (fn)-[:WRITES]->(w:StateVariable)
            RETURN fn.name AS name, fn.visibility AS visibility,
                   fn.is_payable AS is_payable,
                   fn.has_external_call AS has_external_call,
                   collect(DISTINCT r.name) AS reads,
                   collect(DISTINCT w.name) AS writes
            """,
            contract_id=contract_id,
        )
        functions = []
        for record in func_result:
            reads = [r for r in record["reads"] if r is not None]
            writes = [w for w in record["writes"] if w is not None]
            functions.append({
                "name": record["name"],
                "visibility": record["visibility"],
                "is_payable": record["is_payable"],
                "has_external_call": record["has_external_call"],
                "reads": sorted(reads),
                "writes": sorted(writes),
            })

        # Query 2 — State variables
        sv_result = tx.run(
            """
            MATCH (sv:StateVariable {contract_id: $contract_id})
            RETURN sv.name AS name, sv.type AS type
            """,
            contract_id=contract_id,
        )
        state_variables = [
            {"name": record["name"], "type": record["type"]}
            for record in sv_result
        ]

        # Query 3 — Reentrancy edges
        edge_result = tx.run(
            """
            MATCH (fn:Function {contract_id: $contract_id})
                  -[e:MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE]->
                  (sv:StateVariable)
            RETURN fn.name AS `from`, sv.name AS `to`, type(e) AS type
            """,
            contract_id=contract_id,
        )
        edges = [
            {"type": record["type"], "from": record["from"], "to": record["to"]}
            for record in edge_result
        ]

        return {
            "functions": functions,
            "state_variables": state_variables,
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # Delete (for testing / cleanup)
    # ------------------------------------------------------------------

    def delete_graph(self, contract_id: str) -> None:
        """Delete all nodes and relationships for a given contract_id."""
        with self.driver.session() as session:
            session.execute_write(self._delete_graph_tx, contract_id)

    @staticmethod
    def _delete_graph_tx(tx, contract_id: str) -> None:
        tx.run(
            """
            MATCH (n {contract_id: $contract_id})
            DETACH DELETE n
            """,
            contract_id=contract_id,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Verify connection by running a simple query."""
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1")
                value = result.single()[0]
                if value == 1:
                    print("Neo4j connection successful!")
                    return True
        except Exception as e:
            print(f"Neo4j connection failed: {e}")
            return False

    def close(self):
        if self.driver:
            self.driver.close()


if __name__ == "__main__":
    client = NeoClient()
    client.health_check()
    client.close()
