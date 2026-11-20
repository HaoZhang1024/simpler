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
    echo "Usage: bash run.sh ASSIGNED_DEVICE" >&2
    exit 2
fi
device=$1
if [[ -n ${TASK_DEVICE:-} && $TASK_DEVICE != "$device" ]]; then
    echo "Requested device $device differs from allocated TASK_DEVICE=$TASK_DEVICE" >&2
    exit 2
fi
src=$(cd "$(dirname "$0")" && pwd)
root=$(git -C "$src" rev-parse --show-toplevel)
mkdir -p "$root/build"
out=$(mktemp -d "$root/build/a6-same-address-XXXXXXXX")
echo "A6 output: $out"
exec > >(tee "$out/run.log") 2>&1
echo "case=A6-same-address device=$device source=$(git -C "$root" rev-parse HEAD)"
sdk=${ASCEND_HOME_PATH:?load the A6 CANN environment}
cc="$sdk/bin/ccec"
"$cc" --version
pin=6065c782e05c730f1d264532cc3075c509d1da89
isa=${PTO_ISA_ROOT:-"$root/build/pto-isa"}
if [[ $(git -C "$isa" rev-parse HEAD 2>/dev/null || true) != "$pin" ]]; then
    isa="$out/pto-isa"
    git init -q "$isa"
    git -C "$isa" fetch --depth 1 https://github.com/hw-native-sys/pto-isa.git "$pin"
    git -C "$isa" checkout -q --detach FETCH_HEAD
fi
[[ $(git -C "$isa" rev-parse HEAD) == "$pin" ]]
if [[ -n $(git -C "$isa" status --porcelain -- include) ]]; then
    echo "Modified PTO-ISA headers in $isa" >&2
    exit 1
fi
echo "PTO-ISA=$pin target=dav-920r1"
"$cc" -xcce -O2 -std=c++17 -fPIC -DREGISTER_BASE --cce-aicore-arch=dav-920r1 \
    -mllvm -cce-aicore-dcci-insert-for-scalar=false -mllvm -cce-aicore-addr-transform \
    -I"$isa/include" -I"$sdk/include" -I"$sdk/pkg_inc" -I"$sdk/pkg_inc/runtime/runtime" \
    -c "$src/device.cpp" -o "$out/device.o"
"$cc" --cce-fatobj-link -shared "$out/device.o" -L"$sdk/lib64" -lruntime -o "$out/libmeasurement.so"
"${CXX:-c++}" -O2 -std=c++17 -I"$sdk/include" -I"$sdk/pkg_inc" -I"$sdk/pkg_inc/runtime" \
    "$src/host.cpp" -L"$out" -lmeasurement -Wl,-rpath,'$ORIGIN' -L"$sdk/lib64" -lascendcl -lruntime -o "$out/probe"
for group in gm cnt_notify; do
    "$out/probe" "$device" "$group" "$out/$group.csv" 2>&1 | tee "$out/$group.log"
done
python3 "$src/summarize.py" "$out"
cat "$out/result.md"
echo "PASS: six validated scenarios. Results: $out"
