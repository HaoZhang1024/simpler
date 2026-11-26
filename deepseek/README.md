# DeepSeek-V4 Pro decode operators on A3

These ten frozen operator fixtures come from `pypto-lib/models/deepseek_v4_pro`. Both builds used the same model inputs, compiled callable, validation rules and A3 9392 device. A is the PR baseline. J combines ready MIX dispatch and the Phase 4b early-queue check.

Each operator ran in three groups with both builds. HCA, CSA and SWA ran in three additional groups with the order reversed, bringing each attention operator to three AJ groups and three JA groups. AJ and JA identify the order of the two processes in a group. The first order alternates by operator. Each process performed 10 warmups and 100 measured calls. The primary metric is device-clock L0 Effective, from the earlier of orchestration/scheduling start to the later end. Host-side resets and numerical checks are outside this interval. AICore time has no L0 marker in these captures.

- `calls.csv.gz` contains all 8,580 calls. Keep `warmup=0` for the 7,800 formal measurements. Call numbers are local to each process.
- `groups.csv` contains 78 process summaries of the formal calls. Percentiles use linear interpolation. Subtract A from J within each operator and group. Groups 1–3 are the initial matrix and 4–6 the attention follow-up.
- `manifest.json` records firmware, callable, tensor-file and model-source hashes, and the checks on calls 1 and 110 of each process. Every mutable tensor was restored before each call. Each process also checked read-only inputs after the last invocation.
