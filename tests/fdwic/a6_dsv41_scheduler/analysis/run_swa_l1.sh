#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated baseline A6 card}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
swa=$(cd "$(dirname "$0")/.." && pwd)
root=$(cd "$swa/../../.." && pwd)
trial=$(realpath "${1:-$root/build/swa-integrated-758Yr8}")
python="$trial/src/.venv/bin/python"
shopt -s nullglob
baselines=("$trial"/src/build/swa-a6-*/L0/summary.json)
[[ ${#baselines[@]} == 1 ]] || { echo "Expected one integrated L0 baseline in $trial" >&2; exit 1; }
base=$(dirname "$(dirname "${baselines[0]}")")
"$python" - "$base/L0/summary.json" "$DEVICE" <<'PY'
import json, sys
baseline = json.load(open(sys.argv[1]))
if baseline["status"] != "passed" or baseline["device"] != int(sys.argv[2]) or baseline["platform"] != "a6":
    raise SystemExit("Select the device used for the validated A6 L0 baseline")
PY
out=$(mktemp -d "$root/build/swa-l1-XXXXXX")
echo "SWA L1 directory: $out"
"$python" -I "$swa/run.py" --platform a6 --device "$DEVICE" --level 1 --warmup 1 --rounds 10 \
    --a6-query "$base/query/query" --build-dir "$base/t25-54" --runtime-lib "$base/lib/a6/onboard" --output "$out/L1"
"$python" - "$base/L0/summary.json" "$out" <<'PY'
import json
from pathlib import Path
import sys

baseline = json.loads(Path(sys.argv[1]).read_bytes())
out = Path(sys.argv[2])
capture = json.loads((out / "L1/summary.json").read_bytes())
if any(capture[k] != baseline[k] for k in ("device", "build", "runtime_sha256")):
    raise SystemExit("L1 artifact or device differs from the integrated L0 baseline")
result, = capture["results"]
if not (result["numerical_validation"] and (result["warmup"], result["rounds"], result["calls_per_round"]) == (1, 10, 560)):
    raise SystemExit("Expected 10 validated rounds of 560 A6 SWA kernel calls")
feedback = {k: v for k, v in result.items() if k != "samples"}
feedback["source_commit"] = capture["build"]["source_commit"]
text = json.dumps(feedback)
(out / "feedback.json").write_text(text + "\n")
print(text)
PY
