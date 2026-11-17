#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Run the single-device SWA L0 benchmark using the PR runner and timing rules."""

import argparse
import hashlib
import json
import os
import shlex
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRODUCTION = HERE.parent / "dsv41_scheduler/production"


def summarize(output):
    sys.path.insert(0, str(PRODUCTION))
    from timing import paired_spans, summarize_replay  # noqa: PLC0415

    core = summarize_replay(output)
    result = json.loads((output / "rank0/result.json").read_text())
    text = "\n".join(p.read_text() for p in sorted((output / "rank0/host").glob("host.*.log")))
    _, walls = paired_spans(text)
    if len(walls) != 1:
        raise ValueError("SWA requires exactly one device")
    spans = walls[result["device"]]
    if len(spans) != result["warmup"] + result["rounds"]:
        raise ValueError("Unexpected extra invocations in the L0 run")
    wall_ms = [s["duration_ns"] / 1e6 for s in spans[result["warmup"] :]]
    return {
        "runtime": result["runtime"],
        "device": result["device"],
        "profiling_level": 0,
        "warmup": result["warmup"],
        "rounds": result["rounds"],
        "numerical_validation": result["validated_against_fused_prefix"],
        "aicore_mean_ms": core["mean_ms"],
        "aicore_min_ms": min(core["samples_ms"]),
        "aicore_max_ms": max(core["samples_ms"]),
        "aicore_samples_ms": core["samples_ms"],
        "device_mean_ms": statistics.mean(wall_ms),
        "device_samples_ms": wall_ms,
    }


def allocated_device(parser, requested):
    device = os.environ["TASK_DEVICE"]
    if not device.isdigit():
        parser.error("SWA needs one allocated device; TASK_DEVICE must contain a single ID")
    if requested is not None and requested != int(device):
        parser.error("--device differs from the allocated TASK_DEVICE")
    return int(device)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=HERE / "build/a5")
    parser.add_argument("--runtime-lib", type=Path, default=REPO / "build/lib/a5/onboard")
    parser.add_argument("--runtime", choices=["host_build_graph", "percounter", "both"], default="both")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--device", type=int, help="Assigned by task-submit inside its allocation")
    args = parser.parse_args()
    if args.device is not None and not os.environ.get("TASK_DEVICE"):
        parser.error("--device must come from task-submit, not a manual device selection")
    build_dir, output, libraries = args.build_dir.resolve(), args.output.resolve(), args.runtime_lib.resolve()
    if args.warmup < 1 or args.rounds < 1:
        parser.error("Require at least one warmup and one measured round")
    if output.exists():
        parser.error("Output already exists; select a new directory")
    build = json.loads((build_dir / "build.json").read_text())
    if build["platform"] != "a5":
        parser.error("This entry currently validates A5 only; A6 adaptation is pending")
    bundle, runner = build_dir / "bundle", build_dir / "host/native-runner"
    for path, expected in ((runner, build["runner_sha256"]), (bundle / "callable.bin", build["callable_sha256"])):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error(f"Build artifact changed: {path.name}")
    runtimes = ["host_build_graph", "percounter"] if args.runtime == "both" else [args.runtime]
    runtime_files = [libraries / "../dispatcher/libsimpler_aicpu_dispatcher.so"]
    for runtime in runtimes:
        runtime_files += [
            libraries / runtime / name for name in ("libhost_runtime.so", "libaicpu_kernel.so", "aicore_kernel.o")
        ]
    if any(not path.is_file() for path in runtime_files):
        parser.error("Build the selected A5 runtimes and dispatcher first")
    if not os.environ.get("ASCEND_HOME_PATH"):
        parser.error("Source the CANN environment first")
    if not os.environ.get("TASK_DEVICE"):
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--build-dir",
            str(build_dir),
            "--runtime-lib",
            str(libraries),
            "--runtime",
            args.runtime,
            "--output",
            str(output),
            "--warmup",
            str(args.warmup),
            "--rounds",
            str(args.rounds),
        ]
        subprocess.run(
            ["task-submit", "--device", "auto", "--device-num", "1", "--max-time", "300", "--run", shlex.join(command)],
            check=True,
        )
        return
    device = allocated_device(parser, args.device)
    subprocess.run(["bash", str(REPO / ".claude/skills/onboard-arch-precheck/check.sh"), "a5"], check=True)
    output.mkdir(parents=True)
    environment = {**os.environ, "DSV41_RUNNER": str(runner), "DSV41_PYTHON": sys.executable}
    record = {
        "case": "swa",
        "platform": "a5",
        "device": device,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "build": build,
        "runtime_sha256": {
            p.resolve().relative_to(libraries.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in runtime_files
        },
        "status": "running",
        "results": [],
    }
    try:
        for runtime in runtimes:
            destination = output / runtime
            command = [
                "bash",
                str(PRODUCTION / "run.sh"),
                str(bundle),
                str(libraries),
                str(destination),
                "0",
                str(args.warmup),
                str(args.rounds),
                f"--runtime={runtime}",
            ]
            subprocess.run(command, env=environment, check=True)
            record["results"].append(summarize(destination))
        record["status"] = "passed"
    except Exception:
        record["status"] = "failed"
        raise
    finally:
        record["end_time"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print("\nruntime             AICore mean (ms)  Device mean (ms)  output check")
    for result in record["results"]:
        print(f"{result['runtime']:20} {result['aicore_mean_ms']:16.6f}  {result['device_mean_ms']:16.6f}  PASS")


if __name__ == "__main__":
    main()
