# Copyright (c) PyPTO Contributors.
# Licensed under CANN Open Software License Agreement Version 2.0 (the "License").
# See LICENSE in the root of the software repository for the full text of the License.
"""Export Perfetto views of the integrated percounter SWA run1 captures."""

import argparse
import gzip
import json
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path


CASE = Path(__file__).resolve().parents[1]
ROOT = CASE.parents[2]
# Git tree of simpler_setup/tools used by the integration branch. Its decoder
# reads the seven-column worker records saved by these two trials.
TOOLS_TREE = "2bdfa139328b58f6650ac63e693fac4334e612df"


def order_l1_tracks(events, core_types, workers):
    # Upstream #3302 numbers the full core list before selecting active lanes.
    lanes = {}
    for kind in ("aic", "aiv"):
        for ordinal, worker in enumerate(i for i, t in enumerate(core_types) if t == kind):
            lanes[worker] = (f"{kind.upper()}{ordinal}", len(lanes))
    order = []
    for event in events:
        if event.get("pid") == 4 and event.get("name") == "thread_name":
            tid = event["tid"]
            label, index = lanes[workers[tid]]
            event["args"]["name"] = label
            order.append({**event, "name": "thread_sort_index", "args": {"sort_index": index}})
    events.extend(order)


def export(run, level, platform, tools, names):
    record = run / "chip_swimlane_records.json"
    raw = json.loads(record.read_bytes())
    meta = raw["metadata"]
    rows = raw["aicore_tasks"]
    c, v, calls = {"a5": (32, 64, 578), "a6": (54, 54, 560)}[platform]
    if (
        run.name != "run1"
        or meta["runtime"] != "percounter"
        or raw["chip_swimlane_level"] != level
        or Counter(meta["core_types"]) != {"aic": c, "aiv": v}
        or len(rows) != calls
    ):
        raise ValueError(f"Expected {platform} percounter L{level} run1 with {calls} kernel calls in {run}")

    trace = tools / f"{platform}-L{level}-run1.json"
    command = [sys.executable, "-X", "utf8", "-E", "-S", "-m", "simpler_setup.tools.swimlane_converter"]
    subprocess.run(
        [*command, str(record), "--func-names", str(names), "--deps-json", str(run / "deps.json"), "-o", str(trace)],
        cwd=tools,
        check=True,
    )
    data = json.loads(trace.read_bytes())
    events = data["traceEvents"]
    worker_bars = [e for e in events if e.get("pid") == 4 and e["ph"] == "X"]
    # Compare every kernel duration in device ticks, including repeated calls to
    # the same task. Worker bars at L1 can also include local setup time.
    ticks_per_us = meta["clock_freq_hz"] / 1e6
    measured = Counter((r[0], r[1], r[4] - r[3]) for r in rows)
    drawn = Counter()
    pairs = (line.split() for line in (run / "source-task-map.txt").read_text().splitlines())
    source_ids = {int(replay): int(source) for source, replay in pairs}
    workers = {}
    for bar in worker_bars:
        args = bar["args"]
        worker = int(args["event-hint"].rsplit("CoreId:", 1)[1])
        workers[bar["tid"]] = worker
        task = args["taskId"]
        drawn[worker, task, round(args["kernel-duration-us"] * ticks_per_us)] += 1
        args["source_task_id"] = source_ids[task]
    if drawn != measured or (level == 2 and not any(e.get("cat") == "Percounter L2" for e in events)):
        raise ValueError(f"Trace and device records disagree in {run}")
    if level == 1:
        order_l1_tracks(events, meta["core_types"], workers)

    path = trace.with_suffix(".json.gz")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    path.write_bytes(gzip.compress(encoded, compresslevel=9, mtime=0))
    return path, len(worker_bars)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("a5", "a6"))
    parser.add_argument("l1_run1", type=Path)
    parser.add_argument("l2_run1", type=Path)
    parser.add_argument("--output", type=Path, default=CASE / "doc/swimlanes")
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination) as temp:
        tools = Path(temp)
        # Isolate the offline viewer from any Simpler/CANN installation.
        archive = tools / "tools.zip"
        subprocess.run(
            ["git", "archive", "--format=zip", "--prefix=simpler_setup/tools/", "-o", str(archive), TOOLS_TREE],
            cwd=ROOT,
            check=True,
        )
        with zipfile.ZipFile(archive) as package:
            package.extractall(tools)
        kernels = json.loads((CASE / "kernels/manifest.json").read_bytes())["kernels"]
        names = tools / "names.json"
        mapping = {k["func_id"]: k["name"] for k in kernels}
        names.write_text(json.dumps({"callable_id_to_name": mapping, "orchestrator_name": "SWA"}))
        runs = (args.l1_run1, args.l2_run1)
        outputs = [
            export(run.resolve(), level, args.platform, tools, names) for level, run in enumerate(runs, start=1)
        ]
        for trace, count in outputs:
            path = trace.replace(destination / trace.name)
            print(f"{path}  ({count} verified kernel intervals)", flush=True)


if __name__ == "__main__":
    main()
