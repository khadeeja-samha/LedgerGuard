from sqlalchemy import create_engine, text

engine = create_engine("postgresql://ledgerguard:ledgerguard_pass@localhost:5432/ledgerguard")
conn = engine.connect()

# Check action_description format from a known-completed run
result = conn.execute(text(
    "SELECT action_description FROM agent_actions WHERE audit_run_id = :run_id"
), {"run_id": "46ef00a7-1b48-4c91-99af-ebae00784208"})

for row in result:
    print(row[0])