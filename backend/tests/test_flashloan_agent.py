import pytest
from pathlib import Path
from app.parser.solidity_parser import parse_solidity
from app.utils import compute_contract_id
from app.parser.graph_builder import build_graph
from app.db.neo4j_client import NeoClient
from blockchain.deploy_interface import deploy_contract
from app.agents.attacker_agent import attempt_flashloan_exploit

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_flashloan_exploits_vulnerable_pool(hardhat_node):
    """
    Test that the flashloan attacker agent successfully exploits the vulnerable pool.
    """
    source_code = (FIXTURES_DIR / "vulnerable_pool.sol").read_text()
    
    # 1. Parse and write graph
    contract_id = compute_contract_id(source_code)
    ast = parse_solidity(source_code)
    graph = build_graph(ast, source_code.encode("utf-8"))
    
    neo_client = NeoClient()
    neo_client.write_graph(contract_id, graph)
    
    # 2. Deploy contract
    deployment_info = deploy_contract("VulnerablePool", source_code)
    assert deployment_info["success"] is True, "Deployment failed"
    
    # 3. Run the flash loan exploit attempt
    result = attempt_flashloan_exploit(contract_id, deployment_info, source_code)
    
    # Find claimReward in the results
    claim_reward_result = None
    for r in result.get("results", []):
        if r["function_name"] == "claimReward":
            claim_reward_result = r
            break
            
    assert claim_reward_result is not None, "claimReward was not flagged by the LLM filter!"
    assert claim_reward_result["exploit_outcome"] == "EXPLOIT_SUCCEEDED"


def test_flashloan_fails_against_safe_pool(hardhat_node):
    """
    Test that the flashloan attacker agent either filters out or fails to exploit the safe pool.
    """
    source_code = (FIXTURES_DIR / "safe_pool.sol").read_text()
    
    contract_id = compute_contract_id(source_code)
    ast = parse_solidity(source_code)
    graph = build_graph(ast, source_code.encode("utf-8"))
    
    neo_client = NeoClient()
    neo_client.write_graph(contract_id, graph)
    
    deployment_info = deploy_contract("SafePool", source_code)
    assert deployment_info["success"] is True, "Deployment failed"
    
    result = attempt_flashloan_exploit(contract_id, deployment_info, source_code)
    
    # Check claimReward result
    claim_reward_result = None
    for r in result.get("results", []):
        if r["function_name"] == "claimReward":
            claim_reward_result = r
            break
            
    # Stage 2 might correctly filter it out entirely because it's a fixed TWAP price.
    # If it DOES proceed to exploit execution, the outcome MUST be EXPLOIT_BLOCKED.
    if claim_reward_result is not None:
        assert claim_reward_result["exploit_outcome"] == "EXPLOIT_BLOCKED"
