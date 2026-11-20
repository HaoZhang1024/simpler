#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Collect one L4 round for each of the two plans from a completed A6 t25 L0 trial."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SWA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWA))
from run import allocated_device, check_device  # noqa: E402


def read_round(directory, blocks):
    run = directory / "rank0/run1"
    path = run / "chip_swimlane_records.json"
    if path.exists():
        records = json.loads(path.read_bytes())
    else:
        with gzip.open(path.with_suffix(".json.gz"), "rt", encoding="utf-8") as stream:
            records = json.load(stream)
    pairs = [line.split() for line in (run / "source-task-map.txt").read_text().splitlines() if line.strip()]
    mapping = {int(source): int(replay) for source, replay in pairs}
    rows = records["aicore_tasks"]
    hz = records["metadata"]["clock_freq_hz"]
    if (records["chip_swimlane_level"] != 4 or hz <= 0 or len(rows) != 506 + blocks
            or len({r[1] for r in rows}) != 16
            or len({r[6] for r in rows}) != 1 or any(r[4] < r[3] for r in rows)):
        raise ValueError("Expected one complete SWA L4 formal round")

    def task(src):
        return [r for r in rows if r[1] == mapping[src]]

    t22, t25, t28, t35 = map(task, (22, 25, 28, 35))
    if len(t25) != blocks or len(t22) != 96 or len(t28) != 64 or len(t35) != 64:
        raise ValueError("Unexpected SWA task counts in capture")
    start = min(r[3] for r in t25)
    end = max(r[4] for r in t25)
    anchor = max(r[4] for r in t22)
    metrics = (end - start, end - anchor, min(r[3] for r in t28) - anchor, max(r[4] for r in t35) - anchor)
    return len(rows), len({r[0] for r in t25}), [v * 1e6 / hz for v in metrics]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_run", type=Path)
    parser.add_argument("l0_trial", type=Path, help="Existing swa-t25-* directory")
    parser.add_argument("l4_lib", type=Path, help="Previously verified A6 L4 runtime directory (a6/onboard)")
    parser.add_argument("--device", type=int, required=True)
    args = parser.parse_args()
    args.platform = "a6"
    base, trial = args.baseline_run.resolve(), args.l0_trial.resolve()
    args.a6_query = base / "query/query"
    device = allocated_device(parser, args.device) if "TASK_DEVICE" in os.environ else args.device
    check_device(parser, args, device)
    output = Path(tempfile.mkdtemp(prefix="t25-l4-", dir=trial))
    print(f"L4 directory: {output}", flush=True)
    env = dict(os.environ, TASK_DEVICE=str(device), DSV41_RUNNER=str(base / "case/host/native-runner"),
               DSV41_PYTHON=sys.executable)
    values = []
    for label, case, blocks in (("A1", base / "case", 64), ("B1", trial / "t25-54", 54)):
        l0 = json.loads((trial / label / "summary.json").read_bytes())
        if l0["device"] != device or l0["status"] != "passed" or l0["platform"] != "a6":
            raise ValueError(f"{label}: expected a passing L0 result on the same A6 device")
        bundle = case / "bundle"
        for filename, field in (("plan-rank0.bin", "plan_sha256"), ("callable.bin", "callable_sha256")):
            if hashlib.sha256((bundle / filename).read_bytes()).hexdigest() != l0["build"][field]:
                raise ValueError(f"{label}: {filename} differs from L0")
        dest = output / label
        subprocess.run(["bash", SWA.parent / "dsv41_scheduler/production/run.sh", bundle, args.l4_lib.resolve(),
                        dest, "4", "1", "1", "--runtime=percounter"], env=env, check=True)
        golden = json.loads((dest / "rank0/result.json").read_bytes())
        if not (golden["passed"] and golden["validated_against_fused_prefix"]):
            raise ValueError(f"{label}: numerical validation failed")
        total, cores, times = read_round(dest, blocks)
        values.append(times)
        print(f"{label} golden PASS, graph intervals={total}, t25 blocks={blocks}, t25 active AIV={cores}")
    print("metric_us A64 B54 B-A")
    names = ("t25_span", "t22_end_to_t25_end", "t22_end_to_t28_start", "t22_end_to_t35_end")
    for name, a, b in zip(names, *values):
        print(f"{name} {a:.3f} {b:.3f} {b-a:+.3f}")


if __name__ == "__main__":
    main()
