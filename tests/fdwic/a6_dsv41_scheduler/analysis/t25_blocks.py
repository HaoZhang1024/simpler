#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Group the 54 t25 L4 intervals by observed logical block identity."""

import argparse
import gzip
import json
import struct
from pathlib import Path
from statistics import median


def mark_block(source):
    anchor = "    wait_flag(PIPE_MTE3, PIPE_MTE2, EVENT_ID0);\n    pipe_barrier(PIPE_ALL);"
    if source.count(anchor) != 1:
        raise ValueError("Expected the final run_native barrier")
    return source.replace(anchor, anchor + """
    const int block = get_block_idx(args);
    auto *row = reinterpret_cast<__gm__ uint64_t *>(args[8]) + 8 * block;
    uint64_t tick;
    asm volatile("MOV %0, SYS_CNT" : "=l"(tick) : : "memory");
    row[0] = tick;
    row[1] = get_coreid();
    row[2] = block;
    row[3] = get_block_num(args);
    dcci(row, SINGLE_CACHE_LINE, CACHELINE_OUT);
    dsb(DSB_DDR);""")


def stamped_ids(data, streams, rows):
    if len(data) != 4096 or any(data[54 * 64:]):
        raise ValueError("Expected a zero-cleared 64-line buffer with 54 populated slots")
    worker_ids = {row[0] for row in rows}
    physical = {s["physical_core_id"]: s["worker_id"] for s in streams
                if s["producer"] == "aicore" and s["core_type"] == "aiv" and s["worker_id"] in worker_ids}
    if len(physical) != 54 or set(physical.values()) != worker_ids:
        raise ValueError("Incomplete AIV physical-to-worker mapping")
    by_worker = {row[0]: row for row in rows}
    ids = {}
    for block, (tick, core, index, count) in enumerate(struct.iter_unpack("<4Q32x", data[:54 * 64])):
        # A6 platform get_physical_core_id() masks COREID with AICORE_COREID_MASK.
        worker = physical.get(core & 0x0fff)
        if (index, count) != (block, 54) or worker not in by_worker or worker in ids:
            raise ValueError(f"Invalid block stamp or repeated AIV at block {block}")
        row = by_worker[worker]
        if not row[3] <= tick <= row[4]:
            raise ValueError(f"Block {block} timestamp is outside the matched L4 call")
        ids[worker] = block
    return ids


def analyze(run):
    path = run / "chip_swimlane_records.json"
    records = json.loads(path.read_bytes() if path.exists() else gzip.decompress(path.with_suffix(".json.gz").read_bytes()))
    mapping = dict(map(int, line.split()) for line in (run / "source-task-map.txt").read_text().splitlines() if line.strip())
    task = mapping[25]
    rows = [r for r in records["aicore_tasks"] if r[1] == task]
    hz = records["metadata"]["clock_freq_hz"]
    kinds = records["metadata"]["core_types"]
    if (records["chip_swimlane_level"] != 4 or hz <= 0 or len(records["aicore_tasks"]) != 560 or len(rows) != 54
            or len({r[0] for r in rows}) != 54 or len({r[6] for r in rows}) != 1
            or any(len(r) != 7 or kinds[r[0]] != "aiv" or not 0 < r[3] < r[4] for r in rows)):
        raise ValueError("Expected the complete A6 54-block L4 run with one t25 call per AIV")
    ids = {}
    stamps = run / "t25-stamps.bin"
    if stamps.exists():
        ids = stamped_ids(stamps.read_bytes(), records["scheduler_records"]["streams"], rows)
    elif "aicore_execution_identities" in records:
        # Match same-round device identities only if this archive contains them.
        keys = {(r[6], r[0], r[2]) for r in rows}
        for e in records["aicore_execution_identities"]["records"]:
            if (e["run_epoch"], e["core_id"], e["reg_task_id"]) in keys:
                worker = e["core_id"]
                if worker in ids or e["task_id"] != task or e["executed"] is not True or e["block_num"] != 54:
                    raise ValueError("Execution identity disagrees with t25 L4")
                ids[worker] = e["block_idx"]
        if set(ids.values()) != set(range(54)):
            raise ValueError("Incomplete t25 execution identities")

    def us(ticks):
        return round(ticks * 1e6 / hz, 3)

    first = min(r[3] for r in rows)
    last = max(r[4] for r in rows)
    details = []
    tails = []
    groups = {"single": [], "double": []}
    for worker, _, _, start, end, _, _ in rows:
        block = ids.get(worker)
        heads = [] if block is None else list(range(block, 64, 54))
        row = dict(worker=worker, block_idx=block, heads=heads, start_us=us(start-first),
                   end_us=us(end-first), duration_us=us(end-start))
        details.append(row)
        if end == last:
            tails.append(row)
        if heads:
            groups["single" if len(heads) == 1 else "double"].append(end-start)
    summary = dict(span_us=us(last-first), tails=tails, identity="observed" if ids else "missing")
    for name, ticks in groups.items():
        if ticks:
            summary[name] = dict(n=len(ticks), min_us=us(min(ticks)), median_us=us(median(ticks)),
                                 max_us=us(max(ticks)))
    return summary, sorted(details, key=lambda r: r["block_idx"] if ids else r["worker"])


def report(rank, *, require_identity=False):
    golden = json.loads((rank / "result.json").read_bytes())
    if not (golden["passed"] and golden["validated_against_fused_prefix"] and golden["runtime"] == "percounter"
            and golden["warmup"] == 1 and golden["rounds"] == 3):
        raise ValueError("Expected three formal rounds with SWA golden")
    details = {}
    lines = []
    for i in (1, 2, 3):
        summary, details[i] = analyze(rank / f"run{i}")
        if require_identity and summary["identity"] != "observed":
            raise ValueError(f"run{i}: missing block identity in the diagnostic capture")
        lines.append(f"run{i} " + json.dumps(summary))
    (rank / "t25-blocks.json").write_text(json.dumps(details, indent=2) + "\n")
    feedback = "\n".join(lines) + "\n"
    (rank / "t25-blocks-feedback.txt").write_text(feedback)
    print(feedback + f"Feedback: {rank / 't25-blocks-feedback.txt'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rank", type=Path, help="Existing B1/rank0 from the paired t25 L4 capture")
    report(parser.parse_args().rank)
