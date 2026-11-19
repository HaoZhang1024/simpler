#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Summarize SWA t22/t25/t35 from one converted percounter L4 Worker View."""

import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


def summarize(trace, mapping):
    # Use the worker track: scheduler tracks may nest additional copies of kernel intervals.
    workers = {
        event["pid"]
        for event in trace["traceEvents"]
        if event.get("name") == "process_name" and event.get("args", {}).get("name") == "Worker View"
    }
    if len(workers) != 1:
        raise ValueError("Expected one Worker View process")
    tasks = defaultdict(list)
    for event in trace["traceEvents"]:
        args = event.get("args", {})
        if event.get("pid") in workers and event.get("ph") == "X" and "kernel-start-time-us" in args:
            tasks[mapping[args["taskId"]]].append(args)
    count = sum(map(len, tasks.values()))
    if len(tasks) != 16 or count not in (570, 578):
        raise ValueError(f"Expected one complete SWA invocation, found {len(tasks)} tasks and {count} intervals")

    def first(task):
        return min(row["kernel-start-time-us"] for row in tasks[task])

    def last(task):
        return max(row["kernel-end-time-us"] for row in tasks[task])

    origin = min(map(first, tasks))
    result = {"executions": count, "kernel_window_us": round(max(map(last, tasks)) - origin, 3), "tasks": []}
    for task in (22, 25, 35):
        rows = tasks[task]
        starts = [row["kernel-start-time-us"] for row in rows]
        first_dispatch = min(row["dispatch-time-us"] for row in rows)
        by_core = defaultdict(list)
        by_func = defaultdict(list)
        for row in rows:
            identity = re.search(r"FuncId:(\d+), CoreId:(\d+)", row["event-hint"])
            if identity is None:
                raise ValueError(f"Missing function/core identity on task {task}")
            func, core = map(int, identity.groups())
            by_core[core].append((row["kernel-start-time-us"], row["kernel-end-time-us"]))
            by_func[func].append(row["kernel-end-time-us"] - row["kernel-start-time-us"])
        expected = {22: {18: 24 if count == 578 else 48, 19: 48}, 25: {20: 64}, 35: {27: 64}}
        if {func: len(times) for func, times in by_func.items()} != expected[task]:
            raise ValueError(f"Unexpected function counts on source task {task}; check trace and replay mapping")
        preds = [mapping[int(i)] for i in re.findall(r"t(\d+)", rows[0]["fanin-hint"])]
        latest = max((pred for pred in preds if pred in tasks), key=last)
        gaps = []
        for intervals in by_core.values():
            ordered = sorted(intervals)
            gaps.extend(right[0] - left[1] for left, right in zip(ordered, ordered[1:]))
        result["tasks"].append(
            {
                "source_task": task,
                "intervals": len(rows),
                "active_cores": len(by_core),
                "executions_per_core_histogram": dict(sorted(Counter(map(len, by_core.values())).items())),
                "reuse_gap_median_us": round(median(gaps), 3) if gaps else None,
                "first_kernel_us": round(min(starts) - origin, 3),
                "last_kernel_end_us": round(last(task) - origin, 3),
                "span_us": round(last(task) - min(starts), 3),
                "start_spread_us": round(max(starts) - min(starts), 3),
                "latest_compute_pred": latest,
                "other_preds_without_kernel": [p for p in preds if p not in tasks],
                "pred_end_to_first_dispatch_us": round(first_dispatch - last(latest), 3),
                "first_dispatch_to_first_kernel_us": round(min(starts) - first_dispatch, 3),
                "kernel_us_by_func": {
                    k: {"n": len(v), "median": round(median(v), 3), "max": round(max(v), 3)}
                    for k, v in sorted(by_func.items())
                },
            }
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("source_task_map", type=Path)
    args = parser.parse_args()
    pairs = [line.split() for line in args.source_task_map.read_text().splitlines() if line.strip()]
    with (gzip.open if args.trace.suffix == ".gz" else open)(args.trace, "rt", encoding="utf-8") as stream:
        print(json.dumps(summarize(json.load(stream), {int(replay): int(src) for src, replay in pairs}), indent=2))
