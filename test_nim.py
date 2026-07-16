import logging
import uuid
import sys
from app.agents.auditor_agent import generate_findings
from app.db.postgres_client import SessionLocal, AgentAction, AuditRun
from unittest.mock import patch

logging.basicConfig(level=logging.INFO)

def test_nim_real_call():
    print("\n--- 4. CONFIRM REAL NIM GENERATION ---")
    audit_run_id = str(uuid.uuid4())
    contract_id = "test-contract-" + audit_run_id[:8]
    
    db = SessionLocal()
    try:
        run = AuditRun(id=audit_run_id, contract_id=contract_id, status="completed")
        db.add(run)
        db.commit()
        
        act1 = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="attacker_agent",
            action_description="Attempt Reentrancy Exploit",
            result={
                "results": [
                    {"function_name": "vuln_func", "exploit_outcome": "EXPLOIT_SUCCEEDED"}
                ]
            }
        )
        db.add(act1)
        db.commit()
    finally:
        db.close()

    mock_graph = {
        "edges": [
            {"from": "vuln_func", "type": "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"}
        ]
    }
    
    with patch("app.agents.auditor_agent.NeoClient.read_graph", return_value=mock_graph):
        print("Running generate_findings() and awaiting REAL NimClient API response...")
        findings = generate_findings(audit_run_id, contract_id)
        
        for f in findings:
            if f["function_name"] == "vuln_func":
                print(f"\nFunction: {f['function_name']} | Risk: {f['risk_level']} ({f['risk_score']}) | Attack: {f['attack_type']}")
                print(f"\nDescription (REAL LLM OUTPUT):")
                print(f["description"])
                print(f"\nTotal characters: {len(f['description'])}")

if __name__ == "__main__":
    test_nim_real_call()
