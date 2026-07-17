import json
from sqlalchemy import create_engine, text

engine = create_engine('postgresql://ledgerguard:ledgerguard_pass@localhost:5432/ledgerguard')
conn = engine.connect()

print("--- AUDIT RUNS ---")
runs = conn.execute(text("SELECT id, status, started_at, completed_at FROM audit_runs ORDER BY started_at DESC LIMIT 10")).fetchall()
for r in runs:
    print(f"ID: {r[0]} | Status: {r[1]} | Started: {r[2]} | Completed: {r[3]}")

for r in runs:
    if r[1] == 'completed':
        print(f"\n--- RESULTS FOR COMPLETED RUN {r[0]} ---")
        # Get findings from findings table
        findings = conn.execute(text("SELECT function_name, risk_level, risk_score, attack_type FROM findings WHERE audit_run_id = :id"), {"id": r[0]}).fetchall()
        print("Findings in table:")
        for f in findings:
            print(f"  Func: {f[0]} | Risk: {f[1]} | Score: {f[2]} | Attack: {f[3]}")
        
        # Get agent actions
        actions = conn.execute(text("SELECT action_description, result FROM agent_actions WHERE audit_run_id = :id ORDER BY timestamp"), {"id": r[0]}).fetchall()
        print("Agent actions:")
        for act in actions:
            desc = act[0]
            res = act[1]
            if isinstance(res, str):
                res = json.loads(res)
            
            # Print condensed result
            res_results = res.get("results", []) if isinstance(res, dict) else []
            print(f"  Action: {desc}")
            for item in res_results:
                print(f"    Func: {item.get('function_name')} | Exploit Outcome: {item.get('exploit_outcome')}")
