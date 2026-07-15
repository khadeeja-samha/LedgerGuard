import logging
from web3 import Web3

logger = logging.getLogger(__name__)

def run_baseline_usage(contract_id: str, deployment_info: dict) -> dict:
    """
    Executes a baseline sequence of normal user transactions against the deployed contract
    to verify its functional correctness deterministically, independently of the LLM.
    
    This acts as our "false-positive guard". It proves that the normal flow works
    (deposit -> check -> withdraw -> check) without any AI reasoning involvement.
    
    Args:
        contract_id: SHA-256 hex digest identifying the contract.
        deployment_info: Dict containing 'address' and 'abi'.
        
    Returns:
        A dict with 'steps' (log of balances) and 'all_correct' (bool).
    """
    # Explicitly connect to the local Hardhat node to guarantee network isolation,
    # matching the environment where the victim is deployed.
    w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:8545'))
    
    if not w3.is_connected():
        return {
            "all_correct": False,
            "error": "Failed to connect to local Hardhat node at http://127.0.0.1:8545",
            "steps": []
        }
        
    address = deployment_info.get("address")
    abi = deployment_info.get("abi")
    
    if not address or not abi:
        return {
            "all_correct": False,
            "error": "Missing address or ABI in deployment_info",
            "steps": []
        }
        
    contract = w3.eth.contract(address=address, abi=abi)
    
    # We explicitly use accounts[2] as our "normal user". 
    # accounts[0] = default deployer
    # accounts[1] = typically the attacker (via ethers.getSigners() in the agent script)
    # accounts[2] = normal user (this script)
    # This guarantees state isolation from the GenericAttacker test runs.
    if len(w3.eth.accounts) <= 2:
        return {
            "all_correct": False,
            "error": "Not enough accounts available on the local node (need at least 3)",
            "steps": []
        }
        
    user_account = w3.eth.accounts[2]
    
    # Check if the contract supports deposit/withdraw (e.g. Bank contracts vs AMMs)
    has_deposit = any(f.get("name") == "deposit" for f in abi if f.get("type") == "function")
    has_withdraw = any(f.get("name") == "withdraw" for f in abi if f.get("type") == "function")
    
    if not (has_deposit and has_withdraw):
        logger.info(f"Contract {address} does not support deposit/withdraw. Skipping baseline usage.")
        return {
            "all_correct": True,
            "steps": [{"step": "skipped", "reason": "No deposit/withdraw functions in ABI"}]
        }

    steps = []
    all_correct = True
    
    try:
        # Step 0: Check initial balance
        initial_balance_wei = contract.functions.balances(user_account).call()
        initial_balance_eth = w3.from_wei(initial_balance_wei, 'ether')
        steps.append({"step": "initial", "balance_eth": float(initial_balance_eth)})
        
        # Step 1: Deposit 1 ETH
        deposit_amount_wei = w3.to_wei(1, 'ether')
        tx_hash = contract.functions.deposit().transact({
            'from': user_account,
            'value': deposit_amount_wei
        })
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Step 2: Check balance after deposit
        post_deposit_balance_wei = contract.functions.balances(user_account).call()
        post_deposit_balance_eth = w3.from_wei(post_deposit_balance_wei, 'ether')
        steps.append({"step": "post_deposit", "balance_eth": float(post_deposit_balance_eth)})
        
        if post_deposit_balance_wei != (initial_balance_wei + deposit_amount_wei):
            all_correct = False
            
        # Step 3: Withdraw (ALL)
        tx_hash = contract.functions.withdraw().transact({
            'from': user_account
        })
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Step 4: Check balance after withdraw
        post_withdraw_balance_wei = contract.functions.balances(user_account).call()
        post_withdraw_balance_eth = w3.from_wei(post_withdraw_balance_wei, 'ether')
        steps.append({"step": "post_withdraw", "balance_eth": float(post_withdraw_balance_eth)})
        
        if post_withdraw_balance_wei != 0:
            all_correct = False
            
    except Exception as e:
        return {
            "all_correct": False,
            "error": str(e),
            "steps": steps
        }

    return {
        "all_correct": all_correct,
        "steps": steps
    }