#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Solve the synchronization-constrained bound for the A6 t25=54 SWA replay."""

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path

from t25_ab import REPO, SWA, split_plan

sys.path[:0] = [str(REPO), str(SWA.parent / "dsv41_scheduler/production")]
from ideal_bound import complete_flat_dag  # noqa: E402
from sync_bound import QUANTUM_NS, solve_model  # noqa: E402

CAPACITIES = {"aic": 54, "aiv": 54}
ROWS_PER_ROUND = 560
MANIFEST_KEYS = ("plan_sha256", "callable_sha256", "runner_sha256")


def read_json(path):
    return json.loads(path.read_bytes())


def checked_run(path, build, level):
    data = read_json(path / "summary.json")
    (result,) = data["results"]
    if (
        data["platform"] != "a6"
        or data["case"] != "swa"
        or data["status"] != "passed"
        or result["runtime"] != "percounter"
        or result["profiling_level"] != level
        or result["warmup"] != 1
        or result["rounds"] != 10
        or not result["numerical_validation"]
        or any(data["build"][key] != build[key] for key in MANIFEST_KEYS)
    ):
        raise ValueError(f"Expected a passing matching A6 L{level} run: {path}")
    return data, result


def read_plan(case):
    build = read_json(case / "build.json")
    plan = case / "bundle/plan-rank0.bin"
    if (
        build["platform"] != "a6"
        or build["executions"] != ROWS_PER_ROUND
        or hashlib.sha256(plan.read_bytes()).hexdigest() != build["plan_sha256"]
    ):
        raise ValueError("Expected the prepared A6 t25=54 plan and matching build.json")
    tasks = {
        r["id"]: r
        for r in split_plan(case / "host/record-tool", plan)
        if r["op"] == 2 and 8 <= r["id"] <= 35 and any(k >= 0 for k in r["kernels"])
    }
    if (
        len(tasks) != 16
        or not {22, 25} <= tasks.keys()
        or (tasks[22]["blocks"], tasks[22]["kernels"], tasks[22]["sync"]) != (48, [18, 19, -1], 1)
        or (tasks[25]["blocks"], tasks[25]["kernels"], tasks[25]["sync"]) != (54, [-1, 20, -1], 0)
        or tasks[25]["scalars"] != [72, 8, 80]
    ):
        raise ValueError("Expected the frozen A6 SWA launch geometry and t25 inputs")
    return build, tasks


def read_round(folder, plan_tasks, iteration):
    raw = read_json(folder / "chip_swimlane_records.json")
    meta = raw["metadata"]
    kinds, hz = meta["core_types"], meta["clock_freq_hz"]
    scheduler = raw.get("scheduler_tasks") or {}
    events = raw.get("percounter_task_events") or {}
    if (
        raw["chip_swimlane_level"] != 2
        or meta["runtime"] != "percounter"
        or Counter(kinds) != CAPACITIES
        or hz <= 0
        or scheduler.get("producer") != "aicore"
        or events.get("dropped") != 0
        or events.get("unmatched_deferred_updates") != 0
        or "records" not in events
    ):
        raise ValueError(f"Expected an A6 54C+54V Percounter L2 block capture: {folder}")

    mapping_path = folder / "source-task-map.txt"
    pairs = [tuple(map(int, row.split())) for row in mapping_path.read_text().splitlines()]
    mapping = {target: source for source, target in pairs}
    deps = complete_flat_dag(read_json(folder / "deps.json"), mapping_path, set(plan_tasks), 1)
    nodes, expected = {}, {}
    for task in deps["tasks"]:
        tid = int(task["task_id"])
        if tid in nodes or tid not in mapping:
            raise ValueError("Unexpected dependency task ID in SWA capture")
        source = mapping[tid]
        plan = plan_tasks.get(source)
        kernels = task["kernel_ids"]
        if plan is not None:
            if (kernels, task["block_num"]) != (plan["kernels"], plan["blocks"]):
                raise ValueError(f"Kernel IDs or block count differ from plan for t{source}")
            for lane, kernel in enumerate(kernels):
                if kernel >= 0:
                    for block in range(plan["blocks"]):
                        expected[tid, block, lane] = kernel
        elif any(k >= 0 for k in kernels):
            raise ValueError(f"Unexpected compute node t{source}")
        nodes[tid] = {"sync": bool(plan and plan["sync"]), "units": []}

    executions = [event for event in events["records"] if event["kind"] == "kernel_end"]
    timing = {
        (e["worker_id"], int(e["task_id"]), e["kernel_start_cycles"], e["cycles"], e["run_epoch"]): e
        for e in executions
    }
    spans, rows, seen = {}, [], set()
    if len(timing) != len(executions) or len(timing) != ROWS_PER_ROUND:
        raise ValueError("Missing or duplicate per-block timing records")
    for worker, tid, _, start, end, _, epoch in raw["aicore_tasks"]:
        event = timing.pop((worker, tid, start, end, epoch), None)
        plan = plan_tasks.get(mapping.get(tid))
        if event is None or plan is None or event["block_count"] != plan["blocks"]:
            raise ValueError("L2 worker row and kernel_end event disagree")
        block, lane, finish = event["block_index"], event["cluster_lane"], event["finish_cycles"]
        key = (tid, block, lane)
        kind = "aic" if lane == 0 else "aiv"
        if (
            key not in expected
            or key in seen
            or not 0 <= worker < len(kinds)
            or kinds[worker] != kind
            or not 0 < start < end <= finish
        ):
            raise ValueError(f"Invalid or duplicate execution {key} on worker {worker}")
        seen.add(key)
        ticks = (end - start) * 10**9 // (hz * QUANTUM_NS)
        nodes[tid]["units"].append((block, lane, kind, ticks))
        first, last = spans.get(tid, (start, end))
        spans[tid] = (min(first, start), max(last, end))
        rows.append((iteration, mapping[tid], tid, block, lane, kind, worker, expected[key], start, end, hz, ticks))
    if timing or seen != expected.keys() or len(seen) != ROWS_PER_ROUND:
        raise ValueError("Expected 560 unique SWA executions")

    edges = sorted({(int(e["pred"]), int(e["succ"])) for e in deps["edges"]})
    check_completion_order(nodes, edges, spans, mapping)
    return nodes, edges, rows, mapping


