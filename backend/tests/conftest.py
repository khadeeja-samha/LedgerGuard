import os
import sys
import subprocess
import pytest
from pathlib import Path

# Add backend dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from blockchain.deploy_interface import check_node_ready, BLOCKCHAIN_DIR

@pytest.fixture(scope="session")
def hardhat_node():
    """
    Session-scoped fixture to start the local Hardhat node,
    wait for readiness, and tear it down after tests complete.
    """
    print("\nStarting Hardhat local node...")
    
    npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
    process = subprocess.Popen(
        [npx_cmd, "hardhat", "node"],
        cwd=str(BLOCKCHAIN_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True
    )
    
    try:
        # Wait for RPC endpoint to be ready
        check_node_ready(timeout=15, interval=0.5)
        print("Hardhat node is ready.")
        yield process
    finally:
        print("\nStopping Hardhat local node...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
