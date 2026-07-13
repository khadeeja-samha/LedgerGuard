import pytest
import hashlib
from pathlib import Path
from app.parser.solidity_parser import parse_solidity
from app.parser.graph_builder import build_graph
from app.db.neo4j_client import NeoClient
from blockchain.deploy_interface import deploy_contract
from app.agents.attacker_agent import attempt_reentrancy_exploit
from app.agents.user_agent import run_baseline_usage

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_attacker_exploits_vulnerable_contract(hardhat_node):
    """
    Test that the attacker agent successfully exploits a known vulnerable contract,
    and that the User Agent confirms the contract is otherwise functionally correct.
    """
    source_code = (FIXTURES_DIR / "vulnerable_bank.sol").read_text()
    
    # 1. Parse and write graph
    contract_id = hashlib.sha256(source_code.encode("utf-8")).hexdigest()
    ast = parse_solidity(source_code)
    graph = build_graph(ast, source_code.encode("utf-8"))
    
    neo_client = NeoClient()
    neo_client.write_graph(contract_id, graph)
    
    # 2. Deploy contract
    deployment_info = deploy_contract("VulnerableBank", source_code)
    assert deployment_info["success"] is True, "Deployment failed"
    
    # 3. Run baseline guard
    # MUST RUN BEFORE SEEDING: We run the User Agent baseline check first.
    # The User Agent relies on accounts[2] and executes a deposit -> check -> withdraw_all -> check sequence.
    # Since it withdraws all its funds, it leaves the contract balance at 0.
    baseline_result = run_baseline_usage(contract_id, deployment_info)
    assert baseline_result["all_correct"] is True, "Baseline usage failed"
    
    # 4. Seed the contract with victim funds
    # MUST RUN BEFORE EXPLOIT: Since the User Agent leaves the contract empty, we must 
    # explicitly deposit victim funds before the Attacker Agent runs. Otherwise, the reentrancy
    # loop will fail (revert) when it tries to steal funds that don't exist, leading to a false EXPLOIT_BLOCKED.
    # 
    # Account Isolation:
    # - accounts[0]: default deployer (used by deploy_contract)
    # - accounts[1]: Attacker (used internally by GenericAttacker in the agent script)
    # - accounts[2]: User Agent (used by run_baseline_usage)
    # - accounts[4]: Victim Seeder (used strictly here for seeding funds)
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
    contract = w3.eth.contract(address=deployment_info["address"], abi=deployment_info["abi"])
    victim_account = w3.eth.accounts[4]
    tx_hash = contract.functions.deposit().transact({'from': victim_account, 'value': w3.to_wei(10, 'ether')})
    w3.eth.wait_for_transaction_receipt(tx_hash)
    
    # 5. Attempt exploit
    exploit_res = attempt_reentrancy_exploit(contract_id, deployment_info, source_code)
    results = exploit_res.get("results", [])
    
    # Find the result for the 'withdraw' function
    withdraw_result = next((r for r in results if r.get("function_name") == "withdraw"), None)
    assert withdraw_result is not None, "No exploit result found for 'withdraw' function"
    
    # 5. Assertions
    assert withdraw_result["exploit_outcome"] == "EXPLOIT_SUCCEEDED"
    # drained_amount is best-effort from LLM test title parsing, may be None
    if withdraw_result.get("drained_amount"):
        print(f"\n[VulnerableBank] Drained Amount: {withdraw_result['drained_amount']}")
    else:
        print(f"\n[VulnerableBank] Exploit Succeeded (drained amount not parsed from title)")

def test_attacker_fails_against_safe_contract(hardhat_node):
    """
    Test that a safe contract (no vulnerable edges) returns an empty result set,
    bypassing the LLM entirely.
    """
    source_code = (FIXTURES_DIR / "safe_bank.sol").read_text()
    
    # 1. Parse and write graph
    contract_id = hashlib.sha256(source_code.encode("utf-8")).hexdigest()
    ast = parse_solidity(source_code)
    graph = build_graph(ast, source_code.encode("utf-8"))
    
    neo_client = NeoClient()
    neo_client.write_graph(contract_id, graph)
    
    # 2. Deploy contract
    deployment_info = deploy_contract("SafeBank", source_code)
    assert deployment_info["success"] is True, "Deployment failed"
    
    # 3. Attempt exploit
    exploit_res = attempt_reentrancy_exploit(contract_id, deployment_info, source_code)
    
    # 4. Assertions
    assert exploit_res.get("results") == [], "Expected empty results for safe contract"
    assert "No functions flagged" in exploit_res.get("summary", ""), "Expected summary message about no flagged functions"
    print("\n[SafeBank] Exploit attempt correctly bypassed LLM and returned empty results.")
