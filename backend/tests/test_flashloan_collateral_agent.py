from pathlib import Path
from blockchain.deploy_interface import deploy_contract
from app.agents.flashloan_exploit_runner import run_flashloan_collateral_exploit

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_exploit_succeeds_against_vulnerable_lending_pool(hardhat_node):
    source_code = (FIXTURES_DIR / "mock_lending_pool_vulnerable.sol").read_text()
    deployment_info = deploy_contract("MockLendingPoolVulnerable", source_code)
    assert deployment_info["success"] is True, "Deployment failed"

    result = run_flashloan_collateral_exploit("MockLendingPoolVulnerable")

    assert result["error"] is None, f"Script error: {result['error']}"
    assert result["outcome"] == "EXPLOIT_SUCCEEDED"
    assert result["collateral_paid"] < result["fair_collateral"]
    print(
        f"\n[Vulnerable] Paid {result['collateral_paid']} vs fair {result['fair_collateral']} "
        f"at manipulated price {result['manipulated_price']}"
    )


def test_exploit_blocked_against_safe_lending_pool(hardhat_node):
    source_code = (FIXTURES_DIR / "mock_lending_pool_safe.sol").read_text()
    deployment_info = deploy_contract("MockLendingPoolSafe", source_code)
    assert deployment_info["success"] is True, "Deployment failed"

    result = run_flashloan_collateral_exploit("MockLendingPoolSafe")

    assert result["error"] is None, f"Script error: {result['error']}"
    assert result["outcome"] == "EXPLOIT_BLOCKED"
    print(f"\n[Safe] Outcome: {result['outcome']}")