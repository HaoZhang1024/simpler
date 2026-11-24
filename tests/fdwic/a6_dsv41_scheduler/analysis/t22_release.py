#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""Split the observed t22 wait at the group's last entry_commit timestamp."""

from statistics import mean


def release_round(rows, events, chain):
    mix = {(r.block_idx, r.worker): r for r in rows if r.source_task == 22}
    (tid,) = {r.task_id for r in mix.values()}
    (hz,) = {r.clock_hz for r in mix.values()}
    us = 1e6 / hz
    marks = {}
    inputs = {}
    for event in events:
        if int(event["task_id"]) != tid:
            continue
        kind, block = event["kind"], event["block_index"]
        if kind == "inputs_ready":
            if block in inputs:
                raise ValueError(f"Duplicate t22 inputs_ready for block {block}")
            inputs[block] = event["cycles"]
        if kind in ("entry_commit", "ready"):
            key = (block, event["worker_id"], kind)
            if key[:2] not in mix or key in marks:
                raise ValueError(f"Unexpected or duplicate t22 checkpoint {key}")
            marks[key] = event["cycles"]
    if len(marks) != 2 * len(mix) or set(inputs) != {b for b, _ in mix}:
        raise ValueError("Incomplete t22 block and lane checkpoints")
    last = max(stamp for (_, _, kind), stamp in marks.items() if kind == "entry_commit")
    (step,) = [s for s in chain if s["task"] == 22]
    critical = (step["block"], step["worker"])
    lane_table = []
    for (block, worker), row in sorted(mix.items()):
        commit = marks[block, worker, "entry_commit"]
        ready = marks[block, worker, "ready"]
        if not 0 < commit <= ready <= row.dispatch_cycles:
            raise ValueError(f"Invalid t22 checkpoint order for block {block}, worker {worker}")
        prev = max(
            (r for r in rows if r.worker == worker and r.kernel_end_cycles <= row.start_cycles),
            key=lambda r: r.kernel_end_cycles,
            default=None,
        )
        lane_table.append(
            {
                "round": row.iteration,
                "block": block,
                "lane": row.subtask_slot,
                "worker": worker,
                "is_last_commit": commit == last,
                "is_critical": (block, worker) == critical,
                "previous_task": prev.source_task if prev else None,
                "previous_block": prev.block_idx if prev else None,
                "prev_end_to_commit_us": (commit - prev.kernel_end_cycles) * us if prev else None,
                "inputs_ready_to_commit_us": (commit - inputs[block]) * us,
                "commit_relative_to_last_us": (commit - last) * us,
                "last_commit_to_ready_us": (ready - last) * us,
            }
        )
    ready = marks[critical[0], critical[1], "ready"]
    # Match the prior report's clipping to the last visible blocker and dispatch.
    lo = max(marks[critical[0], critical[1], "entry_commit"], step["prior_kernel_end_cycles"])
    hi = max(lo, min(ready, step["dispatch_cycles"]))
    cut = min(hi, max(lo, last))
    tails = [r for r in lane_table if r["is_last_commit"]]
    return {
        "round": rows[0].iteration,
        "last_commit_lanes": [
            [
                r[k]
                for k in (
                    "block",
                    "lane",
                    "worker",
                    "previous_task",
                    "previous_block",
                    "prev_end_to_commit_us",
                    "inputs_ready_to_commit_us",
                )
            ]
            for r in tails
        ],
        "critical_block_worker": list(critical),
        "before_last_commit_us": (cut - lo) * us,
        "after_last_commit_us": (hi - cut) * us,
        "first_ready_minus_last_commit_us": min(r["last_commit_to_ready_us"] for r in lane_table),
        "last_ready_minus_last_commit_us": max(r["last_commit_to_ready_us"] for r in lane_table),
    }, lane_table


def release_summary(rounds):
    fields = (
        "before_last_commit_us",
        "after_last_commit_us",
        "first_ready_minus_last_commit_us",
        "last_ready_minus_last_commit_us",
    )
    return {
        "mean_us": {k: round(mean(r[k] for r in rounds), 3) for k in fields},
        "last_lane_columns": [
            "block",
            "lane",
            "worker",
            "previous_task",
            "previous_block",
            "prev_end_to_commit_us",
            "inputs_ready_to_commit_us",
        ],
        "rounds": rounds,
    }
