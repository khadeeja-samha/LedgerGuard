import os
import sys
from fastapi.testclient import TestClient

# Add backend to path for imports
sys.path.insert(0, os.path.abspath("backend"))

from app.main import app
from app.db.postgres_client import SessionLocal, Finding
import json

client = TestClient(app)

def test_api():
    print("--- 1. Testing /api/audit/start on vulnerable_pool.sol ---")
    fixture_path = "backend/tests/fixtures/vulnerable_pool.sol"
    with open(fixture_path, "r") as f:
        source_code = f.read()

    # FIRST RUN
    response1 = client.post("/api/audit/start", json={"source_code": source_code})
    assert response1.status_code == 200, f"Error: {response1.text}"
    data1 = response1.json()
    audit_run_id_1 = data1["audit_run_id"]
    print(f"Run 1 Audit Run ID: {audit_run_id_1}")

    db = SessionLocal()
    try:
        rows1 = db.query(Finding).filter(Finding.audit_run_id == audit_run_id_1).all()
        print(f"\nReal Finding rows in Postgres for Run 1:")
        for r in rows1:
            print(f"  - ID: {r.id}, Func: {r.function_name}, Risk: {r.risk_score} ({r.risk_level}), Attack: {r.attack_type}")
    finally:
        db.close()

    # GET FINDINGS
    print(f"\n--- GET /api/audit/{audit_run_id_1}/findings ---")
    res_get1 = client.get(f"/api/audit/{audit_run_id_1}/findings")
    print(json.dumps(res_get1.json(), indent=2, ensure_ascii=True))


    # SECOND RUN
    print("\n--- 2. IDEMPOTENCY / ISOLATION VERIFICATION ---")
    print("Triggering second run on identical contract...")
    response2 = client.post("/api/audit/start", json={"source_code": source_code})
    assert response2.status_code == 200, f"Error: {response2.text}"
    data2 = response2.json()
    audit_run_id_2 = data2["audit_run_id"]
    print(f"Run 2 Audit Run ID: {audit_run_id_2}")

    db = SessionLocal()
    try:
        rows2 = db.query(Finding).filter(Finding.audit_run_id == audit_run_id_2).all()
        print(f"\nReal Finding rows in Postgres for Run 2:")
        for r in rows2:
            print(f"  - ID: {r.id}, Func: {r.function_name}, Risk: {r.risk_score} ({r.risk_level}), Attack: {r.attack_type}")
            
        print(f"\nTotal rows for Run 1: {len(rows1)}")
        print(f"Total rows for Run 2: {len(rows2)}")
        print(f"Overlap check (Run1 IDs vs Run2 IDs):")
        ids1 = {r.id for r in rows1}
        ids2 = {r.id for r in rows2}
        intersection = ids1.intersection(ids2)
        print(f"  Intersection: {intersection} (Should be set())")
    finally:
        db.close()


    # BOGUS ID GET
    print("\n--- Bogus ID Check ---")
    bogus_id = "nonexistent-audit-run-9999"
    res_bogus = client.get(f"/api/audit/{bogus_id}/findings")
    print(f"GET /api/audit/{bogus_id}/findings response:")
    print(f"Status Code: {res_bogus.status_code}")
    print(f"Response Body: {res_bogus.json()}")


if __name__ == "__main__":
    test_api()
