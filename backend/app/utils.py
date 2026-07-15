import hashlib

def compute_contract_id(source_code: str) -> str:
    """Derive a stable contract_id from the normalized source code."""
    normalized = source_code.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
