import logging
from web3 import Web3
from app.db.postgres_client import SessionLocal, AgentAction
from app.agents.user_agent import run_baseline_usage
from app.agents.attacker_agent import attempt_reentrancy_exploit, attempt_flashloan_exploit

logger = logging.getLogger(__name__)

def run_audit_agents(contract_id: str, deployment_info: dict, audit_run_id: str, source_code: str):
    """
    Orchestrates the agent pipeline for a given deployed contract.
    Writes each step's result to PostgreSQL using the audit_run_id.
    """
    db = SessionLocal()
    
    try:
        # 1. Run User Agent (Baseline Guard)
        # MUST RUN BEFORE SEEDING to ensure a pristine state where it withdraws all funds
        baseline_result = run_baseline_usage(contract_id, deployment_info)
        
        user_action = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="user_agent",
            action_description="Baseline usage check (deposit -> withdraw)",
            result=baseline_result,
            tx_hash=None
        )
        db.add(user_action)
        db.commit()
        
        # 2. Explicitly seed the contract with victim funds (accounts[4])
        # If the contract has a deposit function, call it. Otherwise, assume it was funded during deployment or doesn't need it.
        w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
        contract = w3.eth.contract(address=deployment_info["address"], abi=deployment_info["abi"])
        
        has_deposit = any(f.get("name") == "deposit" for f in deployment_info["abi"] if f.get("type") == "function")
        if has_deposit:
            victim_account = w3.eth.accounts[4]
            tx_hash = contract.functions.deposit().transact({'from': victim_account, 'value': w3.to_wei(10, 'ether')})
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            seed_action = AgentAction(
                audit_run_id=audit_run_id,
                agent_type="system_seeder",
                action_description="Seed contract with 10 ETH victim funds",
                result={"success": True, "amount": "10 ETH"},
                tx_hash=receipt.transactionHash.hex() if hasattr(receipt, 'transactionHash') else receipt.get('transactionHash', '').hex() if isinstance(receipt.get('transactionHash'), bytes) else str(receipt.get('transactionHash'))
            )
            db.add(seed_action)
            db.commit()
        else:
            seed_action = AgentAction(
                audit_run_id=audit_run_id,
                agent_type="system_seeder",
                action_description="Seed contract skipped (no deposit function, assumed funded at deploy)",
                result={"success": True, "amount": "0 ETH"},
                tx_hash=None
            )
            db.add(seed_action)
            db.commit()
        
        # 3. Run Attacker Agent
        # With funds in place, attempt the reentrancy exploit
        exploit_result = attempt_reentrancy_exploit(contract_id, deployment_info, source_code)
        
        attacker_action = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="attacker_agent",
            action_description="Attempt Reentrancy Exploit",
            result=exploit_result,
            tx_hash=None
        )
        db.add(attacker_action)
        db.commit()

        # 4. Run Flash-Loan Attacker Agent
        flashloan_result = attempt_flashloan_exploit(contract_id, deployment_info, source_code)
        
        flashloan_action = AgentAction(
            audit_run_id=audit_run_id,
            agent_type="attacker_agent",
            action_description="Attempt Flash-Loan Exploit",
            result=flashloan_result,
            tx_hash=None
        )
        db.add(flashloan_action)
        db.commit()

    finally:
        db.close()