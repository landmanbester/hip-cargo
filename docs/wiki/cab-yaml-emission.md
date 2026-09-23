---
type: reference
title: Cab YAML emission
description: How CLI source becomes cab YAML, the two text-rewriting steps that can corrupt it, and the invariants that must hold.
tags: [generate-cabs, yaml, introspector, libcst]
timestamp: 2026-09-23
last_verified_commit: PENDING
---

# Cab YAML emission

Source: `utils/introspector.py` (`get_cst_value`, `format_info_fields`),
`core/generate_cabs.py` (dump, format, validate, write).

## The pipeline

```
cli/*.py --libcst--> ParamSpec --> cab dict --yaml.safe_dump--> text
                                                                 |
                                            format_info_fields (text rewrite)
                                                                 |
                                            yaml.safe_load guard --> cabs/*.yml
```

Two steps operate on *text*, not on a document model, and are therefore the
places a cab can go wrong.

## Value extraction: `get_cst_value`

Maps a LibCST node to a Python value. Its final `else` returns the node's
**source text**, which is correct for expressions we cannot evaluate (`Path.cwd()`)
and silently wrong for anything we simply forgot to handle.

**Signed literals are not `Integer` nodes.** `-1` parses as
`UnaryOperation(Minus, Integer("1"))`. Before #109 it hit the fallback and a
cab got `default: '-1'` — a *string* under `dtype: int`. Unary `-`, `+` and `~`
on numeric literals are now resolved; everything else still falls back.

Two reasons this survived so long, worth remembering when adding types here:

- **The round-trip test cannot see it.** `generate-function` casts the default
  back using `dtype`, so `cli → cab → cli` is byte-identical with the bug intact.
  Assert on the *type* of the value in the cab, not just the round-trip.
- **`generate-schemas` shares the IR.** Anything wrong in `ParamSpec` also lands
  in the generated Pydantic models, where nothing coerces it.

## Info formatting: `format_info_fields`

Rewrites each `info:` value from the dumped one-liner into one line per
sentence (split on `". "`), so cab YAML reads well in a diff.

Invariants this rewrite must preserve:

1. **Quote the whole value or none of it.** A colon forces quoting, or YAML
   reads the line as a nested mapping. Quoting *individual lines* of a
   multi-line plain scalar produces unparseable YAML — a quoted scalar cannot be
   continued by unquoted lines (#110). A multi-line single-quoted scalar folds
   to the same string a plain one does, so wrapping the whole block is safe.
2. **Undo `safe_dump`'s escaping before re-escaping.** `safe_dump` emits a
   single-quoted scalar for values containing `": "`, doubling any apostrophe
   inside it. Stripping only the outer quotes leaves `don''t` in the value.
3. **Trailing comments stay YAML comments.** The inline comment extracted from
   the help string (`\s{2,}#`) is appended after the last line, outside the
   scalar. This rules out block scalars (`|-` / `>-`), where `#` would become
   literal content — comment preservation is a core feature.

## The generation-time guard

`generate_cabs` runs `yaml.safe_load` over the formatted text before writing and
raises `ValueError` if it fails. Before that guard, `generate-cabs` wrote
corrupt cabs and exited 0; the breakage only surfaced later, in a project's
round-trip test (`generate-function` loads the YAML) or in stimela.

## What the guard does not catch

The guard asserts that the output **parses**, not that it means what went in.
Two families survive it, because both produce valid YAML with the wrong value.
Verified against this branch, one `help=` string per row:

| `help=` | Result |
|---|---|
| `"Weights column. Options are as follows:"` | guard raises `ValueError` |
| `"Options are as follows:"` | **silent** — `info` loads as `{'Options are as follows': None}`, a mapping |
| `"Use channel #3. Second sentence."` | guard raises |
| `"- leading dash. Second sentence."` | guard raises |
| `"Angle in degrees (°). Second sentence."` | **silent** — `info` loads as `'Angle in degrees (\xB0). ...'` |

The colon rows are the same defect as #110 from a different angle: the rewrite
decides quoting from one heuristic (`": "` present) rather than from what YAML
actually requires, so a trailing colon, a `" #"` and a leading `"- "` all slip
past it. The non-ASCII row is separate: `safe_dump` defaults to
`allow_unicode=False` and emits a *double*-quoted scalar with escapes, and
stripping the quotes without unescaping leaves the escape text in the value.
`°`, `λ` and `μ` are all plausible in this domain.

`get_cst_value` has the matching gap on the value side: its fallback returns the
node's source text for anything it cannot evaluate, so a module-level constant
or a call still lands in the cab as if it were a value — `default: SENTINEL`,
`default: float("inf")` — under a numeric `dtype`. #109 fixed the signed-literal
instance of this, not the class.

Tracked in #116. The shape of the fix for the first family is to make the guard
a *value* comparison rather than a parse: build the multi-line form, reload it,
and fall back to the single-line scalar `safe_dump` already produced when the
value does not survive. That keeps the comment placement in invariant 3 intact,
which a block scalar would not. `allow_unicode=True` on the dump removes the
second family at source.

Tests: `tests/test_yaml_emission.py`, fixture
`tests/fixtures/src/fixture_pkg/cli/yaml_emission_demo.py`.
