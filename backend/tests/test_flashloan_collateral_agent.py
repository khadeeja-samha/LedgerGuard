from app.agents.flashloan_exploit_runner import (
    run_flashloan_collateral_exploit,
    deploy_pool_contract,
)


def test_exploit_succeeds_against_vulnerable_lending_pool(hardhat_node):
    """
    LendingPoolAttacker manipulates MockLendingPoolVulnerable's internal
    reserve-derived price during a flash loan callback, then borrows
    against artificially deflated collateral requirements.
    """
    deploy_pool_contract("MockLendingPoolVulnerable")

    result = run_flashloan_collateral_exploit("MockLendingPoolVulnerable")

    assert result["error"] is None, f"Script error: {result['error']}"
    assert result["outcome"] == "EXPLOIT_SUCCEEDED"
    assert result["collateral_paid"] < result["fair_collateral"]
    print(
        f"\n[Vulnerable] Paid {result['collateral_paid']} vs fair {result['fair_collateral']} "
        f"at manipulated price {result['manipulated_price']}"
    )


def test_exploit_blocked_against_safe_lending_pool(hardhat_node):
    """
    MockLendingPoolSafe uses a fixed oraclePrice, immune to reserve
    manipulation during the flash loan window — same attacker contract
    should fail to gain any discount here.
    """
    deploy_pool_contract("MockLendingPoolSafe")

    result = run_flashloan_collateral_exploit("MockLendingPoolSafe")

    assert result["error"] is None, f"Script error: {result['error']}"
    assert result["outcome"] == "EXPLOIT_BLOCKED"
    print(f"\n[Safe] Outcome: {result['outcome']}")