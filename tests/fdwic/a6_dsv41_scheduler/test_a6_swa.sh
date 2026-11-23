#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
set -euo pipefail

if [[ $# != 1 || ! $1 =~ ^[0-9]+$ ]]; then
    echo "Usage: bash test_a6_swa.sh DEVICE" >&2
    exit 2
fi
device=$1
swa=$(cd "$(dirname "$0")" && pwd)
cd "$swa/../../.."
export PYTHONPATH="$PWD/python:$PWD${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p build
out=$(mktemp -d "$PWD/build/swa-a6-XXXXXX")
echo "SWA output: $out"
exec > >(tee "$out/test.log") 2>&1
git rev-parse HEAD

python simpler_setup/build_runtimes.py --platforms a6 --runtime percounter \
    --lib-dir "$out/lib" --profiling-dfx 1 --profiling-orch 0 \
    --profiling-sched 0 --profiling-tensormap 0
cmake -S tools/cann-examples/query -B "$out/query" -G Ninja
cmake --build "$out/query" --target query
python -I "$swa/prepare.py" build --platform a6 --pto-isa build/pto-isa \
    --build-dir "$out/case" --jobs 4
if [[ ${SWA_SYNC_BOUND:-0} == 1 ]]; then
    python -I "$swa/analysis/t25_ab.py" "$out" --prepare-only "$out"
    for level in 0 2; do
        python -I "$swa/run.py" --platform a6 --device "$device" --level "$level" \
            --a6-query "$out/query/query" --runtime-lib "$out/lib/a6/onboard" \
            --build-dir "$out/t25-54" --output "$out/L$level" --warmup 1 --rounds 10
    done
    python "$swa/analysis/swa_sync_bound.py" "$out/t25-54" "$out/L0" "$out/L2" "$out/model" --time-limit 30
else
    python -I "$swa/run.py" --platform a6 --device "$device" \
        --a6-query "$out/query/query" --runtime-lib "$out/lib/a6/onboard" \
        --build-dir "$out/case" --output "$out/result" --warmup 1 --rounds 10
fi
