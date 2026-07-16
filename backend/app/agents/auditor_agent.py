import logging
from app.db.neo4j_client import NeoClient
from app.db.postgres_client import SessionLocal, AgentAction
from app.llm.nim_client import NimClient

logger = logging.getLogger(__name__)

def _compute_deterministic_risk(edge_type: str, exploit_outcome: str) -> tuple[str, str, int]:
    """
    Deterministically computes attack type, risk level, and risk score.
    
    Args:
        edge_type: The Neo4j relationship type string.
        exploit_outcome: The recorded result from the attacker agent (or "MISSING_LOG").
        
    Returns:
        (attack_type, risk_level, risk_score)
    """
    if edge_type == "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE":
        attack_type = "reentrancy"
    elif edge_type == "USES_MANIPULABLE_PRICE_SOURCE":
        attack_type = "flashloan"
    else:
        attack_type = "unknown"

    if exploit_outcome == "EXPLOIT_SUCCEEDED":
        risk_level = "high"
        risk_score = 9
    elif exploit_outcome == "EXPLOIT_BLOCKED":
        risk_level = "low"
        risk_score = 2
    else:
        # SCRIPT_ERROR, CLASSIFICATION_INCONCLUSIVE, MISSING_LOG, etc.
        risk_level = "unknown"
        risk_score = 5
        
    return attack_type, risk_level, risk_score


def generate_findings(audit_run_id: str, contract_id: str) -> list[dict]:
    """
    Reads the Neo4j graph and Postgres action logs to compute risk scores deterministically,
    then uses NimClient to generate an English explanation for each finding.
    """
    neo_client = NeoClient()
    graph = neo_client.read_graph(contract_id)
    
    # Filter for only relevant edges
    target_edge_types = {
        "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE",
        "USES_MANIPULABLE_PRICE_SOURCE"
    }
    flagged_edges = [e for e in graph.get("edges", []) if e.get("type") in target_edge_types]
    
    if not flagged_edges:
        return []

    # Map Postgres actions: (function_name, attack_type) -> exploit_outcome
    db = SessionLocal()
    action_map = {}
    try:
        actions = db.query(AgentAction).filter_by(
            audit_run_id=audit_run_id, 
            agent_type="attacker_agent"
        ).all()
        
        for action in actions:
            if not action.result:
                continue
                
            desc = action.action_description or ""
            if "Reentrancy" in desc:
                act_type = "reentrancy"
            elif "Flash-Loan" in desc:
                act_type = "flashloan"
            else:
                continue
                
            results_list = action.result.get("results", [])
            for res in results_list:
                func_name = res.get("function_name")
                outcome = res.get("exploit_outcome")
                if func_name and outcome:
                    action_map[(func_name, act_type)] = outcome
    finally:
        db.close()

    nim_client = NimClient()
    findings = []
    
    for edge in flagged_edges:
        func_name = edge.get("from")
        edge_type = edge.get("type")
        
        if not func_name or not edge_type:
            continue
            
        # Determine attack_type deterministically based on edge_type first
        attack_type, _, _ = _compute_deterministic_risk(edge_type, "MISSING_LOG")
        
        # Look up outcome
        exploit_outcome = action_map.get((func_name, attack_type))
        if not exploit_outcome:
            exploit_outcome = "MISSING_LOG"
            logger.info(f"No attacker action logged for function '{func_name}' (attack: {attack_type}). Defaulting to MISSING_LOG.")
        elif exploit_outcome == "SCRIPT_ERROR":
            logger.warning(f"Attacker action for function '{func_name}' (attack: {attack_type}) resulted in SCRIPT_ERROR.")

        # Compute risk score deterministically
        _, risk_level, risk_score = _compute_deterministic_risk(edge_type, exploit_outcome)
        
        # Prepare context and prompt LLM
        system_prompt = (
            "You are a smart contract auditor generating a final finding description. "
            "You will be given the function name, edge type, attack type, exploit outcome, "
            "and an EXACT risk_score and risk_level. "
            "Your ONLY task is to write a plain-English, one-paragraph explanation of the finding. "
            "DO NOT modify the risk score or level. "
            "DO NOT generate any markdown or JSON, just output the plain text paragraph."
        )
        
        user_prompt = (
            f"Function: {func_name}\n"
            f"Edge Type: {edge_type}\n"
            f"Attack Type: {attack_type}\n"
            f"Exploit Outcome: {exploit_outcome}\n"
            f"Risk Level: {risk_level}\n"
            f"Risk Score: {risk_score}\n\n"
            "Generate the explanation:"
        )
        
        try:
            description = nim_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=12288
            )
        except Exception as e:
            logger.error(f"LLM generation failed for {func_name}: {e}")
            description = "Description generation failed due to LLM error."
        
        findings.append({
            "function_name": func_name,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "description": description,
            "attack_type": attack_type
        })
        
    return findings
