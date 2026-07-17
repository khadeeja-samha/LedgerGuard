import os
import sys
from fastapi.testclient import TestClient

# Add backend to path for imports
sys.path.insert(0, os.path.abspath("backend"))

from app.main import app
from app.db.postgres_client import SessionLocal, Finding
import json

client = TestClient(app)

TARGET_CONTRACTS = [
    {
        "name": "vulnerable_bank.sol",
        "path": "tests/fixtures/vulnerable_bank.sol",
        "expected_finding": True,
        "expected_attack_type": "reentrancy",
        "expected_score": 9
    },
    {
        "name": "safe_bank.sol",
        "path": "tests/fixtures/safe_bank.sol",
        "expected_finding": False
    },
    {
        "name": "vulnerable_pool.sol",
        "path": "tests/fixtures/vulnerable_pool.sol",
        "expected_finding": True,
        "expected_attack_type": "flashloan",
        "expected_score": 9
    },
    {
        "name": "safe_pool.sol",
        "path": "tests/fixtures/safe_pool.sol",
        "expected_finding": False
    }
]

def run_gate_test():
    print("========================================")
    print("STEP E: FOUR-CONTRACT END-TO-END GATE TEST")
    print("========================================\n")
    
    results = []
    
    for contract in TARGET_CONTRACTS:
        print(f"--- Testing {contract['name']} ---")
        with open(contract["path"], "r") as f:
            source_code = f.read()

        print(f"Starting audit via /api/audit/start...")
        response = client.post("/api/audit/start", json={"source_code": source_code})
        assert response.status_code == 200, f"Error: {response.text}"
        data = response.json()
        audit_run_id = data["audit_run_id"]
        print(f"Audit Run ID: {audit_run_id}")

        print(f"Fetching findings via /api/audit/{audit_run_id}/findings...")
        res_get = client.get(f"/api/audit/{audit_run_id}/findings")
        assert res_get.status_code == 200
        findings = res_get.json()
        
        print(f"Found {len(findings)} total findings.")
        for f in findings:
            print(f"  - [{f.get('risk_level')}] Function: {f.get('function_name')} | Attack: {f.get('attack_type')} | Score: {f.get('risk_score')}")
        
        # Verify findings match expectation
        if contract["expected_finding"]:
            # We expect at least one finding of this type with high risk (score 9)
            high_risk_findings = [f for f in findings if f.get('risk_score') == 9]
            if len(high_risk_findings) > 0:
                # Check that the first high-risk finding matches exactly the expected score and type
                f = high_risk_findings[0]
                if f.get("attack_type") == contract["expected_attack_type"] and f.get("risk_score") == contract["expected_score"]:
                    print(f"[PASS] Vulnerability found as expected with correct type and score.")
                    results.append({"name": contract["name"], "status": "PASS", "details": f"Found expected vulnerability (Type: {f.get('attack_type')}, Score: {f.get('risk_score')})"})
                else:
                    print(f"[FAIL] Found vulnerability but mismatch! Expected Type: {contract['expected_attack_type']}, Score: {contract['expected_score']}. Got Type: {f.get('attack_type')}, Score: {f.get('risk_score')}.")
                    results.append({"name": contract["name"], "status": "FAIL", "details": f"Mismatch in type or score: got Type={f.get('attack_type')} Score={f.get('risk_score')}"})
            else:
                print(f"[FAIL] Expected finding but none found!")
                results.append({"name": contract["name"], "status": "FAIL", "details": "Expected finding but none found"})
        else:
            # We expect NO high risk findings for safe contracts. Low risk (blocked/inconclusive) is acceptable.
            high_risk_findings = [f for f in findings if f.get('risk_level') == "high"]
            all_findings_str = ", ".join([f"{f.get('function_name')} ({f.get('risk_level')})" for f in findings])
            details_str = f"Cleared safe contract (Findings: {all_findings_str if findings else 'None'})"
            
            if len(high_risk_findings) == 0:
                print(f"[PASS] Cleared safe contract without false positives. {details_str}")
                results.append({"name": contract["name"], "status": "PASS", "details": details_str})
            else:
                print(f"[FAIL] False positive detected! {details_str}")
                results.append({"name": contract["name"], "status": "FAIL", "details": f"False positive high-risk finding detected! {details_str}"})
        
        print("\n")

    print("========================================")
    print("GATE TEST RESULTS SUMMARY")
    print("========================================")
    all_passed = True
    for r in results:
        status_symbol = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
        print(f"{status_symbol} {r['name'].ljust(30)} : {r['details']}")
        if r["status"] == "FAIL":
            all_passed = False
            
    if all_passed:
        print("\nALL GATE TESTS PASSED!")
    else:
        print("\nGATE TEST FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    run_gate_test()
