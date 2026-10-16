# MLAI evaluation framework

Run from the repository root. The framework preserves current production business logic, including any bugs it detects. Exit code 1 means an evaluated check failed (see the generated report); it does not mean the framework discarded results. Every run creates `evaluation/benchmarks/results/<UTC-run-id>-<uuid>/`.

## Setup

Use the existing `.venv`:

```bash
.venv/bin/python -m pip install -r evaluation/benchmarks/requirements.txt
```

Existing development dependencies suffice for normal runs. `coverage` is optional for branch measurement: unavailable branch coverage is N/A. No external service is added. A writable local `/tmp` directory is used for each isolated backend. Do not use network-mounted SQLite benchmark files as a substitute without documenting the change.

## Commands

```bash
# Lightweight tests of framework utilities (should pass regardless of production findings)
.venv/bin/python -m pytest evaluation/benchmarks/tests/test_metrics.py evaluation/benchmarks/tests/test_compare.py -q

# Quick policy, fault/security and 1/5-concurrent smoke evaluation
.venv/bin/python -m evaluation.benchmarks smoke

# Five, ten, twenty employees: all A-E proof scenarios with mocked inference
.venv/bin/python -m evaluation.benchmarks load --concurrency 5
.venv/bin/python -m evaluation.benchmarks load --concurrency 10
.venv/bin/python -m evaluation.benchmarks load --concurrency 20

# A-E with F (burst versus evenly staggered over 10 seconds), all supported levels
.venv/bin/python -m evaluation.benchmarks suite --arrival both

# More repeat batches for more stable estimates
.venv/bin/python -m evaluation.benchmarks load --concurrency 20 --arrival both --repetitions 5

# Real VLM concurrency is explicitly opt-in; may consume shared GPU resources
.venv/bin/python -m evaluation.benchmarks load --concurrency 5 --scenarios cold ready --live-vlm

# Independent VLM classification, field extraction, corruption and injection probes
.venv/bin/python -m evaluation.benchmarks vlm --live-vlm

# Existing optional LLM adapter, not the disabled default pipeline
.venv/bin/python -m evaluation.benchmarks llm --live-llm

# Full suite with explicit real model evaluation (expensive)
.venv/bin/python -m evaluation.benchmarks suite --arrival both --live-vlm --live-llm
```

`no_proof` is A: legitimate one-day annual leave. `ready` is B: distinct documents uploaded and inspected during setup, outside measured submission. `cold` is C: unique printed reference content and SHA-256, uploaded then immediately submitted. `mixed` is D: configurable 50/25/25 split, exactly 10/5/5 at 20 employees. `contention` is E: 50/50 no-proof/cold, exactly 10/10 at 20 employees. `--arrival both` applies F to each workload. Smaller odd counts use deterministic largest-remainder rounding. These workloads use 100+ synthetic team members so team quota does not accidentally dominate throughput. CLI supports 1, 5, 10, 15, 20, 30 concurrent clients.

## Configuration and timing semantics

Edit `evaluation/benchmarks/config.json` or supply `--config path.json`. JSON is used instead of YAML to avoid a parser dependency. Effective workload and scheduling parameters, source/dataset/annotation/policy hashes, model IDs, hardware, interpreter, cache policy and inference mode are recorded. Fixed application time is `2026-09-01T08:00:00+07:00`, timezone `Asia/Ho_Chi_Minh`, matching repository calendar semantics. Arrival timestamps are actual observed wall times; scheduling skew uses monotonic clocks.

Each batch starts a fresh isolated backend, cache, upload directory and database. READY documents are preprocessed before request arrival. No-proof, READY and COLD measures are separated by category. COLD SHA uniqueness is asserted. Burst starts use one coordinated future monotonic epoch; staggered starts use an even 10-second window. `seed` records reproducible bootstrap intervals; the arrival schedule and document generator are deterministic.

Mock-mode completion deadline is 10 seconds, sufficiently larger than the 20 ms mocked inference; stuck requests are reported as unfinished/timeouts. Explicit real VLM uses `real_completion_timeout_seconds` (1800 seconds by default) for the serial inference queue. Neither deadline turns unfinished requests into valid outcomes.

- `upload_ms`: client upload call including job enqueue.
- `ack_ms`: submission HTTP call; HTTP 202 is **not** completion.
- `final_ms`: from employee arrival (includes COLD upload) to observing a valid automatic outcome. The CLI polls `PROCESSING` until a valid persisted workflow stop or deadline. Human-wait states are listed separately from `business_final` states.
- `queue_ms`: persisted created-to-start job timestamps. `job_service_ms` includes VLM wrapper, parsing and proof persistence, not pure inference; retries currently overwrite timestamps, so per-attempt waits are N/A.
- `vlm_client`: worker-observed inspector duration; Ollama response durations (nanoseconds) and client latency (milliseconds) are separate in `inference.csv`. Ollama durations are not network/queue subtraction estimates.
- `sqlite_lock_wait` and `sqlite_transaction`: batch aggregate timings through existing metric callbacks; exact attribution to a single request is N/A.
- Throughput: automatic policy outcomes per measured batch second. Human completion throughput is N/A without human resolution workloads.

