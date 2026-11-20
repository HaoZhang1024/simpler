#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Collect paired L4 traces for the two plans from a completed A6 t25 L0 trial."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from t25_report import report_pair

SWA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWA))
from run import allocated_device, check_device  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_run", type=Path)
    parser.add_argument("l0_trial", type=Path, help="Existing swa-t25-* directory")
    parser.add_argument("l4_lib", type=Path, help="Previously verified A6 L4 runtime directory (a6/onboard)")
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--rounds", type=int, choices=range(1, 4), default=3, help="Formal L4 rounds per plan")
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
    for label, case in (("A1", base / "case"), ("B1", trial / "t25-54")):
        l0 = json.loads((trial / label / "summary.json").read_bytes())
        if l0["device"] != device or l0["status"] != "passed" or l0["platform"] != "a6":
            raise ValueError(f"{label}: expected a passing L0 result on the same A6 device")
        bundle = case / "bundle"
        for filename, field in (("plan-rank0.bin", "plan_sha256"), ("callable.bin", "callable_sha256")):
            if hashlib.sha256((bundle / filename).read_bytes()).hexdigest() != l0["build"][field]:
                raise ValueError(f"{label}: {filename} differs from L0")
        dest = output / label
        subprocess.run(["bash", SWA.parent / "dsv41_scheduler/production/run.sh", bundle, args.l4_lib.resolve(),
                        dest, "4", "1", str(args.rounds), "--runtime=percounter"], env=env, check=True)
        golden = json.loads((dest / "rank0/result.json").read_bytes())
        if not (golden["passed"] and golden["validated_against_fused_prefix"]):
            raise ValueError(f"{label}: numerical validation failed")
    report_pair(output)


if __name__ == "__main__":
    main()
