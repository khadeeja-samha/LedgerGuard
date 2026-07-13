import requests
import json
import time
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "backend" / "tests" / "fixtures"

def test_audit_for_file(filename):
    source = (FIXTURES_DIR / filename).read_text()
    print(f"\n=========================================")
    print(f"Starting Audit on {filename}")
    print(f"=========================================")
    
    start_time = time.time()
    try:
        # POST start
        post_start = time.time()
        resp = requests.post("http://localhost:8000/api/audit/start", json={"source_code": source})
        post_duration = time.time() - post_start
        print(f"POST Status: {resp.status_code} (took {post_duration:.2f} seconds)")
        
        data = resp.json()
        print("POST Response:")
        print(json.dumps(data, indent=2))
        
        audit_run_id = data.get("audit_run_id")
        if audit_run_id:
            # GET agent-log
            get_start = time.time()
            log_resp = requests.get(f"http://localhost:8000/api/audit/{audit_run_id}/agent-log")
            get_duration = time.time() - get_start
            print(f"\nGET Agent-Log Status: {log_resp.status_code} (took {get_duration:.2f} seconds)")
            print("GET Response:")
            print(json.dumps(log_resp.json(), indent=2))
            
    except Exception as e:
        print(f"Error during audit of {filename}: {e}")
    
    total_duration = time.time() - start_time
    print(f"\nTotal time for {filename}: {total_duration:.2f} seconds")
    return total_duration

if __name__ == "__main__":
    t1 = test_audit_for_file("vulnerable_bank.sol")
    t2 = test_audit_for_file("safe_bank.sol")
    print(f"\nGrand Total Duration: {t1 + t2:.2f} seconds")
