import pytest
from pathlib import Path
from web3 import Web3
from blockchain.deploy_interface import deploy_contract, DeploymentError

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_contract_deploys_and_is_callable(hardhat_node):
    """
    Primary Gate Test:
    Proves real on-chain state change by compiling, deploying,
    reading state, writing state (depositing ETH), and asserting changes.
    """
    # 1. Read fixture source
    fixture_path = FIXTURES_DIR / "vulnerable_bank.sol"
    source_code = fixture_path.read_text()

    # 2. Deploy dynamically
    contract_name = "VulnerableBank"  # The main contract inside vulnerable_bank.sol
    deployment = deploy_contract(contract_name, source_code)
    
    assert deployment["success"] is True
    address = deployment["address"]
    abi = deployment["abi"]
    assert address.startswith("0x")
    
    # 3. Connect Web3
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
    assert w3.is_connected(), "Web3 could not connect to local node"
    
    # 4. Setup contract and accounts
    contract = w3.eth.contract(address=address, abi=abi)
    accounts = w3.eth.accounts
    depositor = accounts[1]  # Use second account
    
    # 5. READ: initial balance should be 0
    initial_balance = contract.functions.balances(depositor).call()
    print(f"\nInitial Balance: {initial_balance} wei ({w3.from_wei(initial_balance, 'ether')} ETH)")
    assert initial_balance == 0
    
    # 6. WRITE: Deposit 1 ETH
    deposit_amount = w3.to_wei(1, "ether")
    print(f"Depositing {deposit_amount} wei (1 ETH)...")
    tx_hash = contract.functions.deposit().transact({
        "from": depositor,
        "value": deposit_amount
    })
    
    # Wait for tx receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt.status == 1, "Deposit transaction failed"
    
    # 7. READ: verify balance increased
    final_balance = contract.functions.balances(depositor).call()
    print(f"Final Balance: {final_balance} wei ({w3.from_wei(final_balance, 'ether')} ETH)")
    assert final_balance == deposit_amount


def test_deployment_failure_is_detected(hardhat_node):
    """
    Tests that a syntax error in the contract source code
    raises a proper DeploymentError due to compilation failure.
    """
    bad_source = "pragma solidity ^0.8.24; contract Broken { syntax error }"
    
    with pytest.raises(DeploymentError) as exc_info:
        deploy_contract("BrokenBank", bad_source)
    
    error_message = str(exc_info.value)
    print(f"\nCaught Expected DeploymentError:\n{error_message}")
    assert "exit code 1" in error_message.lower()
