#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Run the single-device SWA benchmark or collect A6 per-block L2 timings."""

import argparse
import hashlib
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRODUCTION = HERE.parent / "dsv41_scheduler/production"


def summarize(output, level=0):
    result = json.loads((output / "rank0/result.json").read_text())
    if level == 2:
        if not (result["passed"] and result["validated_against_fused_prefix"]):
            raise ValueError("L2 capture failed numerical validation")
        return {
            "runtime": result["runtime"],
            "profiling_level": level,
            "warmup": result["warmup"],
            "rounds": result["rounds"],
            "numerical_validation": True,
        }

    sys.path.insert(0, str(PRODUCTION))
    from timing import paired_spans, summarize_replay  # noqa: PLC0415

    core = summarize_replay(output)
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


def parse_options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["a5", "a6"], default="a5")
    parser.add_argument("--a6-query", type=Path, help="Built tools/cann-examples/query executable")
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--runtime-lib", type=Path)
    parser.add_argument("--runtime", choices=["host_build_graph", "percounter", "both"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--level", type=int, choices=(0, 2), default=0, help="Use L2 for A6 block capture")
    parser.add_argument("--device", type=int, help="Allocated device ID (required on A6 unless TASK_DEVICE is set)")
    args = parser.parse_args()
    args.runtime = args.runtime or ("percounter" if args.platform == "a6" else "both")
    if args.level == 2 and args.platform != "a6":
        parser.error("--level 2 is supported here only for A6 Percounter")
    if args.platform == "a6":
        if args.runtime != "percounter" or not args.a6_query:
            parser.error("A6 requires percounter and --a6-query")
        if args.device is None and not os.environ.get("TASK_DEVICE"):
            parser.error("Provide --device for the assigned A6 device")
        if args.device is not None and args.device < 0:
            parser.error("--device must be nonnegative")
    elif args.device is not None and not os.environ.get("TASK_DEVICE"):
        parser.error("--device must come from task-submit, not a manual device selection")
    return parser, args


def check_device(parser, args, device):
    if args.platform == "a6":
        query = subprocess.check_output([str(args.a6_query.resolve()), "device", str(device)], text=True)
        if not re.search(r"^\s*soc_name:\s+Ascend960DT_966B7(?:\s|$)", query, re.MULTILINE):
            parser.error(f"Expected Ascend960DT_966B7 on device {device}; query returned:\n{query}")
    else:
        subprocess.run(["bash", str(REPO / ".claude/skills/onboard-arch-precheck/check.sh"), "a5"], check=True)


def main():
    parser, args = parse_options()
    build_dir = (args.build_dir or HERE / "build" / args.platform).resolve()
    libraries = (args.runtime_lib or REPO / "build/lib" / args.platform / "onboard").resolve()
    output = args.output.resolve()
    if args.warmup < 1 or args.rounds < 1:
        parser.error("Require at least one warmup and one measured round")
    if output.exists():
        parser.error("Output already exists; select a new directory")
    build = json.loads((build_dir / "build.json").read_text())
    if build["platform"] != args.platform:
        parser.error("Build and requested platform differ")
    bundle, runner = build_dir / "bundle", build_dir / "host/native-runner"
    for path, expected in ((runner, build["runner_sha256"]), (bundle / "callable.bin", build["callable_sha256"])):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            parser.error(f"Build artifact changed: {path.name}")
    if (
        args.platform == "a6"
        and hashlib.sha256((bundle / "plan-rank0.bin").read_bytes()).hexdigest() != build["plan_sha256"]
    ):
        parser.error("A6 replay plan differs from the prepared plan")
    runtimes = ["host_build_graph", "percounter"] if args.runtime == "both" else [args.runtime]
    runtime_files = [libraries / "../dispatcher/libsimpler_aicpu_dispatcher.so"]
    for runtime in runtimes:
        runtime_files += [
            libraries / runtime / name for name in ("libhost_runtime.so", "libaicpu_kernel.so", "aicore_kernel.o")
        ]
    if any(not path.is_file() for path in runtime_files):
        parser.error("Build the selected runtimes and dispatcher first")
    if not os.environ.get("ASCEND_HOME_PATH"):
        parser.error("Source the CANN environment first")
    if args.platform == "a5" and not os.environ.get("TASK_DEVICE"):
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
    device = allocated_device(parser, args.device) if os.environ.get("TASK_DEVICE") else args.device
    check_device(parser, args, device)
    output.mkdir(parents=True)
    environment = {
        **os.environ,
        "TASK_DEVICE": str(device),
        "DSV41_RUNNER": str(runner),
        "DSV41_PYTHON": sys.executable,
    }
    record = {
        "case": "swa",
        "platform": args.platform,
        "device": device,
        "profiling_level": args.level,
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
                str(args.level),
                str(args.warmup),
                str(args.rounds),
                f"--runtime={runtime}",
            ]
            subprocess.run(command, env=environment, check=True)
            record["results"].append(summarize(destination, args.level))
        record["status"] = "passed"
    except Exception:
        record["status"] = "failed"
        raise
    finally:
        record["end_time"] = datetime.now(timezone.utc).isoformat()
        (output / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print_results(output, record)


def print_results(output, record):
    if record["profiling_level"] == 2:
        print(f"L2 capture and numerical validation passed: {output}")
        return
    print("\nruntime             AICore mean (ms)  Device mean (ms)  output check")
    for result in record["results"]:
        print(f"{result['runtime']:20} {result['aicore_mean_ms']:16.6f}  {result['device_mean_ms']:16.6f}  PASS")


if __name__ == "__main__":
    main()
