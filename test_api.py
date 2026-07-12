import requests
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "backend" / "tests" / "fixtures"

def test_contract(name, filename):
    source = (FIXTURES_DIR / filename).read_text()
    print(f"\n--- {name} ---")
    try:
        resp = requests.post("http://localhost:8000/api/contracts/upload", json={"source_code": source})
        print(f"Status: {resp.status_code}")
        print("Response:")
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_contract("Vulnerable Bank", "vulnerable_bank.sol")
    test_contract("Safe Bank", "safe_bank.sol")
