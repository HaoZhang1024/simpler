#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated A6 card}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
root=$(cd "$(dirname "$0")/../../../.." && pwd)
trial=$(realpath "${1:-$root/build/swa-integrated-758Yr8}")
python="$trial/src/.venv/bin/python"
shopt -s nullglob
models=("$trial"/src/build/swa-a6-*/model/summary.json)
[[ ${#models[@]} == 1 ]] || { echo "Expected one saved SWA model in $trial" >&2; exit 1; }
baseline=$(dirname "$(dirname "${models[0]}")")
"$python" -c 'import json, sys; assert json.load(open(sys.argv[1]))["device"] == int(sys.argv[2]), "Select baseline device"' \
    "${models[0]}" "$DEVICE"
out=$(mktemp -d "$root/build/ipc-lifecycle-XXXXXX")
echo "IPC comparison directory: $out"
exec > >(tee "$out/run.log") 2>&1
ipc=$(git -C "$root" rev-parse HEAD)
for arm in gm ipc; do
    ref=$ipc
    if [[ $arm == gm ]]; then ref=be6e23f0ed9dd27e08475c56c68fb7faf10d6693; fi
    src="$out/$arm/src"
    mkdir -p "$out/$arm"
    git clone -q --local "$root" "$src"
    git -C "$src" checkout -q --detach "$ref"
    mkdir -p "$src/build"
    git clone -q --local "$trial/src/build/pto-isa" "$src/build/pto-isa"
    git -C "$src/build/pto-isa" checkout -q --detach "$(cat "$src/pto_isa.pin")"
    echo "$arm $ref"
    "$python" -I "$src/simpler_setup/build_runtimes.py" --platforms a6 --runtime percounter \
        --lib-dir "$out/$arm/lib" --profiling-dfx 1 --profiling-orch 0 --profiling-sched 0 --profiling-tensormap 0
    "$python" -I "$src/tests/fdwic/a6_dsv41_scheduler/run.py" --platform a6 --device "$DEVICE" --level 0 \
        --a6-query "$baseline/query/query" --build-dir "$baseline/t25-54" --runtime-lib "$out/$arm/lib/a6/onboard" \
        --output "$out/$arm/L0" --warmup 1 --rounds 10
done

"$python" - "$out" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

out = Path(sys.argv[1])
captures = {arm: json.loads((out / arm / "L0/summary.json").read_text()) for arm in ("gm", "ipc")}
gm, ipc = captures.values()
assert gm["build"] == ipc["build"] and gm["device"] == ipc["device"]
for binary in ("libaicpu_kernel.so", "aicore_kernel.o"):
    key = f"onboard/percounter/{binary}"
    assert gm["runtime_sha256"][key] != ipc["runtime_sha256"][key], f"Identical {binary} in both arms"
feedback = {"device": gm["device"], "plan_sha256": gm["build"]["plan_sha256"]}
for arm, capture in captures.items():
    result, = capture["results"]
    assert capture["status"] == "passed" and result["numerical_validation"]
    assert result["warmup"] == 1 and result["rounds"] == 10
    feedback[arm] = {"commit": subprocess.check_output(
        ["git", "-C", str(out / arm / "src"), "rev-parse", "HEAD"], text=True
    ).strip(), "passed": True}
    for metric in ("aicore", "device"):
        samples = result[f"{metric}_samples_ms"]
        assert len(samples) == 10
        feedback[arm][f"{metric}_samples_us"] = [round(x * 1000, 3) for x in samples]
        feedback[arm][f"{metric}_mean_us"] = round(result[f"{metric}_mean_ms"] * 1000, 3)
feedback["ipc_minus_gm_us"] = {
    metric: round(feedback["ipc"][f"{metric}_mean_us"] - feedback["gm"][f"{metric}_mean_us"], 3)
    for metric in ("aicore", "device")
}
text = json.dumps(feedback)
(out / "feedback.json").write_text(text + "\n")
print(text)
PY
