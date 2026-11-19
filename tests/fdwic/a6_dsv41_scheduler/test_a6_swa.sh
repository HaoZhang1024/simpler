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
python -I "$swa/run.py" --platform a6 --device "$device" \
    --a6-query "$out/query/query" --runtime-lib "$out/lib/a6/onboard" \
    --build-dir "$out/case" --output "$out/result" --warmup 1 --rounds 10
