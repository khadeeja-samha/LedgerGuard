# stability_check.py — corrected query logic
import requests
import time
import json
from sqlalchemy import create_engine, text

API_URL = "http://localhost:8000/api/audit/start"
DB_URL = "postgresql://ledgerguard:ledgerguard_pass@localhost:5432/ledgerguard"

with open("tests/fixtures/vulnerable_pool.sol") as f:
    source_code = f.read()

engine = create_engine(DB_URL)
results = []

N_RUNS = 8

for i in range(N_RUNS):
    print(f"--- Run {i+1}/{N_RUNS} ---")
    try:
        resp = requests.post(API_URL, json={"source_code": source_code}, timeout=900)
        resp.raise_for_status()
        audit_run_id = resp.json()["audit_run_id"]
    except Exception as e:
        print(f"  Run failed to start/complete: {e}")
        results.append("RUN_FAILED")
        continue

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT result FROM agent_actions
                WHERE audit_run_id = :run_id
                  AND action_description = 'Attempt Flash-Loan Exploit'
                ORDER BY timestamp DESC LIMIT 1
            """),
            {"run_id": audit_run_id}
        ).fetchone()

    outcome = "NOT_FOUND"
    if row and row[0]:
        for finding in row[0].get("results", []):
            if finding.get("function_name") == "claimReward":
                outcome = finding.get("exploit_outcome", "UNKNOWN")
                break

    print(f"  claimReward outcome: {outcome}")
    results.append(outcome)
    time.sleep(2)

print("\n=== Summary ===")
print(f"Total runs: {len(results)}")
for outcome in set(results):
    count = results.count(outcome)
    print(f"  {outcome}: {count}/{len(results)} ({100*count/len(results):.0f}%)")