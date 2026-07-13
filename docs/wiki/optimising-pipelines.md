---
type: guide
title: Optimising pipelines from diagnostics
description: How an agent turns the requested-vs-used diagnostics report into concrete optimisation actions.
tags: [optimisation, diagnostics, agent-workflow]
timestamp: 2026-07-13
last_verified_commit: a1b714a
---

# Optimising pipelines from diagnostics

The `/diagnostics` endpoint serves **facts, not advice** — deriving the
optimisation is the consumer's job. This page is the playbook. Schema and
caveats: [diagnostics.md](diagnostics.md).

## Workflow

1. Run the pipeline with monitoring attached; fetch
   `GET /api/progress/{job_id}/diagnostics`.
2. Rank tasks by `wall_s` — optimise the dominant term first; ignore steps
   contributing <10% of `pipeline.wall_s`.
3. For each dominant task, read the signals below.
4. Change **one** resource request or code path, re-run, diff the two reports.

## Signal → interpretation → action

| Signal | Likely meaning | Action |
|--------|----------------|--------|
| `cpu_utilisation` ≪ 1 (e.g. <0.3) with large `wall_s` | I/O-bound, lock-bound, or over-provisioned CPUs | Shrink `num_cpus` (frees scheduler slots → more parallel steps), or investigate the wait (see `read_blocks`/`read_mb`) |
| `cpu_utilisation` ≈ 1 | CPU-saturated at its request | Raise `num_cpus` only if the code actually scales; otherwise this step is the honest critical path |
| `cpu_utilisation` > 1 | Step spawns more threads than requested (e.g. unpinned BLAS/OpenMP) | Cap threads (`OMP_NUM_THREADS` in the cab's `env_vars`) or raise the request to match reality — oversubscription degrades co-scheduled steps |
| `peak_rss_mb` ≪ memory request | Over-provisioned memory | Shrink the request → better bin-packing |
| `peak_rss_mb == rss_entry_mb` | Stale process high-water mark (Ray worker reuse, caveat 1) | Trust the psutil tier (`sampled: true`) or discount the peak |
| High `queue_lag_s` | Step waited for resources — the cluster couldn't place it | Shrink *other* steps' requests, or this step's own oversized request |
| High `import_s` | Cold-start dominated (container image + heavy imports) | Defer/trim imports; for short pipelines, weigh per-step containers against a shared image |
| `cpu_user_s + cpu_system_s` ≪ expected with busy children | Under-attribution: `RUSAGE_SELF` excludes subprocesses (caveat 2) | Don't conclude idleness for steps that shell out |
| `pipeline.wall_s` ≫ Σ task `wall_s` | Time lost *between* steps | Look at queue lags and the runner's submission pattern, not the task bodies |

## Escalation and complements

- **Line-level**: diagnostics name the step, not the line. Escalate to
  py-spy (sampling, no code change) or memray (allocation) on the named step.
- **Cluster-wide / time-series**: Ray Dashboard (`:8265`) owns node metrics,
  task timelines, and scheduling state — complementary vocabulary, not a
  replacement for the per-step attribution here.
- **Live view during the run**: `WS /ws/progress/{job_id}` streams DIAGNOSTIC
  events as they arrive; the REST report is simpler for post-run analysis.

Worked example: `stokify/demo.py` prints this table per run and gates its
PASS on the field contract.
