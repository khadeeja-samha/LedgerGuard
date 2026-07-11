"""
Convert a tree-sitter Solidity AST into a contract graph structure.

The graph captures functions, state variables, external calls, state
reads/writes, and — critically — whether an external call occurs BEFORE
a write to a state variable (the classic reentrancy / CEI-violation
ordering signal).

Documented V1 limitations:
  - External call detection covers low-level calls only (.call,
    .delegatecall, .staticcall, .send, .transfer).  Contract-interface
    calls like token.transfer(to, amount) are NOT detected.
  - Analysis is intra-function only.  If withdraw() delegates to an
    internal helper that makes the external call, withdraw() will not
    be flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node, Tree

# Low-level call member names that transfer control externally.
_EXTERNAL_CALL_MEMBERS = frozenset({"call", "delegatecall", "staticcall", "send", "transfer"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_graph(tree: Tree, source_bytes: bytes) -> dict:
    """Build a contract graph from a parsed Solidity tree.

    Args:
        tree: A tree-sitter ``Tree`` returned by ``parse_solidity``.
        source_bytes: The original source encoded as UTF-8 bytes (needed
            to read node text).

    Returns:
        A dict with keys ``functions``, ``state_variables``, ``edges``.
    """
    contracts = _find_nodes(tree.root_node, "contract_declaration")
    if not contracts:
        return {"functions": [], "state_variables": [], "edges": []}

    # Analyse the first contract found (multi-contract files are
    # uncommon in a hackathon demo; easy to extend later).
    contract_node = contracts[0]
    body = _find_first(contract_node, "contract_body")
    if body is None:
        return {"functions": [], "state_variables": [], "edges": []}

    state_vars = _extract_state_variables(body, source_bytes)
    state_var_names = {sv["name"] for sv in state_vars}

    functions: list[dict] = []
    edges: list[dict] = []

    for func_node in _find_nodes(body, "function_definition"):
        func_info = _analyse_function(func_node, state_var_names, source_bytes)
        functions.append(func_info)

        # Build edges for any external call that precedes a state write.
        for ext_call in func_info["external_calls"]:
            if ext_call["before_state_write"]:
                # Find which state variables are written after this call.
                for var_name in func_info["_writes_after_ext_call"]:
                    edges.append({
                        "type": "MAKES_EXTERNAL_CALL_BEFORE_STATE_UPDATE",
                        "from": func_info["name"],
                        "to": var_name,
                    })

        # Remove internal bookkeeping key before returning.
        func_info.pop("_writes_after_ext_call", None)

    return {
        "functions": functions,
        "state_variables": state_vars,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# State variable extraction
# ---------------------------------------------------------------------------

def _extract_state_variables(body: Node, source_bytes: bytes) -> list[dict]:
    """Extract state variable declarations from a contract body."""
    results: list[dict] = []
    for sv_node in _find_nodes(body, "state_variable_declaration"):
        name = _text(_find_first(sv_node, "identifier"), source_bytes)
        type_node = _find_first(sv_node, "type_name")
        type_str = _text(type_node, source_bytes) if type_node else "unknown"
        if name:
            results.append({"name": name, "type": type_str})
    return results


# ---------------------------------------------------------------------------
# Function analysis
# ---------------------------------------------------------------------------

def _analyse_function(
    func_node: Node,
    state_var_names: set[str],
    source_bytes: bytes,
) -> dict:
    """Analyse a single function definition.

    Returns a dict with name, visibility, is_payable, reads, writes,
    external_calls (each with before_state_write), and a private
    ``_writes_after_ext_call`` set used by the caller to build edges.
    """
    name = _text(_find_first(func_node, "identifier"), source_bytes) or ""
    visibility = _extract_visibility(func_node, source_bytes)
    is_payable = _extract_is_payable(func_node, source_bytes)

    body_node = _find_first(func_node, "function_body")
    if body_node is None:
        return {
            "name": name,
            "visibility": visibility,
            "is_payable": is_payable,
            "reads": [],
            "writes": [],
            "external_calls": [],
            "_writes_after_ext_call": set(),
        }

    # Flatten all statements into source order.
    flat_stmts = _flatten_statements(body_node)

    # Classify each statement.
    reads: set[str] = set()
    writes: set[str] = set()
    # Each entry: (stmt_index, target_text)
    external_calls_positions: list[tuple[int, str]] = []
    # Each entry: (stmt_index, variable_name)
    state_write_positions: list[tuple[int, str]] = []

    for idx, stmt_node in enumerate(flat_stmts):
        stmt_reads, stmt_writes = _classify_state_access(stmt_node, state_var_names, source_bytes)
        reads.update(stmt_reads)
        writes.update(stmt_writes)

        if stmt_writes:
            for var in stmt_writes:
                state_write_positions.append((idx, var))

        ext_targets = _find_external_calls(stmt_node, source_bytes)
        for target in ext_targets:
            external_calls_positions.append((idx, target))

    # Determine ordering: for each external call, does any state write
    # come AFTER it?
    external_calls_output: list[dict] = []
    writes_after_ext_call: set[str] = set()

    for call_idx, target in external_calls_positions:
        later_writes = [
            var for (write_idx, var) in state_write_positions
            if write_idx > call_idx
        ]
        before_state_write = len(later_writes) > 0
        external_calls_output.append({
            "target": target,
            "before_state_write": before_state_write,
        })
        if before_state_write:
            writes_after_ext_call.update(later_writes)

    return {
        "name": name,
        "visibility": visibility,
        "is_payable": is_payable,
        "reads": sorted(reads),
        "writes": sorted(writes),
        "external_calls": external_calls_output,
        "_writes_after_ext_call": writes_after_ext_call,
    }


def _extract_visibility(func_node: Node, source_bytes: bytes) -> str:
    """Extract the visibility keyword from a function definition."""
    vis_node = _find_first(func_node, "visibility")
    if vis_node is None:
        return "internal"  # Solidity default
    return _text(vis_node, source_bytes).strip()


def _extract_is_payable(func_node: Node, source_bytes: bytes) -> bool:
    """Check whether the function has the ``payable`` state mutability."""
    mut_node = _find_first(func_node, "state_mutability")
    if mut_node is None:
        return False
    return _text(mut_node, source_bytes).strip() == "payable"


# ---------------------------------------------------------------------------
# Statement flattening
# ---------------------------------------------------------------------------

def _flatten_statements(body_node: Node) -> list[Node]:
    """Recursively collect all leaf statements in source order.

    Walks into ``if_statement``, ``for_statement``, ``while_statement``,
    ``block`` (``function_body``) nodes to find the actual expression /
    variable-declaration statements inside, sorted by source position.
    This is conservative: both branches of an if/else are included.
    """
    stmts: list[Node] = []
    _collect_stmts(body_node, stmts)
    stmts.sort(key=lambda n: (n.start_point[0], n.start_point[1]))
    return stmts


_CONTAINER_TYPES = frozenset({
    "function_body", "block", "statement",
    "if_statement", "else_clause",
    "for_statement", "while_statement", "do_while_statement",
    "try_statement", "catch_clause",
    "unchecked_block",
})

_LEAF_STMT_TYPES = frozenset({
    "expression_statement",
    "variable_declaration_statement",
    "return_statement",
    "emit_statement",
    "revert_statement",
})


def _collect_stmts(node: Node, acc: list[Node]) -> None:
    """Recursively walk into container nodes, collecting leaf statements."""
    if node.type in _LEAF_STMT_TYPES:
        acc.append(node)
        return
    if node.type in _CONTAINER_TYPES or node.type == "contract_body":
        for child in node.children:
            _collect_stmts(child, acc)


# ---------------------------------------------------------------------------
# State access classification
# ---------------------------------------------------------------------------

def _classify_state_access(
    stmt_node: Node,
    state_var_names: set[str],
    source_bytes: bytes,
) -> tuple[set[str], set[str]]:
    """Determine which state variables a statement reads and writes.

    Returns (reads, writes) as sets of variable names.
    """
    reads: set[str] = set()
    writes: set[str] = set()

    # Find all assignment expressions (= and +=, -=, etc.)
    assignments = _find_nodes(stmt_node, "assignment_expression")
    assignments.extend(_find_nodes(stmt_node, "augmented_assignment_expression"))

    written_lhs_nodes: list[Node] = []
    for assign in assignments:
        lhs = _get_assignment_lhs(assign)
        if lhs is not None:
            written_lhs_nodes.append(lhs)
            lhs_vars = _extract_state_var_refs(lhs, state_var_names, source_bytes)
            writes.update(lhs_vars)

    # Everything else that references a state variable is a read.
    all_refs = _extract_state_var_refs(stmt_node, state_var_names, source_bytes)
    reads = all_refs - writes

    # For augmented assignments (+=, -=), the LHS is also read.
    for assign in _find_nodes(stmt_node, "augmented_assignment_expression"):
        lhs = _get_assignment_lhs(assign)
        if lhs is not None:
            lhs_vars = _extract_state_var_refs(lhs, state_var_names, source_bytes)
            reads.update(lhs_vars)

    return reads, writes


def _get_assignment_lhs(assign_node: Node) -> Node | None:
    """Get the LHS expression node of an assignment.

    In tree-sitter-solidity, the first ``expression`` child of an
    assignment_expression or augmented_assignment_expression is the LHS.
    """
    for child in assign_node.children:
        if child.type == "expression":
            return child
    return None


def _extract_state_var_refs(
    node: Node,
    state_var_names: set[str],
    source_bytes: bytes,
) -> set[str]:
    """Find all references to known state variable names within a subtree."""
    refs: set[str] = set()
    _walk_for_state_refs(node, state_var_names, source_bytes, refs)
    return refs


def _walk_for_state_refs(
    node: Node,
    state_var_names: set[str],
    source_bytes: bytes,
    acc: set[str],
) -> None:
    """Recursively walk a subtree looking for identifier nodes that match
    known state variable names."""
    if node.type == "identifier":
        name = _text(node, source_bytes)
        if name in state_var_names:
            acc.add(name)
        return
    for child in node.children:
        _walk_for_state_refs(child, state_var_names, source_bytes, acc)


# ---------------------------------------------------------------------------
# External call detection
# ---------------------------------------------------------------------------

def _find_external_calls(stmt_node: Node, source_bytes: bytes) -> list[str]:
    """Find external low-level calls in a statement.

    Returns a list of target strings (e.g., "msg.sender") for each
    external call found.

    Detects patterns:
      1. call_expression whose callee is struct_expression wrapping a
         member_expression ending in .call/.delegatecall/.staticcall
         (the {value: ...} syntax).
      2. call_expression whose callee is a member_expression ending in
         .transfer/.send (no options block).
    """
    targets: list[str] = []
    _walk_for_external_calls(stmt_node, source_bytes, targets)
    return targets


def _walk_for_external_calls(
    node: Node,
    source_bytes: bytes,
    acc: list[str],
) -> None:
    """Recursively search for external call patterns."""
    if node.type == "call_expression":
        target = _check_external_call(node, source_bytes)
        if target is not None:
            acc.append(target)
            return  # Don't recurse into the call's children.

    for child in node.children:
        _walk_for_external_calls(child, source_bytes, acc)


def _check_external_call(call_node: Node, source_bytes: bytes) -> str | None:
    """Check if a call_expression is an external low-level call.

    Returns the target string (e.g., "msg.sender") or None.
    """
    # The callee is the first expression child, or the struct_expression.
    callee = _get_callee(call_node)
    if callee is None:
        return None

    # Unwrap any generic 'expression' wrapper nodes.
    callee = _unwrap_expression(callee)

    # Pattern 1: struct_expression wrapping member_expression
    # e.g., msg.sender.call{value: amount}("")
    if callee.type == "struct_expression":
        member_expr = _find_first(callee, "member_expression")
        if member_expr is not None:
            return _check_member_is_external(member_expr, source_bytes)

    # Pattern 2: direct member_expression (no options block)
    # e.g., addr.transfer(amount) or addr.send(amount)
    if callee.type == "member_expression":
        return _check_member_is_external(callee, source_bytes)

    return None


def _check_member_is_external(member_node: Node, source_bytes: bytes) -> str | None:
    """Check if a member_expression's terminal identifier is an external
    call keyword.  Returns the target (the object being called on) or None."""
    # The member_expression has children:
    #   expression (the object), ".", identifier (the member name)
    # Find the last identifier child — that's the member name.
    member_name_node = None
    object_node = None
    for child in member_node.children:
        if child.type == "identifier":
            member_name_node = child
        elif child.type in ("expression", "member_expression"):
            object_node = child

    if member_name_node is None:
        return None

    member_name = _text(member_name_node, source_bytes)
    if member_name not in _EXTERNAL_CALL_MEMBERS:
        return None

    # Extract the target text (the object before .call/.transfer/etc.)
    if object_node is not None:
        # Unwrap expression wrapper to get the actual content for target text.
        unwrapped = _unwrap_expression(object_node)
        return _text(unwrapped, source_bytes)

    return None


def _get_callee(call_node: Node) -> Node | None:
    """Extract the callee expression from a call_expression.

    In tree-sitter-solidity, the callee is the first child that is
    an expression, member_expression, struct_expression, or identifier.
    """
    for child in call_node.children:
        if child.type in (
            "expression", "member_expression", "struct_expression",
            "identifier", "array_access",
        ):
            return child
    return None


def _unwrap_expression(node: Node) -> Node:
    """Peel off generic ``expression`` wrapper nodes.

    tree-sitter-solidity frequently wraps concrete node types (e.g.,
    ``struct_expression``, ``member_expression``) inside a generic
    ``expression`` node.  This helper recursively unwraps until it
    reaches a non-``expression`` node.
    """
    while node.type == "expression" and node.child_count == 1:
        node = node.children[0]
    return node


# ---------------------------------------------------------------------------
# Tree traversal helpers
# ---------------------------------------------------------------------------

def _find_nodes(root: Node, node_type: str) -> list[Node]:
    """Find all descendant nodes of a given type (BFS)."""
    results: list[Node] = []
    queue = list(root.children)
    while queue:
        node = queue.pop(0)
        if node.type == node_type:
            results.append(node)
        queue.extend(node.children)
    return results


def _find_first(root: Node, node_type: str) -> Node | None:
    """Find the first descendant node of a given type (BFS)."""
    queue = list(root.children)
    while queue:
        node = queue.pop(0)
        if node.type == node_type:
            return node
        queue.extend(node.children)
    return None


def _text(node: Node | None, source_bytes: bytes) -> str:
    """Extract the UTF-8 text of a node."""
    if node is None:
        return ""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")
