#!/usr/bin/env bash
# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail

: "${DEVICE:?Set DEVICE to the allocated A6 card (baseline used device 0)}"
: "${ASCEND_HOME_PATH:?Load the A6 CANN environment}"
base=$(cd "$(dirname "$0")/../../../.." && pwd)
mkdir -p "$base/build"
trial=$(mktemp -d "$base/build/swa-integrated-XXXXXX")
echo "Comparison directory: $trial"
exec > >(tee "$trial/comparison.log") 2>&1

checkout() {
    git init -q "$1"
    git -C "$1" fetch -q --depth 1 "$2" "$3"
    git -C "$1" checkout -q --detach FETCH_HEAD
    [[ $(git -C "$1" rev-parse HEAD) == "$3" ]]
}
revision=$(git -C "$base" rev-parse HEAD)
echo "Simpler source: $revision"
checkout "$trial/src" "$base" "$revision"
cd "$trial/src"
checkout build/pto-isa https://github.com/hw-native-sys/pto-isa.git "$(cat pto_isa.pin)"

python -m venv --system-site-packages .venv
source .venv/bin/activate
export PYTHONPATH="$PWD/python:$PWD"
python -m pip install 'cloudpickle>=2.2' -r tests/fdwic/dsv41_scheduler/production/requirements-bound.txt
# Check both interpreter modes used by the runtime builder and SWA kernel preparation.
for mode in normal isolated; do
    flags=()
    if [[ $mode == isolated ]]; then flags=(-I); fi
    python "${flags[@]}" - <<'PY'
from importlib.util import find_spec
from pathlib import Path
import sys
root = Path.cwd()
sys.path[:0] = [str(root), str(root / "python")]
for package, expected in (("simpler_setup", root / "simpler_setup"), ("simpler", root / "python/simpler")):
    path = Path(find_spec(package).origin).resolve()
    print(package, path)
    if path.parent != expected.resolve():
        raise SystemExit(f"Expected {expected}, found {path}")
PY
done
SWA_SYNC_BOUND=1 bash tests/fdwic/a6_dsv41_scheduler/test_a6_swa.sh "$DEVICE"
python - "$trial/feedback.json" <<'PY'
import json
from pathlib import Path
import sys
summary_path, = Path("build").glob("swa-a6-*/model/summary.json")
s = json.loads(summary_path.read_text())
rounds = s["rounds"]
feedback = {k: v for k, v in s.items() if k not in ("build", "rounds")}
feedback["source_commit"] = s["build"]["source_commit"]
feedback["aicore_l0_samples_us"] = [
    float(line.split(",")[1]) for line in (summary_path.parent / "l0.csv").read_text().splitlines()[1:]
]
feedback["critical_chain_by_source_task"] = {}
for task in (22, 9, 35):
    steps = [step for r in rounds for step in r["chain"] if step["task"] == task]
    feedback["critical_chain_by_source_task"][task] = {
        "rounds_present": sum(any(step["task"] == task for step in r["chain"]) for r in rounds),
        **{key: sum(step[key] for step in steps) / len(rounds)
           for key in ("gap_us", "gap_before_dispatch_us", "gap_after_dispatch_us")},
    }
text = json.dumps(feedback, indent=2)
Path(sys.argv[1]).write_text(text + "\n")
print(text)
PY
echo "Feedback: $trial/feedback.json"
