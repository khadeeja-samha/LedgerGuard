import time
import sys
import os
from app.llm.nim_client import NimClient

# Reconfigure stdout to support unicode printing on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def test_generate(client: NimClient, system_prompt: str, user_prompt: str, reasoning: bool):
    print(f"\n--- Running generate() with reasoning={reasoning} ---")
    start_time = time.time()
    try:
        response = client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            reasoning=reasoning
        )
        duration = time.time() - start_time
        print(f"Success! Duration: {duration:.2f} seconds")
        print("Response content:")
        print(response)
        print("-" * 50)
        return response
    except Exception as e:
        duration = time.time() - start_time
        print(f"Failed! Duration: {duration:.2f} seconds")
        print(f"Error: {e}")
        print("-" * 50)
        raise

def main():
    # If API key is not set, prompt the user or warn them
    api_key = os.getenv("NIM_API_KEY")
    if not api_key:
        print("WARNING: NIM_API_KEY is not set in environment or .env file.")
        print("Please set it in backend/.env before running this script.")
        print("We will attempt to proceed in case it's set in the global environment.\n")

    # System and User Prompts
    system_prompt = "You are a smart contract auditor helper."
    user_prompt = "Explain in one sentence what a reentrancy attack is, and give a very brief code snippet showing it."

    # Test Case 1 & 2: Valid client
    try:
        print("Initializing valid NimClient...")
        client = NimClient()
        
        # 1. Test reasoning=True
        test_generate(client, system_prompt, user_prompt, reasoning=True)
        
        # 2. Test reasoning=False
        test_generate(client, system_prompt, user_prompt, reasoning=False)
        
    except Exception as e:
        print(f"Test execution with valid client failed: {e}")

    # Test Case 3: Invalid API key
    print("\n--- Running Test Case 3: Deliberate Invalid API Key ---")
    try:
        invalid_client = NimClient(api_key="invalid_api_key_test_value")
        print("Invoking generate() with invalid client (expecting exception)...")
        invalid_client.generate(system_prompt, user_prompt, reasoning=False)
        print("ERROR: generate() succeeded with an invalid API key! This should not happen.")
    except Exception as e:
        print("Successfully caught expected exception for invalid API key:")
        print(f"Caught Exception: {e}")

if __name__ == "__main__":
    main()
