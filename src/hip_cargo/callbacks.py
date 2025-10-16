"""
Typer wildcard option support using callbacks and glob expansion.

Simple approach: Use string options with multiple=True, then expand
wildcards in a callback. Users quote the patterns to prevent shell expansion.
"""

from pathlib import Path
from typing import List, Optional, Tuple

import typer


def expand_patterns(patterns: Optional[Tuple[str, ...]]) -> List[str]:
    """
    Callback to expand glob patterns and flatten into a single list.

    Args:
        patterns: Tuple of glob patterns from multiple --option invocations

    Returns:
        Flattened list of all matching file paths

    Example:
        Input: ('test*.txt', 'exam*.txt')
        Output: ['test1.txt', 'test2.txt', 'exam1.txt', 'exam2.txt']
    """
    # import ipdb; ipdb.set_trace()
    if not patterns:
        return []

    all_files = []
    for pattern in patterns:
        matches = sorted(Path.cwd().glob(pattern))

        if not matches:
            typer.echo(f"Warning: No matches found for pattern: {pattern}", err=True)

        all_files.extend(str(m) for m in matches)

    return all_files


def make_pattern_expander(
    allow_empty: bool = True,
    sort_results: bool = True,
    warn_no_match: bool = True,
):
    """
    Factory function to create customized pattern expansion callbacks.

    Args:
        allow_empty: If False, raise error when no matches found
        sort_results: Whether to sort matches for each pattern
        warn_no_match: Whether to warn when a pattern has no matches

    Returns:
        Callback function for typer.Option

    Example:
        strict_expander = make_pattern_expander(allow_empty=False)

        files: List[str] = typer.Option(
            None,
            "--input",
            callback=strict_expander,
            ...
        )
    """

    def callback(patterns: Optional[Tuple[str, ...]]) -> List[str]:
        if not patterns:
            return []

        all_files = []

        for pattern in patterns:
            matches = list(Path.cwd().glob(pattern))

            if not matches:
                if not allow_empty:
                    raise typer.BadParameter(f"No matches found for pattern: {pattern}")
                elif warn_no_match:
                    typer.echo(f"Warning: No matches found for pattern: {pattern}", err=True)

            if sort_results:
                matches.sort()

            all_files.extend(str(m) for m in matches)

        return all_files

    return callback
