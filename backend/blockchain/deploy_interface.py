import os
import time
import json
import shutil
import requests
import subprocess
from pathlib import Path

class NodeNotReadyError(Exception):
    pass

class DeploymentError(Exception):
    pass

BLOCKCHAIN_DIR = Path(__file__).parent
CONTRACTS_DIR = BLOCKCHAIN_DIR / "contracts"
DEPLOYMENTS_DIR = BLOCKCHAIN_DIR / "deployments"
RPC_URL = "http://127.0.0.1:8545"

def check_node_ready(timeout: int = 10, interval: float = 0.5):
    """
    Polls the local Hardhat RPC endpoint (eth_chainId) to ensure it's fully ready.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.post(
                RPC_URL,
                json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
                timeout=1
            )
            if response.status_code == 200 and "result" in response.json():
                return
        except requests.exceptions.RequestException:
            pass
        time.time()
        time.sleep(interval)
    
    raise NodeNotReadyError(f"Hardhat node at {RPC_URL} not ready after {timeout} seconds.")

def deploy_contract(contract_name: str, source_code: str) -> dict:
    """
    Deploys a contract by compiling it dynamically and running Hardhat deployment.
    """
    check_node_ready()

    # 1. Wipe old contracts and deployments to prevent artifact collision
    if CONTRACTS_DIR.exists():
        shutil.rmtree(CONTRACTS_DIR)
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    
    deployment_file = DEPLOYMENTS_DIR / f"{contract_name}.json"
    if deployment_file.exists():
        deployment_file.unlink()

    # 2. Write new source
    contract_path = CONTRACTS_DIR / f"{contract_name}.sol"
    contract_path.write_text(source_code)

    # 3. Compile and Deploy via Hardhat
    env = os.environ.copy()
    env["CONTRACT_NAME"] = contract_name

    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    try:
        subprocess.run(
            [npx_cmd, "hardhat", "run", "scripts/deploy.js", "--network", "localhost"],
            cwd=str(BLOCKCHAIN_DIR),
            env=env,
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Deployment failed with exit code {e.returncode}.\nStdout:\n{e.stdout}\nStderr:\n{e.stderr}")

    # 4. Verify and return output
    if not deployment_file.exists():
        raise DeploymentError(f"Deployment succeeded but JSON output file {deployment_file} is missing.")
    
    try:
        data = json.loads(deployment_file.read_text())
    except json.JSONDecodeError as e:
        raise DeploymentError(f"Failed to parse deployment JSON output: {e}")

    if not data.get("success") or not data.get("address"):
        raise DeploymentError(f"Deployment JSON missing success flag or address: {data}")

<<<<<<< HEAD
    return data
=======
    return data
>>>>>>> 81b59a06fe5f34041a73f5a97991e4a4320ffc28
