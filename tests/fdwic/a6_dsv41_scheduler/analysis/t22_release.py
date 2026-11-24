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


def entry_roles_round(rows, events, chain, *, split_observation=False):
    """Use one critical block and one clipping window for every role in that round."""
    mix = [r for r in rows if r.source_task == 22]
    (tid,) = {r.task_id for r in mix}
    (hz,) = {r.clock_hz for r in mix}
    (step,) = [s for s in chain if s["task"] == 22]
    (critical,) = [r for r in mix if (r.block_idx, r.worker) == (step["block"], step["worker"])]
    role_names = ("C", "V0", "V1")
    marks = {}
    for e in events:
        if int(e["task_id"]) != tid or e["kind"] not in ("inputs_ready", "claim", "entry_commit"):
            continue
        key = (e["block_index"], e["kind"], e["cluster_lane"])
        if key in marks:
            raise ValueError(f"Duplicate t22 role checkpoint {key}")
        marks[key] = e

    units = {(r.block_idx, r.subtask_slot): r for r in mix}
    blocks = {r.block_idx for r in mix}
    roles = {r.subtask_slot for r in mix}
    if roles not in ({0, 1}, {0, 1, 2}) or len(units) != len(mix) or len(mix) != len(blocks) * len(roles):
        raise ValueError("Incomplete t22 MIX role set")
    if len(marks) != len(mix) + 2 * len(blocks):
        raise ValueError("Incomplete t22 role checkpoints")

    all_blocks = {role_names[k]: [] for k in roles}
    critical_block = {}
    critical_block_raw = {}
    raw_before, raw_after = [], []
    split = {}
    us = 1e6 / hz
    for block in blocks:
        inputs = marks[block, "inputs_ready", 0]
        ready = inputs["cycles"]
        if (
            inputs["worker_id"] != units[block, 0].worker
            or marks[block, "claim", 1]["worker_id"] != units[block, 1].worker
        ):
            raise ValueError(f"Unexpected t22 publisher or claimer at block {block}")
        for role in roles:
            row = units[block, role]
            entry = marks[block, "entry_commit", role]
            worker, commit = entry["worker_id"], entry["cycles"]
            if worker != row.worker or not 0 < ready <= commit <= row.dispatch_cycles:
                raise ValueError(f"Invalid t22 entry for block {block}, role {role}")
            name = role_names[role]
            all_blocks[name].append((commit - ready) * us)
            if split_observation and role == 1:
                stamp = entry.get("fanin_observed_cycles", 0)
                if not ready <= stamp <= commit:
                    raise ValueError(
                        f"Missing or unordered t22 V0 observation at round {critical.iteration}, block {block}"
                    )
                raw_before.append((stamp - ready) * us)
                raw_after.append((commit - stamp) * us)
            if block != critical.block_idx:
                continue
            critical_block_raw[name] = (commit - ready) * us
            start = max(ready, step["prior_kernel_end_cycles"])
            end = min(commit, step["dispatch_cycles"])
            critical_block[name] = max(0, end - start) * us
            if role == 1:
                if split_observation:
                    cut = max(start, min(end, stamp))
                    split["critical_before_us"] = (cut - start) * us
                    split["critical_after_us"] = max(0, end - cut) * us
                # Use the raw window. The chain clips out time before the preceding kernel ends.
                v0_busy = (
                    sum(
                        max(0, min(commit, r.kernel_end_cycles) - max(ready, r.start_cycles))
                        for r in rows
                        if r.worker == worker
                    )
                    * us
                )
    if split_observation:
        split["all_before_us"] = mean(raw_before)
        split["all_after_us"] = mean(raw_after)
    return {
        **split,
        "round": critical.iteration,
        "critical_role": role_names[critical.subtask_slot],
        "critical_block_raw_us": critical_block_raw,
        "critical_block_us": critical_block,
        "all_blocks_raw_us": {k: mean(v) for k, v in all_blocks.items()},
        "critical_block_v0_raw_kernel_overlap_us": v0_busy,
        "blocks": len(blocks),
    }


def entry_roles_summary(rounds):
    def role_means(field):
        return {k: round(mean(r[field][k] for r in rounds), 3) for k in rounds[0][field]}

    result = {
        "rounds": len(rounds),
        "blocks_checked": sum(r["blocks"] for r in rounds),
        "critical_roles": [r["critical_role"] for r in rounds],
        "critical_lane_us": round(mean(r["critical_block_us"][r["critical_role"]] for r in rounds), 3),
        "critical_block_us": role_means("critical_block_us"),
        "all_blocks_raw_us": role_means("all_blocks_raw_us"),
        "critical_block_raw_us": role_means("critical_block_raw_us"),
        "critical_block_v0_raw_kernel_overlap_us": round(
            mean(r["critical_block_v0_raw_kernel_overlap_us"] for r in rounds), 3
        ),
    }
    if "all_before_us" in rounds[0]:
        fields = ("critical_before_us", "critical_after_us", "all_before_us", "all_after_us")
        result["v0_observation"] = {k: round(mean(r[k] for r in rounds), 3) for k in fields}
        result["v0_by_round"] = [{k: round(r[k], 3) for k in ("round", *fields)} for r in rounds]
    return result