Mock mode measures real HTTP, orchestration and SQLite, while VLM is explicitly mocked. It is never reported as real VLM latency or quality. No-proof timings remain genuine but are labeled with the surrounding run's mock mode. `--live-vlm` turns on existing production inspector calls and keeps any real failure or CV blur-gate result. The normal pytest suite refuses live inference.

Model cache coldness differs from model-weight coldness: the proof cache is controlled, but shared Ollama residency is marked `uncontrolled-external-residency`. For weight cold/warm experiments use dedicated model servers and record externally controlled residency with separate configs. The framework never unloads models from a shared daemon. Observers record actual generation options; the existing source determines inference parameters rather than changing business behavior.

## Datasets and ground truth

`datasets/applications.json`: 110 synthetic cases across the eight requested categories. `ground_truth.json` holds independently authored expectations, policy clauses, state, audit requirements, severity, rationale and policy-conflict flags. Ground truth is generated by the authored builder without importing or calling the evaluated engine. There are fewer unique templates than cases; template variants are not independent evidence.

`proof_annotations.json` contains printed document annotations. Images are generated on demand in the isolated directory using Pillow and unique textual references; no real employee/medical documents are used. Normal, low-resolution, mild/strong blur, rotation, lighting, contrast and occlusion stressors are deterministic. Subjective corrupted-image readability is left unlabelled; fields hidden by occlusion are omitted from field scoring. A sentinel injection document remains synthetic and untrusted.

Rebuild authored datasets with:

```bash
.venv/bin/python -m evaluation.benchmarks.datasets.build
```

The unified case corpus at `datasets/unified_cases.json` combines the 120 policy benchmark cases and 38 repository case-bank scenarios (158 total, namespaced IDs; overlapping concepts are retained). Present proof cases have image files under `datasets/unified_proofs/`: 20 copied repository fixtures and 26 generated policy fixtures. All evidence is synthetic. The policy labels still evaluate structured proof facts; the attached images provide corresponding visual inputs but are not yet passed through VLM by the policy runner. Rebuild and validate with:

```bash
.venv/bin/python -m evaluation.benchmarks.datasets.build_unified
.venv/bin/python -m pytest evaluation/benchmarks/tests/test_unified_dataset.py -q
```

Inspect `ARCHITECTURE.md` for policy disagreements before changing annotations. Conflicting cases are **skipped from headline correctness**, with actual observations preserved. Clear violations remain failures. Policy rule latency and optional branch coverage are measured independently; persisted actor/state/ledger/audit behavior is checked in isolated integration tests. Ground-truth state and audit fields are applicable to workflow tests and are not claimed measured by the standalone rule runner.

## Reliability and security

Controlled tests cover concurrency, duplicate applications/jobs/uploads, ledger debit uniqueness, rollback, a bounded busy timeout, retry exhaustion, timeout/invalid-JSON/unavailable-model exceptions, worker recovery, stale success/failure, unfinished requests, cache separation, reviewer races, audit events, model-call exclusion, object/role access, file types/size, traversal and synthetic sensitive log text. Process-kill recovery and real injection are explicitly skipped in lightweight pytest.

```bash
.venv/bin/python -m pytest evaluation/benchmarks/tests -q
```

This command can fail on current production behavior. Never update expectations to pass without an authoritative policy change. Fault injection is only into isolated objects/test databases. It never stops a production server, alters a real record, or copies production documents.

## Results and dashboard

Each run writes `metadata.json`, `requests.csv`, `inference.csv`, `correctness.csv`, `failures.json`, `summary.json`, `report.html`, and measured-only `evaluation.md`. Load runs also save per-batch snapshots and OpenAPI. Tests save JUnit XML. Coverage and GPU samples are present when available/explicitly measured. The offline HTML has an overview, latency/throughput comparisons, filterable SVG request timeline, model quality, policy/escalation, reliability/security and failed/skipped cases. It requires no network or CDN. Missing metrics are N/A.

Bootstrap mean confidence intervals are reproducible but assume request resampling; requests in one concurrent batch are correlated. p99 with a small sample is unstable. Increase repetitions and analyze batch-level variation for publication claims. Security pass rates and integration test rates are separate from production incident rates; a test pass does not establish global safety.

## Before / after

Collect equivalent runs on the intended two checkouts/configurations (this task does not optimize the system):

```bash
.venv/bin/python -m evaluation.benchmarks load --concurrency 5 10 20 --label baseline
# In the intended second build, with identical workload/config/dataset/hardware/model IDs
.venv/bin/python -m evaluation.benchmarks load --concurrency 5 10 20 --label optimized
.venv/bin/python -m evaluation.benchmarks compare \
  --baseline evaluation/benchmarks/results/BASELINE_RUN_ID \
  --optimized evaluation/benchmarks/results/OPTIMIZED_RUN_ID \
  --output evaluation/benchmarks/results/comparison
```

Comparison rejects differences in data/annotation/policy versions, hardware, model IDs, cache policy, model mode, arrival schedule or workloads. It reports latency reductions, throughput/makespan/lock-wait changes, error/reliability changes and available decision parity/quality differences. Same-source comparisons are labeled repeatability, never optimization. External GPU contention, thermal state and uncontrolled residency remain limitations. If two actual builds are unavailable, an optimization comparison is N/A.