def check_completion_order(nodes, edges, spans, mapping):
    preds = {tid: [] for tid in nodes}
    for pred, succ in edges:
        preds[succ].append(pred)
    finish = {}
    for tid in TopologicalSorter(preds).static_order():
        ready = max((finish[pred] for pred in preds[tid]), default=0)
        if tid in spans and spans[tid][0] < ready:
            raise ValueError(f"Observed early release at t{mapping[tid]} is outside the task-completion model")
        finish[tid] = spans[tid][1] if tid in spans else ready


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Prepared t25-54 directory containing build.json, bundle and host")
    parser.add_argument("l0", type=Path, help="A6 run.py output directory for L0")
    parser.add_argument("capture", type=Path, help="A6 run.py output directory for L2")
    parser.add_argument("output", type=Path, help="Fresh output directory for the bound and compact input tables")
    parser.add_argument("--time-limit", type=float, default=30, help="Maximum solver seconds per round")
    args = parser.parse_args()
    build, plan_tasks = read_plan(args.case)
    l0_run, l0 = checked_run(args.l0, build, 0)
    capture_run, _ = checked_run(args.capture, build, 2)
    if l0_run["device"] != capture_run["device"] or l0_run["runtime_sha256"] != capture_run["runtime_sha256"]:
        raise ValueError("L0 and L2 must use the same A6 device and runtime binaries")
    l0_samples = [ms * 1000 for ms in l0["aicore_samples_ms"]]
    if len(l0_samples) != 10 or any(not math.isfinite(us) or us <= 0 for us in l0_samples):
        raise ValueError("Expected ten positive L0 AICore wall samples")

    rank = args.capture / "percounter/rank0"
    rounds = [read_round(rank / f"run{i}", plan_tasks, i) for i in range(1, 11)]
    _, edges, _, mapping = rounds[0]
    if any(other_edges != edges or other_mapping != mapping for _, other_edges, _, other_mapping in rounds):
        raise ValueError("The SWA dependency graph changed across L2 rounds")
    args.output.mkdir(parents=True)
    write_csv(
        args.output / "blocks.csv",
        (
            "round",
            "source_task",
            "task_id",
            "block_idx",
            "subtask_slot",
            "core_type",
            "worker",
            "func_id",
            "start_cycles",
            "kernel_end_cycles",
            "clock_hz",
            "duration_ticks",
        ),
        (row for _, _, rows, _ in rounds for row in sorted(rows)),
    )
    nodes = rounds[0][0]
    write_csv(
        args.output / "tasks.csv",
        ("task_id", "source_task", "block_num", "sync_start"),
        (
            (tid, mapping[tid], plan_tasks.get(mapping[tid], {}).get("blocks", 0), int(node["sync"]))
            for tid, node in sorted(nodes.items())
        ),
    )
    write_csv(args.output / "edges.csv", ("pred_task_id", "succ_task_id"), edges)
    write_csv(args.output / "l0.csv", ("round", "aicore_wall_us"), enumerate(l0_samples, 1))
    results = []
    for i, (nodes, _, _, _) in enumerate(rounds, 1):
        solved = solve_model(nodes, edges, CAPACITIES, args.time_limit)
        lower_us = solved["lower_ticks"] * QUANTUM_NS / 1000
        feasible = solved["feasible_ticks"]
        results.append(
            {
                "round": i,
                "status": solved["status"],
                "optimal": solved["optimal"],
                "lower_bound_us": lower_us,
                "feasible_us": None if feasible is None else feasible * QUANTUM_NS / 1000,
            }
        )
        print(json.dumps(results[-1]), flush=True)
    mean_l0 = statistics.mean(l0_samples)
    mean_bound = statistics.mean(row["lower_bound_us"] for row in results)
    feasible_values = [row["feasible_us"] for row in results if row["feasible_us"] is not None]
    summary = {
        "platform": "a6",
        "case": "swa",
        "device": capture_run["device"],
        "runtime_sha256": capture_run["runtime_sha256"],
        "build": build,
        "t25_block_num": 54,
        "capacities": CAPACITIES,
        "capture_level": 2,
        "quantum_ns": QUANTUM_NS,
        "time_limit_seconds_per_round": args.time_limit,
        "executions_per_round": ROWS_PER_ROUND,
        "aicore_wall_l0_mean_us": mean_l0,
        "lower_bound_mean_us": mean_bound,
        "feasible_mean_us": statistics.mean(feasible_values) if len(feasible_values) == len(results) else None,
        "all_optimal": all(row["optimal"] for row in results),
        "excess_us": mean_l0 - mean_bound,
        "excess_percent_of_bound": (mean_l0 / mean_bound - 1) * 100,
        "rounds": results,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in ("build", "rounds")}, indent=2))


if __name__ == "__main__":
    main()
