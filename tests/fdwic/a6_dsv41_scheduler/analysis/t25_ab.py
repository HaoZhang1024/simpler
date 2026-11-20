#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Compare 64 and 54 t25 blocks using one prepared A6 SWA build and one runtime."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SWA = Path(__file__).resolve().parents[1]
REPO = SWA.parents[2]


def split_plan(tool, plan):
    return json.loads(subprocess.check_output([tool, "--records-json", plan]))


def verify_plans(before, after):
    tasks = {r["id"]: r for r in before if r["op"] == 2 and 8 <= r["id"] <= 35}
    count = sum(r["blocks"] * sum(k >= 0 for k in r["kernels"]) for r in tasks.values())
    if len(tasks) != 16 or count != 570 or tasks[22]["blocks"] != 48 or tasks[28]["kernels"] != [21, 22, -1]:
        raise ValueError("Expected the measured 1C1V SWA baseline")
    t25 = tasks[25]
    if t25["blocks"] != 64 or t25["kernels"] != [-1, 20, -1] or t25["scalars"] != [72, 8, 80]:
        raise ValueError("Expected t25 with 72 active rows, 8 groups and capacity 80")
    expected = [dict(r, blocks=54) if r is t25 else r for r in before]
    if after != expected:
        raise ValueError("Trial must change only t25.block_num")


def prepare_trial(case, output, cxx):
    build = json.loads((case / "build.json").read_bytes())
    source = case / "bundle/plan-rank0.bin"
    if build["platform"] != "a6" or hashlib.sha256(source.read_bytes()).hexdigest() != build["plan_sha256"]:
        raise ValueError("Expected a prepared A6 case matching its build.json")
    tool = case / "host/record-tool"
    trial = output / "t25-54"
    bundle = trial / "bundle"
    bundle.mkdir(parents=True)
    target = bundle / source.name
    converter = output / "adapt-plan"
    subprocess.run([cxx, "-std=c++17", "-O2", "-I" + str(SWA.parent / "dsv41_scheduler/production"),
                    "-I" + str(REPO / "src/common"), "-I" + str(REPO / "src/common/task_interface"),
                    SWA / "adapt_plan.cpp", "-o", converter], check=True)
    subprocess.run([converter, source, target, "--t25-54"], check=True)
    verify_plans(split_plan(tool, source), split_plan(tool, target))
    for path in source.parent.iterdir():
        if path.name != source.name:
            (bundle / path.name).symlink_to(path, target_is_directory=path.is_dir())
    (trial / "host").symlink_to(case / "host", target_is_directory=True)
    build.update(plan_sha256=hashlib.sha256(target.read_bytes()).hexdigest(), executions=560)
    (trial / "build.json").write_text(json.dumps(build, indent=2) + "\n")
    return trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_run", type=Path, help="Directory containing case/, lib/ and query/query")
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    base = args.baseline_run.resolve()
    output = Path(tempfile.mkdtemp(prefix="swa-t25-", dir=base.parent))
    print(f"Experiment directory: {output}", flush=True)
    case = base / "case"
    trial = prepare_trial(case, output, args.cxx)
    timings = {}
    for label, build in (("A1", case), ("B1", trial), ("B2", trial), ("A2", case)):
        destination = output / label
        subprocess.run([sys.executable, SWA / "run.py", "--platform", "a6", "--device", str(args.device),
                        "--a6-query", base / "query/query", "--runtime-lib", base / "lib/a6/onboard",
                        "--build-dir", build, "--output", destination, "--warmup", "1", "--rounds", "10"], check=True)
        summary = json.loads((destination / "summary.json").read_bytes())
        (result,) = summary["results"]
        if summary["status"] != "passed" or not result["numerical_validation"]:
            raise ValueError(f"{label} failed numerical validation")
        timings[label] = [round(1000 * result[key], 3) for key in ("aicore_mean_ms", "device_mean_ms")]
    print("batch  AICore_us  Device_us")
    for label, (core, device) in timings.items():
        print(f"{label:5} {core:10.3f} {device:10.3f}")
    print("Golden PASS (4 batches). Negative B-A means faster.")
    for key, idx in (("AICore", 0), ("Device", 1)):
        a1, b1, b2, a2 = (row[idx] for row in timings.values())
        print(f"{key}: B1-A1={b1-a1:+.3f}, B2-A2={b2-a2:+.3f}, A2-A1={a2-a1:+.3f} us")


if __name__ == "__main__":
    main()
