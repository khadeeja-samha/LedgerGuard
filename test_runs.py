import requests, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('postgresql://ledgerguard:ledgerguard_pass@localhost:5432/ledgerguard')
Session = sessionmaker(bind=engine)

with open('backend/tests/fixtures/vulnerable_pool.sol', 'r') as f:
    source_code = f.read()

for i in range(1, 4):
    print(f'\n--- RUN {i} ---')
    res = requests.post('http://localhost:8000/api/audit/start', json={'source_code': source_code})
    if not res.ok:
        print('Error:', res.text)
        continue
    data = res.json()
    audit_run_id = data.get('audit_run_id')
    print(f'audit_run_id: {audit_run_id}')
    
    findings_res = requests.get(f'http://localhost:8000/api/audit/{audit_run_id}/findings')
    findings = findings_res.json()
    for f in findings:
        if f['function_name'] == 'claimReward':
            print(f'Frontend Finding - function: {f["function_name"]}, risk_level: {f["risk_level"]}, risk_score: {f["risk_score"]}')
            
    # Check agent_actions in DB
    session = Session()
    try:
        from sqlalchemy import text
        query = text("SELECT result FROM agent_actions WHERE audit_run_id = :run_id AND action_description LIKE '%claimReward%'")
        result = session.execute(query, {'run_id': audit_run_id}).fetchall()
        for r in result:
            json_data = r[0]
            if type(json_data) is str:
                json_data = json.loads(json_data)
            print(f'Raw exploit_outcome: {json_data.get("exploit_outcome")}')
    finally:
        session.close()
