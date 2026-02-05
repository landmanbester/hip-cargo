"""Utilities for reading and writing YAML with comment preservation."""

import re
from pathlib import Path


def extract_yaml_comments(yaml_file: Path) -> dict[str, str]:
    """
    Extract inline comments from YAML file.

    Returns a dict mapping line content to comments.
    For example: "The cab will have..." -> "# noqa: E501"

    Args:
        yaml_file: Path to YAML file

    Returns:
        Dict mapping text content to inline comments
    """
    comments = {}

    with open(yaml_file) as f:
        for line in f:
            # Look for inline comments (text followed by  #comment)
            # Pattern: content  # comment
            match = re.match(r"^(.+?)\s\s(#.+)$", line)
            if match:
                content = match.group(1).strip()
                comment = match.group(2).strip()
                comments[content] = comment

    return comments


def add_inline_comment_to_string(text: str, comment: str) -> str:
    """
    Add a comment marker to text so format_info_fields can place it correctly.

    Args:
        text: The info text
        comment: The comment (with # prefix)

    Returns:
        Text with comment marker
    """
    return f"{text}  {comment}"
