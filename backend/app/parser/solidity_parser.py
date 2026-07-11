"""
Thin wrapper around tree-sitter-solidity.

Accepts a Solidity source string, returns the tree-sitter Tree object.
No analysis logic lives here — that's in graph_builder.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tree_sitter_solidity
from tree_sitter import Language, Parser

if TYPE_CHECKING:
    from tree_sitter import Tree

_SOL_LANGUAGE = Language(tree_sitter_solidity.language())
_parser = Parser(_SOL_LANGUAGE)


class SolidityParseError(Exception):
    """Raised when the Solidity source cannot be parsed."""


def parse_solidity(source: str) -> Tree:
    """Parse a Solidity source string into a tree-sitter Tree.

    Args:
        source: The full text of a .sol file.

    Returns:
        A tree-sitter ``Tree`` whose ``root_node`` has type
        ``"source_file"`` containing contract / pragma / import nodes.

    Raises:
        SolidityParseError: If the parser rejects the input.
    """
    source_bytes = source.encode("utf-8")
    tree = _parser.parse(source_bytes)
    if tree.root_node.has_error:
        raise SolidityParseError("Failed to parse Solidity source: syntax errors found")
    return tree
