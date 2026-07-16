# LedgerGuard

*We don't just scan your smart contract for bugs — we attack it, live, before someone else does.*

## Overview

LedgerGuard is a multi-agent smart contract security auditing platform. It goes beyond static analysis by parsing Solidity source code, mapping code dependencies into a Neo4j graph database, dynamically provisioning a local blockchain (Hardhat), and eventually utilizing AI agents to actively attack and exploit contracts prior to mainnet deployment.

## Tech Stack

* **Frontend:** Next.js (React)
* **Backend:** FastAPI (Python)
* **Database:** Neo4j (Graph Database)
* **Blockchain:** Hardhat (Local Ethereum network)
* **Parser:** tree-sitter (Solidity)
* **Agent Intelligence:** NVIDIA NIM (meta/llama-3.3-70b-instruct) for future agent logic and vulnerability explanations

## Phase 1 Status — Complete ✅

* **Scaffolding:** FastAPI backend and Next.js frontend initialized and communicating.
* **Parser:** Implemented a `tree-sitter` based Solidity parser capable of extracting functions, state variables, and execution flows.
* **Vulnerability Detection:** Successfully identifying the `MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE` pattern indicative of reentrancy vulnerabilities.
* **Fixtures:** Control pairs established (`vulnerable_bank.sol` / `safe_bank.sol`).
* **Verification:** 17 passing `pytest` tests with verified red→green gate proofs validating the parser logic.

## Phase 2 Status — Complete ✅

1. **Neo4j Real Connection:** Integrated Python client with real graph DB connection (health_check implemented with verified red/green test proofs).
2. **Neo4j Real Graph Writes:** Implemented idempotent `MERGE` logic keyed on `{contract_id: sha256(normalized_source), name}`, ensuring deduplication. A separate `audit_run_id` is tracked per upload. Idempotency is proven via repeated uploads returning the exact same `contract_id` and unchanged node/edge counts.
3. **Frontend GraphViewer:** Implemented utilizing `react-force-graph-2d`. Function nodes render as indigo, StateVariable nodes as emerald, and reentrancy edges highlight vividly in red. Includes a click-to-inspect side panel. Verified against both test fixtures ensuring the correct `contract_id` and edge rendering behaviors.
4. **Hardhat Provisioning (`backend/blockchain/`):** Built a programmatic bridge to deploy arbitrary Solidity source dynamically (`deploy_contract(name, source_code)`). Implemented session-scoped node lifecycle management via `subprocess` with `eth_chainId` readiness polling. Deployment output is structured via JSON files rather than brittle stdout parsing.
5. **Gate Test (`tests/test_hardhat_provisioning.py`):** Achieved real on-chain interactions. Verified balance changes by executing a 1 ETH deposit transaction via `web3.py`. Verified that malformed Solidity strings throw genuine `DeploymentError` exceptions. Both pathways confirmed with red→green sanity checks.

### Test Results
* **Parser:** 17 tests
* **Neo4j:** 5 tests
* **Hardhat:** 2 tests
* **Total:** 24 passing tests, verified to run synchronously in a combined suite without cross-contamination or conflicts.

## Phase 3 Status — Complete ✅

1. **Attacker Agent (`app/agents/attacker_agent.py`)**: Uses NVIDIA NIM (meta/llama-3.3-70b-instruct) to dynamically write Mocha exploits against flagged vulnerabilities. The deterministic Hardhat/Mocha test verdicts serve as the sole source of truth for exploit success.
2. **User Agent (`app/agents/user_agent.py`)**: Deterministic baseline guard that proves a contract is functional via direct `web3.py` interaction (deposit -> check -> withdraw). Runs completely independent of LLMs.
3. **Orchestrator (`app/agents/orchestrator.py`) & Postgres Integration**: Wires the pipeline end-to-end. Records every agent action to a PostgreSQL `agent_actions` table, keyed by `audit_run_id`.
4. **New API Endpoints (`app/api/audit.py`)**:
   - `POST /api/audit/start`: Triggers parsing, Neo4j writes, Hardhat deployment, and Orchestrator execution.
   - `GET /api/audit/{audit_run_id}/agent-log`: Retrieves ordered `agent_actions` JSON payload.
5. **Gate Test Results (`tests/test_attacker_agent.py`)**: 
   - `EXPLOIT_SUCCEEDED` achieved on `vulnerable_bank.sol` (with the Orchestrator seeding victim funds prior to attack).
   - `results == []` on `safe_bank.sol` (AI bypass correctly triggered since no flagged Neo4j edge exists).
   - User Agent baseline integrated and passing deterministically on both.

### Known Limitations (Phase 3)
- `drained_amount` extraction is best-effort regex on LLM-generated Mocha test titles; `exploit_outcome` is the actual, deterministic source of truth.
- Only the **reentrancy** attack pattern is implemented so far. Flash-loan detection is deferred to Week 4.
- No live-streaming UI exists yet — the `agent_actions` data is populated in Postgres, but the frontend does not yet consume or display it (Week 4).

## Week 4 Status — Complete ✅

* **Flash-loan attack pattern detection and execution:** Integrated LLM semantic classification for price-dependency check and mocha execution to prove flash-loan vulnerabilities.
* **`findings` and `audit_runs` PostgreSQL tables:** Successfully added model schemas, database migrations, and auto-backfill logic.
* **Architectural Note:** Reentrancy candidate-detection is based on a deterministic Neo4j graph edge mapping, while flash-loan candidate-detection utilizes an LLM semantic classifier (`_check_flashloan_semantics_with_llm`) paired with real Mocha execution as the sole pass/fail source of truth. Both approaches keep exploit SUCCESS/FAILURE verification fully deterministic; only candidate SELECTION differs by attack type. This is a deliberate architectural choice to handle the semantic variability of price feeds compared to the structural nature of reentrancy call patterns.

## What Is NOT Yet Built

To remain explicit about current scope, the following hackathon milestones are pending:
* Auditor Agent + risk scoring and NVIDIA NIM LLM explanation layer (Phase 4)
* Live agent-log streaming UI in the frontend (Phase 4)
* General UI polish, animations, and theming (Phase 5, deliberately deferred to prioritize core logic)

## Setup Instructions

### 1. Clone & Prerequisites
Ensure you have Python 3.10+, Node.js v18+, and Docker Desktop installed.

```bash
git clone <repository-url>
cd Ledgerguard
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate | Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database Setup (Neo4j)
Ensure Docker Desktop is running, then spin up the Neo4j container:
```bash
# From the root Ledgerguard directory
docker-compose up -d
```

### 4. Frontend Setup
```bash
cd frontend
npm install
```

### 5. Running the Application
Open two terminal windows:

**Terminal 1 (Backend):**
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```
Navigate to `http://localhost:3000` to access the Graph Viewer.

### 6. Running Tests
To verify the system integration, run the full test suite from the backend:
```bash
cd backend
python -m pytest tests/ -v
```

## Project Structure

```
Ledgerguard/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers (contracts.py, audit.py)
│   │   ├── db/           # Neo4j client configuration
│   │   ├── models/       # Pydantic schemas
│   │   ├── parser/       # Tree-sitter Solidity parsing and graph building logic
│   │   └── main.py       # Application entrypoint
│   ├── blockchain/       # Hardhat environment (hardhat.config.js, deploy.js)
│   ├── tests/            # Pytest suites and fixture files
│   └── requirements.txt  # Python dependencies
├── frontend/             # Next.js UI application
├── docker-compose.yml    # Neo4j database configuration
└── README.md
```
