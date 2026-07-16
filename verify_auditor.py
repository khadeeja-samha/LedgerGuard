import logging
import uuid
import sys
from unittest.mock import patch
from app.agents.auditor_agent import generate_findings
from app.db.postgres_client import SessionLocal, AgentAction, AuditRun

logging.basicConfig(level=logging.INFO)

def run_verifications():
    print("\n--- SETUP MOCK DATA ---")
    audit_run_id = str(uuid.uuid4())
    contract_id = "test-contract-" + audit_run_id[:8]
    
    db = SessionLocal()
    try:
        # Create a mock audit run
        run = AuditRun(id=audit_run_id, contract_id=contract_id, status="completed")
        db.add(run)
        db.commit()
        
        # Action 1: Reentrancy results (covers #2 vuln_func and #5 dual_func)
        act1 = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="attacker_agent",
            action_description="Attempt Reentrancy Exploit",
            result={
                "results": [
                    {"function_name": "vuln_func", "exploit_outcome": "EXPLOIT_SUCCEEDED"},
                    {"function_name": "dual_func", "exploit_outcome": "EXPLOIT_BLOCKED"}
                ]
            }
        )
        # Action 2: Flashloan results (covers #3 error_func and #5 dual_func)
        act2 = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="attacker_agent",
            action_description="Attempt Flash-Loan Exploit",
            result={
                "results": [
                    {"function_name": "error_func", "exploit_outcome": "SCRIPT_ERROR"},
                    {"function_name": "dual_func", "exploit_outcome": "EXPLOIT_SUCCEEDED"}
                ]
            }
        )
        db.add(act1)
        db.add(act2)
        db.commit()
    finally:
        db.close()

    mock_graph = {
        "edges": [
            {"from": "vuln_func", "type": "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"},
            {"from": "missing_func", "type": "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"},
            {"from": "error_func", "type": "USES_MANIPULABLE_PRICE_SOURCE"},
            {"from": "dual_func", "type": "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"},
            {"from": "dual_func", "type": "USES_MANIPULABLE_PRICE_SOURCE"}
        ]
    }

    print("\n--- 2. BREAK THE NIM CALL AND CONFIRM THE SCORE SURVIVES ---")
    def mock_generate(*args, **kwargs):
        raise RuntimeError("Fake NIM API Exception")
    
    with patch("app.agents.auditor_agent.NeoClient.read_graph", return_value=mock_graph):
        with patch("app.agents.auditor_agent.NimClient.generate", side_effect=mock_generate):
            findings = generate_findings(audit_run_id, contract_id)
            print("Findings with Broken NIM Call:")
            for f in findings:
                if f["function_name"] == "vuln_func":
                    print(f"Function: {f['function_name']} | Risk: {f['risk_level']} ({f['risk_score']}) | Attack: {f['attack_type']} | Desc: {f['description']}")

    print("\n--- 3. TEST BOTH MISSING_LOG AND SCRIPT_ERROR CASES DISTINCTLY ---")
    print("\n[Logs from generate_findings() for missing_func and error_func]")
    # We run it normally now, but mock LLM to just return a dummy string so we don't spam the real API
    def dummy_generate(*args, **kwargs):
        return "Dummy generated explanation."
        
    with patch("app.agents.auditor_agent.NeoClient.read_graph", return_value=mock_graph):
        with patch("app.agents.auditor_agent.NimClient.generate", side_effect=dummy_generate):
            findings = generate_findings(audit_run_id, contract_id)
            print("\nFindings Output for MISSING_LOG and SCRIPT_ERROR:")
            for f in findings:
                if f["function_name"] in ("missing_func", "error_func"):
                    print(f"Function: {f['function_name']} | Risk: {f['risk_level']} ({f['risk_score']}) | Attack: {f['attack_type']}")

    print("\n--- 5. DUAL-EDGE FUNCTION PRODUCES TWO FINDINGS ---")
    dual_findings = [f for f in findings if f["function_name"] == "dual_func"]
    for f in dual_findings:
        print(f"Function: {f['function_name']} | Attack Type: {f['attack_type']} | Score: {f['risk_score']} | Risk Level: {f['risk_level']}")
    print(f"Total findings for dual_func: {len(dual_findings)}")

if __name__ == "__main__":
    run_verifications()
