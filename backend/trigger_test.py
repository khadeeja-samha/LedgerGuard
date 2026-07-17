import os
import sys
import time
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.api.audit import start_audit
from app.db.postgres_client import SessionLocal, AuditRun, AgentAction

class UploadRequest(BaseModel):
    source_code: str

def mock_run_audit_agents_factory(outer_db):
    def mock_run_audit_agents(contract_id, deployment_info, audit_run_id, source_code):
        print("Mocking a long-running agent execution...")
        time.sleep(1)
        
        print("Simulating a DB connection drop (e.g. proxy timeout / stale idle connection)...")
        # Forcing the outer connection to close, which will cause detached instance or operational errors
        # if anyone tries to use outer_db or its attached objects like audit_run
        outer_db.close()
        
        print("Raising an exception mid-pipeline...")
        raise RuntimeError("NIM API timeout during Attacker Agent!")
    return mock_run_audit_agents

def mock_deploy_contract(*args, **kwargs):
    # Mocking deploy contract so we bypass the NodeNotReadyError and reach run_audit_agents
    return {"success": True, "address": "0x123", "abi": []}

@patch("app.api.audit.deploy_contract", side_effect=mock_deploy_contract)
def trigger_long_running_test(mock_deploy):
    db = SessionLocal()
    request = UploadRequest(source_code="""
pragma solidity ^0.8.0;
contract VulnerableDeposit {
    mapping(address => uint) public balances;
    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }
}
    """)
    
    # Patch run_audit_agents dynamically so we can pass it the outer db session
    with patch("app.api.audit.run_audit_agents", side_effect=mock_run_audit_agents_factory(db)):
        try:
            print("Triggering audit run...")
            result = start_audit(request=request, db=db)
            print("Success?", result)
        except Exception as e:
            print(f"Caught exception from start_audit: {e}")
        finally:
            # We need a NEW session to verify the DB state since outer 'db' was closed
            verify_db = SessionLocal()
            runs = verify_db.query(AuditRun).order_by(AuditRun.started_at.desc()).limit(1).all()
            if runs:
                run = runs[0]
                print(f"Latest run status: {run.status}")
                print(f"Completed at: {run.completed_at}")
                
                # Check agent actions for error log
                error_actions = verify_db.query(AgentAction).filter_by(audit_run_id=run.id, agent_type="system_error").all()
                if error_actions:
                    print(f"Found error log in agent_actions: {error_actions[0].action_description} - {error_actions[0].result}")
                else:
                    print("No system_error logged in agent_actions.")
            else:
                print("No runs found in DB.")
            verify_db.close()

if __name__ == "__main__":
    trigger_long_running_test()
