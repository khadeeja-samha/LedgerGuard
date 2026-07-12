import os
from pathlib import Path
from web3 import Web3
from blockchain.deploy_interface import deploy_contract
import subprocess

BLOCKCHAIN_DIR = Path(__file__).parent / "blockchain"
FIXTURES_DIR = Path(__file__).parent / "tests" / "fixtures"

def main():
    print("Starting Hardhat local node (Background)...")
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    process = subprocess.Popen(
        [npx_cmd, "hardhat", "node"],
        cwd=str(BLOCKCHAIN_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True
    )
    
    try:
        source_code = (FIXTURES_DIR / "vulnerable_bank.sol").read_text()
        print("\nDeploying vulnerable_bank.sol via Pipeline...")
        deployment = deploy_contract("VulnerableBank", source_code)
        
        address = deployment["address"]
        abi = deployment["abi"]
        print(f"Contract successfully deployed to live network at: {address}")
        
        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        contract = w3.eth.contract(address=address, abi=abi)
        test_account = w3.eth.accounts[0]
        
        balance = contract.functions.balances(test_account).call()
        print(f"\nLive Read Result: Balance for account {test_account} is {balance} wei")
        
    finally:
        print("\nStopping Hardhat local node...")
        process.terminate()

if __name__ == "__main__":
    main()
