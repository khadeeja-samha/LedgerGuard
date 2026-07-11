# Ledgerguard

## Week 1 Status

### What was built
- **FastAPI Backend Structure**: Base backend structure established with CORS enabled and endpoints structured using an `APIRouter`.
- **Tree-sitter Solidity Parser**: We migrated from `solidity-parser` (ANTLR) which fails on modern Solidity syntax (like `call{value: ...}`) to `tree-sitter` (v0.25.2) and `tree-sitter-solidity`. This robustly converts Solidity source code into a detailed Abstract Syntax Tree (AST).
- **Core Graph Builder**: We developed the `graph_builder.py` module to analyze the AST and generate a JSON graph mapping out functions, state variables, external calls, and state reads/writes.
- **CEI (Checks-Effects-Interactions) Detection Algorithm**: The graph builder implements a critical ordering detection algorithm. It flattens intra-function statements, checks for external calls vs. state variable writes, and flags `MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE` if an external call is executed before a state update.
- **Automated Gate Proof Verification**: We implemented 17 comprehensive pytest unit tests.
  - Successfully proved that the `vulnerable_bank.sol` fixture generates the `MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE` edge on its `withdraw` function.
  - Successfully proved that the `safe_bank.sol` fixture (which zeroes the balance before making the external call) produces ZERO false positives and does not generate the reentrancy edge.
  - This was definitively verified with a manual red→green test run intentionally breaking the logic to prove the validity of the tests.

### What is NOT yet built (V1 Scoped Items)
To be transparent on the limits of this current MVP:
- **Contract-type external calls**: Currently, the external call detection only covers low-level calls (`.call`, `.delegatecall`, `.staticcall`, `.send`, `.transfer`). It does not detect high-level interface calls like `token.transfer(to, amount)`.
- **Inter-function tracing**: The analysis is strictly intra-function. If an external call is made inside an internal helper function, the top-level calling function is not flagged.
- **Neo4j real writes**: The backend currently produces the JSON structure but does not persist it to a real Neo4j graph database.
- **Hardhat Integration**: There is no direct integration to hook this analysis into a Hardhat deployment pipeline yet.
- **Agents & UI Polish**: Advanced agent features and significant frontend UI polishing are planned but not yet built.
