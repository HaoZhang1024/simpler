#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated A6 device ID}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
swa=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$swa/../../.."
query=${SWA_RUN:-build/swa-a6-MxF89z}/query/query
case_dir=${T25_RUN:-build/swa-t25-lk1vgyf9}/t25-54
[[ -x "$query" && -f "$case_dir/build.json" && -x "$case_dir/host/native-runner" ]] || {
    echo "Check SWA_RUN (query/query) and T25_RUN (t25-54/build.json and host/native-runner)" >&2
    exit 2
}

mkdir -p build
out=$(mktemp -d "$PWD/build/swa-a6-bound-XXXXXX")
echo "SWA bound output: $out"
exec > >(tee "$out/run.log") 2>&1
git rev-parse HEAD > "$out/git-head.txt"
python -m pip install -r tests/fdwic/dsv41_scheduler/production/requirements-bound.txt
python simpler_setup/build_runtimes.py --platforms a6 --runtime percounter \
    --lib-dir "$out/lib" --profiling-dfx 1 --profiling-orch 0 \
    --profiling-sched 0 --profiling-tensormap 0

for level in 0 2; do
    python -I "$swa/run.py" --platform a6 --runtime percounter --device "$DEVICE" \
        --a6-query "$query" --runtime-lib "$out/lib/a6/onboard" --build-dir "$case_dir" \
        --level "$level" --warmup 1 --rounds 10 --output "$out/L$level"
done

cat "$out/git-head.txt" | tee "$out/feedback.txt"
python "$swa/analysis/swa_sync_bound.py" "$case_dir" "$out/L0" "$out/L2" "$out/model" --time-limit 30 \
    | tee -a "$out/feedback.txt"
cat "$out/model/l0.csv" | tee -a "$out/feedback.txt"
echo "Feedback: $out/feedback.txt"
