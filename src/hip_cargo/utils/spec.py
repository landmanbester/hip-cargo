"""Intermediate representation of CLI commands shared by cab and schema generators.

A single CST walk produces a ``ModuleSpec``; both ``generate-cabs`` and
``generate-schemas`` consume the same IR. The IR is *neutral* — it carries the
structural facts of each parameter (name, type-as-string, default, typer
metadata, stimela metadata, source location) without applying cab-specific
shaping (dtype inference, hyphenation, policies). Generator-specific shaping
lives in adaptor functions next to each generator.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParamSpec:
    """Structural facts about one CLI parameter.

    Attributes:
        name: Parameter identifier as written in the function signature.
        dtype_str: Type annotation rendered as a code string (e.g. ``"File"``,
            ``"int | None"``, ``"list[float]"``). Optional/Union wrappers are
            preserved exactly as written.
        default: Python value of the default expression. ``Ellipsis`` denotes a
            required parameter (no default supplied).
        required: True iff ``default is ...`` (or no default was given at all).
        help: ``typer.Option(help=...)`` string, or ``None``.
        stimela_meta: Recursively-thawed dict from the ``StimelaMeta(...)``
            (or legacy ``{"stimela": {...}}``) entry in ``Annotated``. Empty
            dict if absent.
        raw_typer_meta: Full kwargs+default extracted from
            ``typer.Option(...)`` / ``typer.Argument(...)``.
        inline_comment: Inline comment attached to the ``help=`` kwarg, if any
            (e.g. ``"# noqa: E501"``).
        line: 1-based line number of the parameter in its source module, used
            for diagnostics.
    """

    name: str
    dtype_str: str
    default: Any
    required: bool
    help: str | None
    stimela_meta: dict[str, Any] = field(default_factory=dict)
    raw_typer_meta: dict[str, Any] = field(default_factory=dict)
    inline_comment: str | None = None
    line: int | None = None

    @property
    def is_tunable(self) -> bool:
        """True iff this parameter carries ``metadata.tunable=True``.

        Stimela has a finite set of allowed top-level fields on a parameter
        definition, so the ``tunable`` flag lives inside the ``metadata`` dict
        — the dedicated escape hatch for arbitrary metadata.
        """
        meta = self.stimela_meta.get("metadata") or {}
        return bool(meta.get("tunable", False))


@dataclass(frozen=True)
class CommandSpec:
    """One ``@stimela_cab``-decorated function in a CLI module.

    Attributes:
        name: Function name (matches ``cli_function.__name__``).
        module_path: Source ``.py`` path containing the function.
        decorators: Parsed decorators keyed by name. Each value carries
            ``{"args": [...], "kwargs": {...}}`` per ``parse_decorator_libcst``.
        params: All function parameters in declaration order.
        line: 1-based line of the ``def`` statement.
    """

    name: str
    module_path: Path
    decorators: dict[str, dict[str, Any]]
    params: tuple[ParamSpec, ...]
    line: int | None = None

    @property
    def tunable_params(self) -> tuple[ParamSpec, ...]:
        return tuple(p for p in self.params if p.is_tunable)


@dataclass(frozen=True)
class ModuleSpec:
    """All ``@stimela_cab``-decorated commands found in one CLI module."""

    path: Path
    commands: tuple[CommandSpec, ...]
