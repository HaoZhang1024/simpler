#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Summarize a saved pair of A6 SWA L4 captures and export each formal round to Perfetto."""

import argparse
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

REPO = Path(__file__).resolve().parents[4]


def summarize(records, mapping, blocks):
    rows = records["aicore_tasks"]
    hz = records["metadata"]["clock_freq_hz"]
    if (records["chip_swimlane_level"] != 4 or hz <= 0 or len(rows) != 506 + blocks
            or len({r[6] for r in rows}) != 1 or any(r[4] < r[3] for r in rows)):
        raise ValueError("Expected one full A6 SWA L4 epoch")
    epoch = rows[0][6]
    origin = min(r[3] for r in rows)
    kinds = records["metadata"]["core_types"]
    groups = defaultdict(list)
    for row in rows:
        groups[mapping[row[1]]].append(row)
    if len(groups) != 16 or any(len(groups[t]) != n for t, n in ((22, 96), (25, blocks), (28, 64), (35, 64))):
        raise ValueError("Task map or plan differs from the SWA trial")

    def us(cycles):
        return round(cycles * 1e6 / hz, 3)

    tasks = {}
    tails = {}
    streams = records.get("scheduler_records", {}).get("streams", [])
    dispatch = {(core, seq, run_epoch): start for core, seq, start, _, run_epoch
                in records.get("scheduler_tasks", {}).get("records", [])}
    for task, group in sorted(groups.items()):
        by_core = defaultdict(list)
        by_kind = defaultdict(list)
        for row in sorted(group, key=lambda r: r[3]):
            by_core[row[0]].append(row)
            by_kind[kinds[row[0]]].append(row[4] - row[3])
        first = min(r[3] for r in group)
        last = max(group, key=lambda r: r[4])
        starts = [dispatch.get((r[0], r[2], epoch)) for r in group]
        gaps = [b[3] - a[4] for items in by_core.values() for a, b in zip(items, items[1:])]
        tasks[task] = dict(
            intervals=len(group), active_workers=len(by_core), executions_per_worker=dict(Counter(map(len, by_core.values()))),
            first_start_us=us(first - origin), last_end_us=us(last[4] - origin), span_us=us(last[4] - first),
            first_dispatch_us=us(min(starts) - origin) if None not in starts else None,
            start_spread_us=us(max(r[3] for r in group) - first), last_worker=last[0],
            reuse_gap_median_us=us(median(gaps)) if gaps else None,
            kernel_us_by_core_type={k: {"count": len(v), "median": us(median(v)), "max": us(max(v))}
                                    for k, v in by_kind.items()},
        )
        if task not in (25, 35):
            continue
        items = by_core[last[0]]
        window = {"worker": last[0], "gap_us": None, "phases": []}
        tails[task] = window
        if len(items) < 2:
            continue
        begin, end = items[-2][4], last[3]
        window["gap_us"] = us(end - begin)
        window["other_kernels"] = sum(r[0] == last[0] and r[1] != last[1] and begin <= r[3] < end for r in rows)
        for stream in streams:
            if stream["producer"] != "aicore" or stream.get("worker_id") != last[0]:
                continue
            for event in stream["records"]:
                start, stop = max(begin, event["start_cycles"]), min(end, event["end_cycles"])
                if event["run_epoch"] == epoch and start < stop:
                    window["phases"].append({"name": event["kind"], "start_from_previous_end_us": us(start - begin),
                                             "overlap_us": us(stop - start)})
    capture = [{k: s.get(k) for k in ("worker_id", "producer", "capture")} for s in streams]
    anchor = tasks[22]["last_end_us"]
    metrics = {"t25_span": tasks[25]["span_us"], "t22_end_to_t25_end": tasks[25]["last_end_us"] - anchor,
               "t22_end_to_t28_start": tasks[28]["first_start_us"] - anchor,
               "t22_end_to_t35_end": tasks[35]["last_end_us"] - anchor,
               "graph_kernel_span": us(max(r[4] for r in rows) - origin),
               "first_kernel_to_t22_start": tasks[22]["first_start_us"],
               "t18_end_to_t22_start": tasks[22]["first_start_us"] - tasks[18]["last_end_us"],
               "t25_end_to_t35_start": tasks[35]["first_start_us"] - tasks[25]["last_end_us"]}
    return dict(epoch=epoch, clock_hz=hz, intervals=len(rows), tasks=tasks, tail_workers=tails, streams=capture,
                metrics_us={k: round(v, 3) for k, v in metrics.items()})


def export_round(run, blocks, output):
    pairs = [line.split() for line in (run / "source-task-map.txt").read_text().splitlines() if line.strip()]
    mapping = {int(replay): int(source) for source, replay in pairs}
    source = run / "chip_swimlane_records.json"
    # The converter takes plain JSON and discovers same-round deps and name maps beside its input.
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        if not source.exists():
            plain = Path(scratch) / source.name
            with gzip.open(source.with_suffix(".json.gz"), "rb") as src, plain.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            source = plain
        summary = summarize(json.loads(source.read_bytes()), mapping, blocks)
        if not (run / "deps.json").is_file():
            summary["perfetto_error"] = f"Missing same-round dependency graph in {run.name}"
            return summary
        command = [sys.executable, "-m", "simpler_setup.tools.swimlane_converter", source,
                   "-o", output, "--deps-json", run / "deps.json"]
        names = list(run.glob("name_map*.json"))
        if len(names) == 1:
            command.extend(["--func-names", names[0]])
        result = subprocess.run(command, cwd=REPO)
        if result.returncode:
            summary["perfetto_error"] = f"Converter exited with status {result.returncode}"
    return summary


