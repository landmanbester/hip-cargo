---
type: reference
title: Cab YAML emission
description: How CLI source becomes cab YAML, the two text-rewriting steps that can corrupt it, and the invariants that must hold.
tags: [generate-cabs, yaml, introspector, libcst]
timestamp: 2026-11-17
last_verified_commit: dbbf133
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

## Every rewrite is checked against the value (#116)

Parsing is not enough. Before #116 the guard only checked that the output
**parsed**, and the rewrite chose quoting from one heuristic (`": "` present).
These produced valid YAML with the wrong value:

| `help=` | Before #116 |
|---|---|
| `"Options are as follows:"` | `info` loaded as `{'Options are as follows': None}`, a mapping |
| `"Weights column. Options are as follows:"`, `"Use channel #3. ..."`, `"- leading dash. ..."` | unparseable, so the guard raised |
| `"Angle in degrees (°). ..."` | `info` loaded as the escape text `'Angle in degrees (\xB0). ...'` |

Now `format_info_fields`:

1. **Decodes** each dumped scalar with `yaml.safe_load` instead of stripping
   quotes by hand, so `safe_dump`'s quoting and escapes are undone exactly
   (this subsumes invariant 2).
2. **Tries renderings in order**, keeping the first that reloads, comment
   included, to exactly the value:
   - plain, one sentence per line;
   - the same lines as one single-quoted scalar (invariant 1);
   - a single line quoted by `safe_dump`.

   The first two are what hip-cargo always emitted, so cabs that were already
   correct are byte-identical (checked against every committed cab in
   hip-cargo, pfb-imaging, meerkat-beams, pfb-model-spec, surfvis and
   jackknify).
3. **Keeps the comment outside the scalar** in every rendering (invariant 3), so
   comment preservation survives the fallback.

`implicit:` gets the same check, and apostrophes inside it are now escaped.
`generate_cabs` dumps with `allow_unicode=True`, so `°`, `λ` and `μ` stay
literal in cabs. The `safe_load` guard in `generate_cabs` remains as a last
line of defence.

On the value side, `get_cst_value`'s source-text fallback stays, because
`Path.cwd()` and similar defaults rely on it. But a parameter whose dtype is
`int`, `float` or `bool` (optionally `| None`) and whose default is not a
literal (`_is_literal`) now raises `ValueError` in `extract_param_spec`. It
used to emit `default: SENTINEL` or `default: float("inf")` under a numeric
`dtype`. Non-numeric dtypes keep the fallback.

Gotcha: a parameter's inline comment is only picked up when `help=` is the
**last** argument of `typer.Option(...)` with no trailing comma
(`help="..."  # noqa: E501`). After a trailing comma the comment hangs off the
comma, and `_extract_inline_comment_from_help_string` does not look there.

Tests: `tests/test_yaml_emission.py`, fixture
`tests/fixtures/src/fixture_pkg/cli/yaml_emission_demo.py`.
