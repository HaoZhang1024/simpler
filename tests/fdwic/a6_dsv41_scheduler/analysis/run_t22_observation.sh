#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated baseline A6 card}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
root=$(cd "$(dirname "$0")/../../../.." && pwd)
trial=$(realpath "${1:-$root/build/swa-integrated-758Yr8}")
python="$trial/src/.venv/bin/python"
shopt -s nullglob
models=("$trial"/src/build/swa-a6-*/model/summary.json)
[[ ${#models[@]} == 1 ]] || { echo "Expected one saved model in $trial" >&2; exit 1; }
baseline=$(dirname "$(dirname "${models[0]}")")
"$python" -c 'import json, sys; assert json.load(open(sys.argv[1]))["device"] == int(sys.argv[2]), "Select baseline device"' \
    "${models[0]}" "$DEVICE"
out=$(mktemp -d "$root/build/t22-observation-XXXXXX")
echo "Observation directory: $out"
git clone -q --local "$root" "$out/src"
cd "$out/src"
# Keep both sides of the earlier V0 observation experiment on the GM lifecycle.
git checkout -q --detach 7da06ce4f11f914b6dafc43ca567b8d126271c80
mkdir -p build
git clone -q --local "$trial/src/build/pto-isa" build/pto-isa
git -C build/pto-isa checkout -q --detach "$(cat pto_isa.pin)"
"$python" -I simpler_setup/build_runtimes.py --platforms a6 --runtime percounter --lib-dir "$out/lib" \
    --profiling-dfx 1 --profiling-orch 0 --profiling-sched 0 --profiling-tensormap 0
swa=tests/fdwic/a6_dsv41_scheduler
for arm in control probe; do
    lib="$baseline/lib"
    mode=--t22-entry-roles
    if [[ $arm == probe ]]; then lib="$out/lib"; mode=--t22-observation; fi
    "$python" -I "$swa/run.py" --platform a6 --device "$DEVICE" --level 2 --a6-query "$baseline/query/query" \
        --build-dir "$baseline/t25-54" --runtime-lib "$lib/a6/onboard" --output "$out/$arm" --warmup 1 --rounds 10
    "$python" "$swa/analysis/task_sensitivity.py" "$baseline" "$mode" --capture-l2 "$out/$arm" > "$out/$arm.json"
done
"$python" - "$out" "$(git rev-parse HEAD)" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
report = {arm: json.loads((out / f"{arm}.json").read_text()) for arm in ("control", "probe")}
report["probe_commit"] = sys.argv[2]
report["device"] = json.loads((out / "probe/summary.json").read_text())["device"]
text = json.dumps(report)
(out / "feedback.json").write_text(text + "\n")
print(text)
PY
