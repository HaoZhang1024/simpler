#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Analyze a completed SWA run on CPU. Durations are scaled before quantization."""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from swa_sync_bound import (
    CAPACITIES,
    QUANTUM_NS,
    analyze_placement,
    checked_run,
    read_json,
    read_plan,
    read_round,
    solve_model,
)
from t22_release import entry_roles_round, entry_roles_summary, release_round, release_summary


def sensitivity(nodes, edges, rows, capacities, baseline, seconds):
    gains = {}
    for source in sorted({r.source_task for r in rows}):
        variant = {tid: {"sync": n["sync"], "units": []} for tid, n in nodes.items()}
        for r in rows:
            ticks = r.duration_ticks
            if r.source_task == source:
                ticks = (r.kernel_end_cycles - r.start_cycles) * 9 * 10**9 // (10 * r.clock_hz * QUANTUM_NS)
            variant[r.task_id]["units"].append((r.block_idx, r.subtask_slot, r.core_type, ticks))
        solved = solve_model(variant, edges, capacities, seconds)
        # Original feasible placement remains feasible when durations decrease.
        lower = solved["lower_ticks"] * QUANTUM_NS / 1000
        upper = baseline
        if solved["feasible_ticks"] is not None:
            upper = min(baseline, solved["feasible_ticks"] * QUANTUM_NS / 1000)
        if lower > upper + 1e-7:
            raise ValueError(f"Inconsistent sensitivity solve at task {source}")
        gains[source] = (baseline - upper, baseline - lower)
    return gains


def task_windows(rows, raw, chain, blocks25):
    hz = rows[0].clock_hz
    us = 1e6 / hz
    quant = [r for r in rows if r.source_task == 25]
    if sorted(r.block_idx for r in quant) != list(range(blocks25)):
        raise ValueError("Incomplete t25 block set")
    groups = defaultdict(list)
    for r in quant:
        heads = len(range(r.block_idx, 64, blocks25))
        groups[heads].append((r.kernel_end_cycles - r.start_cycles) * us)
    end = max(r.kernel_end_cycles for r in quant)
    tails = sorted(r.block_idx for r in quant if r.kernel_end_cycles == end)
    t25 = {"p50_us": {n: median(values) for n, values in groups.items()}, "last_blocks": tails}

    mix = [r for r in rows if r.source_task == 22]
    blocks = {r.block_idx for r in mix}
    claims = [
        e
        for e in raw["percounter_task_events"]["records"]
        if int(e["task_id"]) == mix[0].task_id and e["kind"] == "claim"
    ]
    by_block = {e["block_index"]: e for e in claims}
    if len(claims) != len(blocks) or set(by_block) != blocks:
        raise ValueError("Expected one MIX owner claim per t22 block")
    if any(not 0 < e["claim_start_cycles"] <= e["cycles"] for e in claims):
        raise ValueError("Invalid t22 claim interval")
    checkpoints = defaultdict(list)
    for e in raw["percounter_task_events"]["records"]:
        if int(e["task_id"]) == mix[0].task_id and e["kind"] in ("inputs_ready", "entry_commit", "ready"):
            lane = None if e["kind"] == "inputs_ready" else e["worker_id"]
            checkpoints[e["kind"], e["block_index"], lane].append(e["cycles"])
    last_claim = max(e["cycles"] for e in claims)
    pieces = Counter()
    hits = 0
    detailed = 0
    for step in chain:
        if step["task"] != 22 or step["prior_kernel_end_cycles"] is None:
            continue
        hits += 1
        start = step["prior_kernel_end_cycles"]
        stop = max(start, step["dispatch_cycles"])
        claim = by_block[step["block"]]
        # Clip the block owner's claim to the visible gap; claim can precede the predecessor's return.
        claim_start = min(stop, max(start, claim["claim_start_cycles"]))
        claim_end = min(stop, max(start, claim["cycles"]))
        pieces["before_owner_claim_us"] += (claim_start - start) * us
        pieces["in_owner_claim_us"] += (claim_end - claim_start) * us
        pieces["after_owner_claim_us"] += (stop - claim_end) * us
        block, worker = step["block"], step["worker"]
        stamps = [
            checkpoints["inputs_ready", block, None],
            checkpoints["entry_commit", block, worker],
            checkpoints["ready", block, worker],
        ]
        if all(len(times) == 1 for times in stamps):
            bounds = [claim_end, *(min(stop, max(start, times[0])) for times in stamps), stop]
            if bounds == sorted(bounds):
                detailed += 1
                for name, left, right in zip(
                    ("to_inputs_ready_us", "to_entry_commit_us", "to_ready_us", "ready_to_dispatch_us"),
                    bounds[:-1],
                    bounds[1:],
                ):
                    pieces[name] += (right - left) * us
        if abs((stop - start) * us - step["gap_before_dispatch_us"]) > 1e-6:
            raise ValueError("t22 phase split disagrees with the recorded critical chain")
    t22 = {
        "claim_end_spread_us": (last_claim - min(e["cycles"] for e in claims)) * us,
        "first_dispatch_minus_last_claim_us": (min(r.dispatch_cycles for r in mix) - last_claim) * us,
        "chain_hits": hits,
        "detailed_hits": detailed,
        **pieces,
    }
    return t25, t22


