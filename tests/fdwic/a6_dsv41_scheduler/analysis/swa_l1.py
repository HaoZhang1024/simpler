# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
"""Summarize measured percounter SWA L1 intervals, preserving overlap across workers."""

import argparse
import json
import statistics
from collections import Counter
from graphlib import TopologicalSorter
from pathlib import Path


def chain_time(graph, intervals, previous):
    # Trace the latest visible blocker, either a DAG predecessor or the previous call on this core.
    parents = {int(task["task_id"]): [] for task in graph["tasks"]}
    for edge in graph["edges"]:
        parents.setdefault(int(edge["succ"]), []).append(int(edge["pred"]))
    last = {}
    for i, row in enumerate(intervals):
        tid = int(row[1])
        if tid not in last or row[4] > intervals[last[tid]][4]:
            last[tid] = i
    incoming = {}
    for tid in TopologicalSorter(parents).static_order():
        candidates = [last[p] for p in parents.get(tid, ()) if last.get(p) is not None]
        incoming[tid] = max(candidates, key=lambda i: intervals[i][4], default=None)
        last.setdefault(tid, incoming[tid])
    index = max(range(len(intervals)), key=lambda i: intervals[i][4])
    total = 0
    while index is not None:
        _, tid, _, start, finish, *_ = intervals[index]
        total += finish - start
        candidates = (incoming[int(tid)], previous[index])
        index = max((i for i in candidates if i is not None), key=lambda i: intervals[i][4], default=None)
        if index is not None and intervals[index][4] > start:
            raise ValueError("Visible predecessor overlaps the L1 window")
    return total


def round_times(directory):
    raw = json.loads((directory / "chip_swimlane_records.json").read_bytes())
    meta = raw["metadata"]
    if raw["chip_swimlane_level"] != 1 or meta["runtime"] != "percounter" or meta["clock_freq_hz"] <= 0:
        raise ValueError(f"Expected a percounter L1 trace in {directory}")
    kinds = meta["core_types"]
    graph = json.loads((directory / "deps.json").read_bytes())
    expected = Counter()
    for task in graph["tasks"]:
        for slot, kernel in enumerate(task["kernel_ids"]):
            if kernel >= 0:
                expected[int(task["task_id"]), "aic" if slot == 0 else "aiv"] += task["block_num"]

    intervals = sorted(raw["aicore_tasks"], key=lambda row: row[3])
    calls = Counter()
    work = Counter()
    last = {}
    previous = []
    registrations = set()
    epochs = set()
    busy = 0
    right = 0
    for i, (worker, tid, registration, start, finish, _, epoch) in enumerate(intervals):
        key = worker, registration, epoch
        if not 0 <= worker < len(kinds) or not 0 < start < finish or key in registrations:
            raise ValueError(f"Invalid or repeated worker interval in {directory}")
        previous.append(last.get(worker))
        if worker in last and intervals[last[worker]][4] > start:
            raise ValueError(f"Overlapping intervals on worker {worker}")
        last[worker] = i
        registrations.add(key)
        epochs.add(epoch)
        kind = kinds[worker]
        calls[int(tid), kind] += 1
        work[kind] += finish - start
        busy += max(0, finish - max(start, right))
        right = max(right, finish)
    if len(epochs) != 1 or calls != expected:
        raise ValueError(f"L1 task/core counts differ from the SWA graph in {directory}")
    ticks_per_us = meta["clock_freq_hz"] / 1e6
    span = right - min(row[3] for row in intervals)
    return len(intervals), {
        "first_to_last_us": span / ticks_per_us,
        "critical_chain_kernel_us": chain_time(graph, intervals, previous) / ticks_per_us,
        "any_kernel_active_us": busy / ticks_per_us,
        "no_kernel_active_us": (span - busy) / ticks_per_us,
        "aic_core_us": work["aic"] / ticks_per_us,
        "aiv_core_us": work["aiv"] / ticks_per_us,
    }


def summarize_l1(rank):
    result = json.loads((rank / "result.json").read_bytes())
    if result["runtime"] != "percounter" or not (result["passed"] and result["validated_against_fused_prefix"]):
        raise ValueError("Expected a numerically validated percounter replay")
    warmup, rounds = result["warmup"], result["rounds"]
    if warmup < 1 or rounds < 1:
        raise ValueError("Missing warmup or measured rounds")
    samples = []
    counts = set()
    for iteration in range(warmup, warmup + rounds):
        count, sample = round_times(rank / f"run{iteration}")
        samples.append(sample)
        counts.add(count)
    if len(counts) != 1:
        raise ValueError("Kernel count changed between rounds")
    return {
        "device": result["device"],
        "warmup": warmup,
        "rounds": rounds,
        "calls_per_round": counts.pop(),
        "mean": {k: round(statistics.mean(s[k] for s in samples), 3) for k in samples[0]},
        "samples": samples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rank", type=Path, help="L1 rank0 directory containing result.json and run*")
    print(json.dumps(summarize_l1(parser.parse_args().rank), indent=2))
