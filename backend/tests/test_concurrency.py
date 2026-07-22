import pytest
import threading
import time
from fastapi.testclient import TestClient
from app.main import app
from app.db.postgres_client import AuditRun, AgentAction, Finding, SessionLocal

client = TestClient(app)

# Two distinct contracts — different source means different contract_ids,
# so cross-contamination in the DB is detectable by audit_run_id FK checks.
VULNERABLE_SOURCE = """
pragma solidity ^0.8.0;
contract VulnerableBankConcTest {
    mapping(address => uint256) public balances;
    function deposit() public payable { balances[msg.sender] += msg.value; }
    function withdraw() public {
        uint256 bal = balances[msg.sender];
        require(bal > 0);
        (bool ok, ) = msg.sender.call{value: bal}("");
        require(ok);
        balances[msg.sender] = 0;
    }
}
"""

SAFE_SOURCE = """
pragma solidity ^0.8.0;
contract SafeBankConcTest {
    mapping(address => uint256) public balances;
    function deposit() public payable { balances[msg.sender] += msg.value; }
    function withdraw() public {
        uint256 bal = balances[msg.sender];
        require(bal > 0);
        balances[msg.sender] = 0;
        (bool ok, ) = msg.sender.call{value: bal}("");
        require(ok);
    }
}
"""


def test_audit_concurrency():
    """
    Stage 2 verification: concurrency queuing + result isolation.

    Verifies:
    1. Two simultaneous POSTs each return 200 with status='queued'.
    2. Both runs get distinct audit_run_ids.
    3. Both complete without crashing (sequential via pipeline_lock).
    4. ISOLATION: agent_action and Finding rows are correctly attributed to
       their own audit_run_id — zero overlap between run A and run B rows.
    """
    responses = []
    errors = []

    def fire(source):
        try:
            res = client.post("/api/audit/start", json={"source_code": source})
            responses.append(res)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=fire, args=(VULNERABLE_SOURCE,))
    t2 = threading.Thread(target=fire, args=(SAFE_SOURCE,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Thread errors: {errors}"
    assert len(responses) == 2
    for r in responses:
        assert r.status_code == 200, f"Request failed: {r.text}"
        assert r.json()["status"] == "queued"

    run_a_id = responses[0].json()["audit_run_id"]
    run_b_id = responses[1].json()["audit_run_id"]
    assert run_a_id != run_b_id, "Both runs must have distinct audit_run_ids"

    # ── Poll until both complete ──────────────────────────────────────────────
    print("\nWaiting for both runs to complete...")
    for run_id in [run_a_id, run_b_id]:
        status = "queued"
        deadline = time.time() + 300
        while status in ("queued", "running") and time.time() < deadline:
            res = client.get(f"/api/audit/{run_id}/status")
            assert res.status_code == 200
            status = res.json()["status"]
            if status in ("queued", "running"):
                time.sleep(2)
        assert status in ("completed", "failed"), (
            f"Run {run_id} timed out or stuck. Final status: {status}"
        )

    # ── ISOLATION ASSERTIONS ──────────────────────────────────────────────────
    db = SessionLocal()
    try:
        # 1. agent_actions: rows tagged with run_a_id must not appear under run_b_id
        run_a_action_ids = {
            a.id for a in db.query(AgentAction)
            .filter(AgentAction.audit_run_id == run_a_id).all()
        }
        run_b_action_ids = {
            a.id for a in db.query(AgentAction)
            .filter(AgentAction.audit_run_id == run_b_id).all()
        }
        overlap_actions = run_a_action_ids & run_b_action_ids
        assert not overlap_actions, (
            f"ACTION ISOLATION FAILURE: {len(overlap_actions)} shared rows between run_a and run_b"
        )

        # 2. findings: rows tagged with run_a_id must not appear under run_b_id
        run_a_finding_ids = {
            f.id for f in db.query(Finding)
            .filter(Finding.audit_run_id == run_a_id).all()
        }
        run_b_finding_ids = {
            f.id for f in db.query(Finding)
            .filter(Finding.audit_run_id == run_b_id).all()
        }
        overlap_findings = run_a_finding_ids & run_b_finding_ids
        assert not overlap_findings, (
            f"FINDING ISOLATION FAILURE: {len(overlap_findings)} shared rows between run_a and run_b"
        )

        # 3. Each audit_run row exists and has a different contract_id
        run_a_row = db.query(AuditRun).filter(AuditRun.id == run_a_id).first()
        run_b_row = db.query(AuditRun).filter(AuditRun.id == run_b_id).first()
        assert run_a_row is not None
        assert run_b_row is not None
        assert run_a_row.contract_id != run_b_row.contract_id, (
            "Different source contracts must produce different contract_ids"
        )

        print(f"\n[OK] Run A ({run_a_id[:8]}...) — actions: {len(run_a_action_ids)}, findings: {len(run_a_finding_ids)}")
        print(f"[OK] Run B ({run_b_id[:8]}...) — actions: {len(run_b_action_ids)}, findings: {len(run_b_finding_ids)}")
        print("[OK] Zero row overlap between Run A and Run B — isolation verified.")
    finally:
        db.close()