def report_pair(directory):
    results = {}
    device = None
    for label, blocks in (("A1", 64), ("B1", 54)):
        rank = directory / label / "rank0"
        golden = json.loads((rank / "result.json").read_bytes())
        if not (golden["passed"] and golden["validated_against_fused_prefix"] and golden["runtime"] == "percounter"
                and golden["warmup"] == 1 and golden["rounds"] >= 1):
            raise ValueError(f"{label}: expected a passing single-warmup percounter run")
        if device is not None and golden["device"] != device:
            raise ValueError("A/B were recorded on different devices")
        device = golden["device"]
        results[label] = []
        for i in range(1, golden["rounds"] + 1):
            output = directory / f"A6-SWA-t25-{blocks}-run{i}.json.gz"
            results[label].append(export_round(rank / f"run{i}", blocks, output))
    a, b = results.values()
    if len(a) != len(b):
        raise ValueError("Cannot compare different numbers of formal rounds")
    (directory / "task-details.json").write_text(json.dumps(results, indent=2) + "\n")
    lines = [f"device {device}, {len(a)} formal rounds per plan, golden PASS A/B",
             "metric_us: A64 median [min,max] | B54 median [min,max] | median(B) - median(A)"]
    for key in a[0]["metrics_us"]:
        x, y = ([r["metrics_us"][key] for r in side] for side in (a, b))
        lines.append(f"{key}: {median(x):.3f} [{min(x):.3f},{max(x):.3f}] | "
                     f"{median(y):.3f} [{min(y):.3f},{max(y):.3f}] | {median(y)-median(x):+.3f}")
    lines.append("task | A/B medians_us: task span | start spread | AIC kernel median | AIV kernel median")
    for task in sorted(a[0]["tasks"]):
        fields = []
        for side in (a, b):
            stats = [r["tasks"][task] for r in side]
            values = [median(s[key] for s in stats) for key in ("span_us", "start_spread_us")]
            for kind in ("aic", "aiv"):
                durations = [s["kernel_us_by_core_type"][kind]["median"] for s in stats
                             if kind in s["kernel_us_by_core_type"]]
                values.append(median(durations) if durations else None)
            fields.append(["NA" if v is None else f"{v:.3f}" for v in values])
        lines.append(f"t{task} | " + " | ".join(f"{x}/{y}" for x, y in zip(*fields)))
    for label, rounds in results.items():
        for i, r in enumerate(rounds, 1):
            quality = [s["capture"] or {} for s in r["streams"] if s["producer"] == "aicore"]
            loss = sum(s.get("dropped") or 0 for s in quality)
            complete = bool(quality) and all(s.get("dropped") == 0 and s.get("truncated") is False for s in quality)
            lines.append(f"{label}/run{i}: intervals={r['intervals']}, t25 workers={r['tasks'][25]['active_workers']}, "
                         f"t25/t35 last-worker gaps_us={r['tail_workers'][25]['gap_us']}/{r['tail_workers'][35]['gap_us']}, "
                         f"sched streams={len(quality)}, known dropped={loss}, reported loss-free={complete}")
            first_dispatch = r["tasks"][22]["first_dispatch_us"]
            if first_dispatch is not None:
                gap = first_dispatch - r["tasks"][18]["last_end_us"]
                lines.append(f"  t18 kernel end to first t22 dispatch_us={gap:.3f}")
            for task, tail in r["tail_workers"].items():
                if tail["gap_us"] is None:
                    continue
                overlaps = Counter()
                for phase in tail["phases"]:
                    overlaps[phase["name"]] += phase["overlap_us"]
                names = ("claim", "resolve", "prepare_subtask", "publish_completion", "async_seal")
                fields = []
                for name in names:
                    phase = "scalar_percounter_" + name
                    fields.append(f"{name}={overlaps[phase]:.3f}" if phase in overlaps else f"{name}=NA")
                lines.append(f"  t{task} worker={tail['worker']}, other kernels={tail['other_kernels']}, "
                             f"phase overlaps_us: {' '.join(fields)}")
            if "perfetto_error" in r:
                lines.append(f"  Perfetto export failed: {r['perfetto_error']}")
    feedback = "\n".join(lines) + "\n"
    (directory / "feedback.txt").write_text(feedback)
    print(feedback)
    if any("perfetto_error" in r for rounds in results.values() for r in rounds):
        raise RuntimeError("Raw timings were saved. Correct the export error and rerun the offline report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path, help="Paired output containing A1/rank0 and B1/rank0")
    report_pair(parser.parse_args().capture_dir.resolve())