def summarize(rounds):
    tasks = sorted(rounds[0]["gains"])
    summary = {}
    for task in tasks:
        intervals = [r["gains"][task] for r in rounds]
        summary[task] = [round(mean(column), 3) for column in zip(*intervals)]
    return {
        "gain_us_if_task_10pct_shorter": dict(sorted(summary.items(), key=lambda kv: -kv[1][0])),
        "t25_mean_of_round_p50_us": {
            n: round(mean(r["t25"]["p50_us"][n] for r in rounds), 3) for n in rounds[0]["t25"]["p50_us"]
        },
        "t25_last_blocks_by_round": [r["t25"]["last_blocks"] for r in rounds],
        "t22_mean_us": {
            k: round(mean(r["t22"].get(k, 0) for r in rounds), 3)
            for k in (
                "before_owner_claim_us",
                "in_owner_claim_us",
                "after_owner_claim_us",
                "claim_end_spread_us",
                "first_dispatch_minus_last_claim_us",
            )
        },
        "t22_chain_hits_by_round": [r["t22"]["chain_hits"] for r in rounds],
        "t22_detailed_hits_by_round": [r["t22"]["detailed_hits"] for r in rounds],
        "t22_after_claim_breakdown_us": {
            k: round(mean(r["t22"].get(k, 0) for r in rounds), 3)
            for k in ("to_inputs_ready_us", "to_entry_commit_us", "to_ready_us", "ready_to_dispatch_us")
        }
        if all(r["t22"]["detailed_hits"] == r["t22"]["chain_hits"] for r in rounds)
        else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Integrated trial directory or its completed SWA run")
    parser.add_argument("--seconds", type=float, default=30, help="Time limit per variant solve")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--t22-entry-roles", action="store_true", help="Compare C and V entry on the same t22 blocks")
    mode.add_argument("--t22-observation", action="store_true", help="Split V0 entry at its first observed fanin flag")
    parser.add_argument(
        "--capture-l2", type=Path, help="Use another role/observation capture of the same case and device"
    )
    mode.add_argument(
        "--t22-release",
        type=Path,
        metavar="LANES.csv",
        help="Analyze t22 timestamps only and save per-lane details to this CSV",
    )
    args = parser.parse_args()
    if args.capture_l2 and not (args.t22_entry_roles or args.t22_observation):
        parser.error("--capture-l2 requires --t22-entry-roles or --t22-observation")
    run = args.run
    if (run / "src/build").is_dir():
        (model,) = (run / "src/build").glob("swa-a6-*/model/summary.json")
        run = model.parents[1]
    prior = read_json(run / "model/summary.json")
    build, tasks = read_plan(run / "t25-54")
    capture, _ = checked_run(run / "L2", build, 2)
    if (
        capture["runtime_sha256"] != prior["runtime_sha256"]
        or capture["device"] != prior["device"]
        or prior["build"] != build
        or not prior["all_optimal"]
        or [r["round"] for r in prior["rounds"]] != list(range(1, 11))
    ):
        raise ValueError("Expected the ten matching solved baseline rounds")
    rounds = []
    lanes = []
    l2 = args.capture_l2 or run / "L2"
    if args.capture_l2:
        other, _ = checked_run(l2, build, 2)
        if other["device"] != capture["device"] or other["build"] != build:
            raise ValueError("Observation run must use the baseline device and frozen case")
        if args.t22_entry_roles and other["runtime_sha256"] != capture["runtime_sha256"]:
            raise ValueError("Control runtime differs from the saved baseline")
        capture = other
    for ref in prior["rounds"]:
        print(f"Analyzing round {ref['round']}/10", file=sys.stderr, flush=True)
        folder = l2 / "percounter/rank0" / f"run{ref['round']}"
        nodes, edges, rows, _ = read_round(folder, tasks, ref["round"])
        placement = analyze_placement(nodes, edges, rows)
        if not args.capture_l2 and (
            placement["chain"] != ref["chain"] or placement["fixed_order_us"] != ref["fixed_order_us"]
        ):
            raise ValueError("Capture differs from saved model")
        raw = read_json(folder / "chip_swimlane_records.json")
        if args.t22_entry_roles or args.t22_observation:
            rounds.append(
                entry_roles_round(
                    rows,
                    raw["percounter_task_events"]["records"],
                    placement["chain"],
                    split_observation=bool(args.t22_observation),
                )
            )
            continue
        if args.t22_release:
            detail, records = release_round(rows, raw["percounter_task_events"]["records"], placement["chain"])
            rounds.append(detail)
            lanes.extend(records)
            continue
        t25, t22 = task_windows(rows, raw, placement["chain"], 54)
        gains = sensitivity(nodes, edges, rows, CAPACITIES, ref["lower_bound_us"], args.seconds)
        kernel_time = Counter()
        for step in placement["chain"]:
            kernel_time[step["task"]] += step["kernel_us"]
        rounds.append({"t25": t25, "t22": t22, "gains": gains, "chain_kernel": kernel_time})
    if args.capture_l2 or args.t22_observation:
        print(
            json.dumps(
                {
                    "case_source_commit": build["source_commit"],
                    "runtime_sha256": capture["runtime_sha256"],
                    **entry_roles_summary(rounds),
                }
            )
        )
        return
    if args.t22_entry_roles:
        print(json.dumps({"source_commit": build["source_commit"], **entry_roles_summary(rounds)}))
        return
    if args.t22_release:
        with args.t22_release.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=lanes[0].keys())
            writer.writeheader()
            writer.writerows(lanes)
        print(
            json.dumps(
                {"source_commit": build["source_commit"], "lane_rows": len(lanes), **release_summary(rounds)},
                ensure_ascii=False,
            )
        )
        return
    chain_us = {task: round(mean(r["chain_kernel"][task] for r in rounds), 3) for task in sorted(tasks)}
    print(
        json.dumps(
            {
                "source_commit": build["source_commit"],
                "pto_isa_commit": build["pto_isa_commit"],
                "baseline_us": prior["lower_bound_mean_us"],
                "actual_chain_kernel_us": chain_us,
                **summarize(rounds),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
