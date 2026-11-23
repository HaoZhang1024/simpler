#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Check the captured Host ABI and adapt only SWA's two MIX task descriptions."""

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from prepare import FIXTURE, HERE, REPO, SUITE, unpack_fixture


def semantic_hash(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_records(tool, path):
    return json.loads(subprocess.check_output([str(tool), "--records-json", str(path)], text=True))


def check_conversion(before, after):
    expected = copy.deepcopy(before)
    changed = []
    for record in expected:
        if record["op"] == 2 and record["id"] in (22, 28):
            record["kernels"][2] = -1
            if record["id"] == 22:
                record["blocks"] *= 2
            changed.append(record["id"])
    if changed != [22, 28] or after != expected:
        raise ValueError("A6 conversion must only change t22/t28 lane masks and t22 block count")
    tasks = [r for r in after if r["op"] == 2 and 8 <= r["id"] <= 35]
    executions = sum(r["blocks"] * sum(k >= 0 for k in r["kernels"]) for r in tasks)
    if len(tasks) != 16 or executions != 570:
        raise ValueError("Expected 16 SWA tasks and 570 A6 kernel instances")
    return executions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cxx", default="g++", help="Host C++ compiler executable, not the AICPU cross compiler")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tools = output / "host"
    tools.mkdir()
    # No runtime or SDK is needed to read the Host submission format.
    flags = [
        args.cxx,
        "-std=c++17",
        "-O2",
        f"-I{SUITE / 'production'}",
        f"-I{REPO / 'src/common'}",
        f"-I{REPO / 'src/common/task_interface'}",
    ]
    for source, target in (
        (SUITE / "production/record_tool.cpp", "record-tool"),
        (HERE / "adapt_plan.cpp", "adapt-plan"),
    ):
        subprocess.run([*flags, str(source), "-o", str(tools / target)], check=True)
    bundle = output / "bundle"
    unpack_fixture(bundle)
    original, converted = bundle / "plan-rank0.bin", output / "plan-a6-rank0.bin"
    before = read_records(tools / "record-tool", original)
    golden = json.loads((FIXTURE / "plan-semantics.json").read_text())
    if len(before) != golden["records"] or semantic_hash(before) != golden["semantic_sha256"]:
        raise ValueError("Host ABI decoded the fixture differently; do not run or convert this capture")
    subprocess.run([str(tools / "adapt-plan"), str(original), str(converted)], check=True)
    after = read_records(tools / "record-tool", converted)
    executions = check_conversion(before, after)
    # Keep the original capture intact; the A6 plan stays separately named.
    summary = {
        "runtime_executed": False,
        "host_compiler": subprocess.check_output([args.cxx, "--version"], text=True).splitlines()[0],
        "original_plan_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "original_semantic_sha256": semantic_hash(before),
        "a6_plan_sha256": hashlib.sha256(converted.read_bytes()).hexdigest(),
        "tasks": 16,
        "a5_executions": 578,
        "a6_executions": executions,
        "changes": [
            {"task": 22, "before": {"blocks": 24, "lanes": "C,V0,V1"}, "after": {"blocks": 48, "lanes": "C,V"}},
            {"task": 28, "before": {"blocks": 32, "lanes": "C,V0,V1"}, "after": {"blocks": 32, "lanes": "C,V"}},
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("Host decode matches A5; only the two expected task descriptions changed. No device execution.")


if __name__ == "__main__":
    main()
