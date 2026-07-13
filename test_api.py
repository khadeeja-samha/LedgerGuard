import requests
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "backend" / "tests" / "fixtures"

def test_audit():
    source = (FIXTURES_DIR / "vulnerable_bank.sol").read_text()
    print("\n--- Starting Audit on Vulnerable Bank ---")
    try:
        resp = requests.post("http://localhost:8000/api/audit/start", json={"source_code": source})
        print(f"Status: {resp.status_code}")
        data = resp.json()
        print("POST Response:")
        print(json.dumps(data, indent=2))
        
        audit_run_id = data.get("audit_run_id")
        if audit_run_id:
            print(f"\n--- Fetching Agent Log for {audit_run_id} ---")
            log_resp = requests.get(f"http://localhost:8000/api/audit/{audit_run_id}/agent-log")
            print(f"Status: {log_resp.status_code}")
            print("GET Response:")
            print(json.dumps(log_resp.json(), indent=2))
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_audit()
