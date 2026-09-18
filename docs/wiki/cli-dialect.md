---
type: reference
title: The CLI dialect
description: Which typer constructs a CLI module may use, why the set is closed, and where the parser enforces it.
tags: [generate-cabs, generate-function, typer, introspector, round-trip]
timestamp: 2026-09-19
last_verified_commit: 4532253
---

# The CLI dialect

Source: `utils/introspector.py` (`extract_typer_metadata_libcst`,
`extract_param_spec`), `utils/cab_to_function.py` (the reverse direction).

## Why the set is closed

A cab and a CLI module are two renderings of one definition. `generate-cabs`
produces the cab from the module; `generate-function` produces the module from
the cab. A human writes whichever side they prefer — the YAML cab is the simpler
one — and generates the other. `tests/test_roundtrip.py`, shipped by
`hip-cargo init` into every downstream project, asserts that
`cli -> cab -> cli` is byte-identical.

That makes the writable language exactly *what a cab can express*. A construct
with no cab representation cannot survive the round trip, so it is not part of
the dialect. This is a design decision, not a missing feature.

## The dialect

| Construct | Status |
|---|---|
| `Annotated[T, typer.Option(...)]` | The only accepted parameter form |
| `typer.Option(..., help=...)` | Required parameter — the `...` *is* the required marker |
| `typer.Option(help=...)` + Python default | Optional parameter |
| `StimelaMeta(...)` in the `Annotated` | Cab fields with no typer equivalent |
| `typer.Argument(...)` | **Rejected** |
| `typer.Option("-x", "--ex", ...)` | **Rejected** |

Flag names are derived from the parameter name (`neg_int` → `--neg-int`), which
is why param_decls have nowhere to live in a cab.

`typer.Argument` is rejected rather than translated: `generate-function` emits
`typer.Option` only, so a module using it would generate a perfectly good cab and
then fail the round trip as a line diff, one step removed from the cause. The cab
still records `policies.positional: true` for every required input — under
`flavour: python` that describes how stimela calls the *core function*, not how
the CLI parses argv.

## Enforcement

Both rejections raise `ValueError` from `extract_typer_metadata_libcst`, before
any cab is written. `extract_param_spec` passes the parameter name in so the
message can name it:

```
Parameter 'ex': typer.Option param_decls are not supported ('-x', '--ex'). Flag
names are derived from the parameter name so that a cab and its CLI module stay
in one-to-one correspondence. Remove them.

Parameter 'ms': typer.Argument is not supported. A cab cannot express a
positional CLI argument, so the CLI module could not be regenerated from it.
Declare it as typer.Option(..., help=...) instead; the cab still records
policies.positional: true.
```

Before #112 and #113 neither was rejected. `typer.Option("-x", "--ex")` on a
**required** parameter emitted `default: -x` and exited 0 — the first positional
argument of the typer call was read as the default value, so the flag string
became the default and `required: true` was dropped. That is the same failure
mode as #109 and #110: unparsed input silently becoming a value. `typer.Argument`
without its `...` raised a `RuntimeError` describing the parser's own invariant.

A required parameter written without the `...` now gets a message naming the
fix instead of that `RuntimeError`.

## What is still tolerated

A **non-string** first positional is still read as a default
(`typer.Option(0.5, help=...)`), the pre-Annotated typer spelling. Only strings
are treated as param_decls, because in `Annotated` style a string positional is
never anything else. Pinned by
`tests/test_cli_dialect.py::test_a_non_string_positional_is_still_read_as_a_default`.

## Related

- [cab-yaml-emission.md](cab-yaml-emission.md) — what happens to values once
  they are extracted.
- Downstream consequence, worth knowing when reviewing a conversion: a project
  moving an existing CLI onto hip-cargo loses short flags and positional
  arguments. That is the format, not a compromise the project made.
