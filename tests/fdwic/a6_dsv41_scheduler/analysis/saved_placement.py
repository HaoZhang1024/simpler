#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Report the fixed-worker bound from a completed SWA bound run without running the device."""

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from swa_sync_bound import (
    CAPACITIES, QUANTUM_NS, ROWS_PER_ROUND, KernelExecution, analyze_placement,
    check_completion_order, checked_run, placement_summary, read_json,
)


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def saved_round(blocks, raw, iteration, tasks):
    scheduler = raw["scheduler_tasks"]
    meta = raw["metadata"]
    hz = meta["clock_freq_hz"]
    if (raw["chip_swimlane_level"] != 2 or meta["runtime"] != "percounter" or hz <= 0
            or Counter(meta["core_types"]) != CAPACITIES or scheduler["producer"] != "aicore"):
        raise ValueError(f"Unexpected L2 metadata in round {iteration}")
    registers = {(w, reg, epoch): (dispatch, finish) for w, reg, dispatch, finish, epoch in scheduler["records"]}
    times = {}
    for w, tid, reg, start, _, _, epoch in raw["aicore_tasks"]:
        times[w, tid, start] = registers.pop((w, reg, epoch))
    if registers or len(times) != len(scheduler["records"]) or len(blocks) != ROWS_PER_ROUND:
        raise ValueError(f"Incomplete scheduler timing in round {iteration}")
    rows, keys = [], set()
    for b in blocks:
        worker, tid, start, end = (int(b[k]) for k in ("worker", "task_id", "start_cycles", "kernel_end_cycles"))
        dispatch, finish = times.pop((worker, tid, start))
        source, block, lane = (int(b[k]) for k in ("source_task", "block_idx", "subtask_slot"))
        key = (tid, block, lane)
        ticks = (end - start) * 10**9 // (hz * QUANTUM_NS)
        if (not 0 < dispatch <= start < end <= finish or int(b["clock_hz"]) != hz
                or int(b["duration_ticks"]) != ticks or int(tasks[tid]["source_task"]) != source
                or not 0 <= block < int(tasks[tid]["block_num"]) or key in keys or lane not in (0, 1)
                or not 0 <= worker < len(meta["core_types"])
                or meta["core_types"][worker] != b["core_type"] or b["core_type"] != ("aic", "aiv")[lane]):
            raise ValueError(f"Invalid block timing at t{source} block {block} in round {iteration}")
        keys.add(key)
        rows.append(KernelExecution(iteration, source, tid, block, lane, b["core_type"], worker,
                                    int(b["func_id"]), start, end, hz, ticks, dispatch, finish))
    if times:
        raise ValueError(f"Unused L2 rows in round {iteration}")
    return rows


def report(run):
    model = run / "model"
    prior = read_json(model / "summary.json")
    base, l0 = checked_run(run / "L0", prior["build"], 0)
    capture, _ = checked_run(run / "L2", prior["build"], 2)
    if (prior["t25_block_num"] != 54 or prior["quantum_ns"] != QUANTUM_NS or prior["capacities"] != CAPACITIES
            or any(r["device"] != prior["device"] or r["runtime_sha256"] != prior["runtime_sha256"]
                   for r in (base, capture))):
        raise ValueError("Model, L0 and L2 must describe the same 54-block run")
    blocks = defaultdict(list)
    for row in csv_rows(model / "blocks.csv"):
        blocks[int(row["round"])].append(row)
    if set(blocks) != set(range(1, 11)):
        raise ValueError("Expected ten measured rounds")
    tasks = {int(t["task_id"]): t for t in csv_rows(model / "tasks.csv")}
    nodes = {tid: {"sync": bool(int(t["sync_start"]))} for tid, t in tasks.items()}
    edges = [(int(e["pred_task_id"]), int(e["succ_task_id"])) for e in csv_rows(model / "edges.csv")]
    results = []
    for i in sorted(blocks):
        raw = read_json(run / "L2/percounter/rank0" / f"run{i}/chip_swimlane_records.json")
        rows = saved_round(blocks[i], raw, i, tasks)
        spans = {}
        for r in rows:
            lo, hi = spans.get(r.task_id, (r.start_cycles, r.kernel_end_cycles))
            spans[r.task_id] = min(lo, r.start_cycles), max(hi, r.kernel_end_cycles)
        check_completion_order(nodes, edges, spans, {tid: t["source_task"] for tid, t in tasks.items()})
        results.append(analyze_placement(nodes, edges, rows))
    summary = placement_summary(results)
    for task in summary["l2_top_chain_gaps"]:
        candidates = [(i, step) for i, result in enumerate(results, 1)
                      for step in result["chain"] if step["task"] == task["task"]]
        i, step = max(candidates, key=lambda item: item[1]["gap_us"])
        task["largest_observed_gap"] = {"round": i, **step}
    return {
        "device": prior["device"], "lower_bound_mean_us": prior["lower_bound_mean_us"],
        "aicore_l0_mean_us": statistics.mean(l0["aicore_samples_ms"]) * 1000,
        "device_l0_mean_us": l0["device_mean_ms"] * 1000,
        **summary,
        "fixed_order_us_by_round": [r["fixed_order_us"] for r in results],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Completed directory containing model/, L0/ and L2/")
    print(json.dumps(report(parser.parse_args().run), indent=2))
