from sqlalchemy import create_engine, text
import json

engine = create_engine("postgresql://ledgerguard:ledgerguard_pass@localhost:5432/ledgerguard")
conn = engine.connect()

result = conn.execute(text(
    "SELECT action_description, result FROM agent_actions WHERE audit_run_id = :run_id ORDER BY timestamp"
), {"run_id": "46ef00a7-1b48-4c91-99af-ebae00784208"})

for row in result:
    print("---", row[0], "---")
    print(json.dumps(row[1], indent=2))
    print()
    