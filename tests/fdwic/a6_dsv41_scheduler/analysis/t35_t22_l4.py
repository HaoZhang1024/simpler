#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Extract worker reuse and MIX launch evidence from the saved A64 rounds."""

import argparse
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from t25_report import summarize

PHASES = ("claim", "resolve", "prepare_subtask", "publish_completion", "async_seal")


def covered(intervals):
    total = 0
    previous = 0
    for a, b in sorted(intervals):
        total += max(0, b - max(a, previous))
        previous = max(previous, b)
    return total


def describe(records, mapping):
    summary = summarize(records, mapping, 64)
    epoch = summary["epoch"]
    rows = records["aicore_tasks"]
    hz = summary["clock_hz"]

    def us(ticks):
        return round(ticks * 1e6 / hz, 3)

    def stats(values):
        if not values:
            return None
        ordered = sorted(values)
        return [us(ordered[0]), us(median(ordered)), us(ordered[math.ceil(.9 * len(ordered)) - 1]), us(ordered[-1])]

    by_worker = defaultdict(list)
    for r in rows:
        if mapping[r[1]] == 35:
            by_worker[r[0]].append(r)
    if sorted(map(len, by_worker.values())) != [1] * 44 + [2] * 10:
        raise ValueError("Expected 54 t35 workers including 10 reused workers")
    streams = {s["worker_id"]: s for s in records.get("scheduler_records", {}).get("streams", [])
               if s["producer"] == "aicore"}
    details = {}
    for worker, group in by_worker.items():
        if len(group) == 1:
            continue
        a, b = sorted(group, key=lambda row: row[3])
        start, end = a[4], b[3]
        if end < start:
            raise ValueError("Overlapping kernels on one worker")
        stream = streams.get(worker, {})
        cap = stream.get("capture", {})
        phases = defaultdict(list)
        for event in stream.get("records", []):
            clipped = max(start, event["start_cycles"]), min(end, event["end_cycles"])
            if event["run_epoch"] == epoch and clipped[0] < clipped[1]:
                phases[event["kind"]].append(clipped)
        others = [mapping[r[1]] for r in rows if r[0] == worker and mapping[r[1]] != 35 and r[3] < end and r[4] > start]
        details[worker] = dict(gap_us=us(end-start), other_tasks=others, capture=cap, phases_us={
            p: us(covered(phases["scalar_percounter_" + p])) for p in PHASES if "scalar_percounter_" + p in phases})
    complete = [d for d in details.values() if d["capture"].get("dropped") == 0 and d["capture"].get("truncated") is False]
    rollup = {}
    for p in PHASES:
        observed = [d["phases_us"][p] for d in complete if p in d["phases_us"]]
        rollup[p] = [len(observed), round(median(observed), 3) if observed else None]
    reuse = dict(full_streams=len(complete), with_other_kernel=sum(bool(d["other_tasks"]) for d in details.values()),
                 tail_worker=summary["tasks"][35]["last_worker"], phase_n_median=rollup)

    anchor = max(r[4] for r in rows if mapping[r[1]] == 18)
    dispatch = {(core, seq): start for core, seq, start, _, ep in records["scheduler_tasks"]["records"] if ep == epoch}
    mix = {}
    for kind in ("aic", "aiv"):
        group = [r for r in rows if mapping[r[1]] == 22 and records["metadata"]["core_types"][r[0]] == kind]
        if len(group) != 48:
            raise ValueError(f"Expected 48 t22 {kind} lanes")
        offsets, delays = [], []
        for core, _, seq, begin, *_ in group:
            tick = dispatch.get((core, seq))
            if tick is not None:
                if tick > begin:
                    raise ValueError("Dispatch after kernel start")
                offsets.append(tick - anchor)
                delays.append(begin - tick)
        mix[kind] = dict(dispatch_n=len(offsets), dispatch_from_t18=stats(offsets), dispatch_to_own_start=stats(delays))
    t21 = [r[4] for r in rows if mapping[r[1]] == 21]
    mix["t21_last_kernel_from_t18"] = us(max(t21)-anchor) if t21 else None
    return reuse, mix, details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path, help="Original paired t25-l4 directory containing A1/rank0")
    args = parser.parse_args()
    root = args.capture_dir.resolve()
    rank = root / "A1/rank0"
    result = json.loads((rank / "result.json").read_bytes())
    if not (result["passed"] and result["validated_against_fused_prefix"] and result["runtime"] == "percounter"
            and result["warmup"] == 1 and result["rounds"] == 3):
        raise ValueError("Expected a validated A1 capture with three formal rounds")
    lines = []
    details = {}
    for i in (1, 2, 3):
        run = rank / f"run{i}"
        path = run / "chip_swimlane_records.json"
        data = path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(".json.gz").read_bytes())
        mapping = {int(replay): int(source) for source, replay in
                   (line.split() for line in (run / "source-task-map.txt").read_text().splitlines() if line.strip())}
        reuse, mix, details[i] = describe(json.loads(data), mapping)
        lines.extend(f"run{i} {name} {json.dumps(value)}" for name, value in (("t35", reuse), ("t22", mix)))
    (root / "t35-workers.json").write_text(json.dumps(details, indent=2) + "\n")
    feedback = "\n".join(lines) + "\n"
    (root / "t35-t22-feedback.txt").write_text(feedback)
    print(feedback + f"Feedback: {root}/t35-t22-feedback.txt")


if __name__ == "__main__":
    main()
