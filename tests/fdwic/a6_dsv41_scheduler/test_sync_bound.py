# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import importlib
import json
from pathlib import Path

import pytest


def test_round_joins_explicit_block_identity_and_checks_completion(tmp_path, monkeypatch):
    pytest.importorskip("ortools")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent / "analysis"))
    bound = importlib.import_module("swa_sync_bound")

    monkeypatch.setattr(bound, "ROWS_PER_ROUND", 3)
    plan = {
        22: {"blocks": 1, "sync": 1, "kernels": [18, 19, -1]},
        25: {"blocks": 1, "sync": 0, "kernels": [-1, 20, -1]},
    }
    raw = {
        "chip_swimlane_level": 2,
        "metadata": {"runtime": "percounter", "clock_freq_hz": 10**9, "core_types": ["aic"] * 54 + ["aiv"] * 54},
        "aicore_tasks": [
            [54, 17, 2, 1000, 1810, 0, 2],
            [0, 14, 1, 100, 930, 0, 2],
            [54, 14, 1, 100, 540, 0, 2],
        ],
        "scheduler_tasks": {"producer": "aicore"},
    }
    events = []
    for row, end in zip(raw["aicore_tasks"], [1800, 900, 500], strict=True):
        worker, tid, _, start, finish, _, epoch = row
        events.append({"kind": "kernel_end", "worker_id": worker, "task_id": tid, "block_count": 1,
                       "kernel_start_cycles": start, "cycles": end, "finish_cycles": finish,
                       "dispatch_cycles": start - 20,
                       "run_epoch": epoch, "block_index": 0, "cluster_lane": int(worker >= 54)})
        row[4] = end
    raw["percounter_task_events"] = {"records": events, "dropped": 0, "unmatched_deferred_updates": 0}
    (tmp_path / "source-task-map.txt").write_text("22 14\n23 15\n25 17\n")
    (tmp_path / "deps.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {"task_id": "14", "kernel_ids": [18, 19, -1], "block_num": 1},
                    {"task_id": "17", "kernel_ids": [-1, 20, -1], "block_num": 1},
                ],
                "edges": [{"pred": "14", "succ": "15"}, {"pred": "15", "succ": "17"}],
            }
        )
    )
    record_path = tmp_path / "chip_swimlane_records.json"
    record_path.write_text(json.dumps(raw))
    nodes, edges, rows, _ = bound.read_round(tmp_path, plan, 1)
    assert nodes[14] == {"sync": True, "units": [(0, 0, "aic", 8), (0, 1, "aiv", 4)]}
    assert nodes[15] == {"sync": False, "units": []}
    assert nodes[17]["units"] == [(0, 1, "aiv", 8)]
    placement = bound.analyze_placement(nodes, edges, rows)
    assert placement["fixed_order_us"] == pytest.approx(1.6)
    assert placement["l2_kernel_span_us"] == pytest.approx(1.7)
    assert placement["chain_gap_us"] == pytest.approx(0.1)
    assert [step["task"] for step in placement["chain"]] == [22, 25]
    assert placement["chain"][-1]["prior_worker"] == 0
    assert placement["chain"][-1]["gap_before_dispatch_us"] == pytest.approx(0.08)
    assert placement["chain"][-1]["gap_after_dispatch_us"] == pytest.approx(0.02)
    assert len(rows) == 3
    solved = bound.solve_model(nodes, edges, bound.CAPACITIES, 2)
    assert solved["optimal"] and solved["lower_ticks"] == 16

    raw["aicore_tasks"][0][3] = 800
    events[0]["kernel_start_cycles"] = 800
    events[0]["dispatch_cycles"] = 780
    record_path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="early release at t25"):
        bound.read_round(tmp_path, plan, 1)

@pytest.mark.parametrize("sync", [False, True])
def test_observed_worker_order_may_conflict_with_exact_co_start(monkeypatch, sync):
    pytest.importorskip("ortools")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent / "analysis"))
    bound = importlib.import_module("swa_sync_bound")
    nodes = {t: {"sync": sync} for t in (1, 2)}
    # Worker 0 executes t1 then t2. Worker 1 executes t2 then t1.
    rows = [bound.KernelExecution(1, t, t, w, 1, "aiv", w, 20, start, start + 100, 10**9, 1, start - 10, start + 115)
            for w, t, start in [(0, 1, 100), (0, 2, 300), (1, 2, 110), (1, 1, 290)]]
    result = bound.analyze_placement(nodes, [], rows)
    if sync:
        assert result["fixed_order_us"] is None
    else:
        assert result["fixed_order_us"] == pytest.approx(0.2)
    assert result["l2_kernel_span_us"] == pytest.approx(0.3)
    assert result["chain_gap_us"] == pytest.approx(0.1)

def test_saved_placement_reads_completed_run(tmp_path, monkeypatch):
    pytest.importorskip("ortools")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent / "analysis"))
    saved = importlib.import_module("saved_placement")
    monkeypatch.setattr(saved, "ROWS_PER_ROUND", 1)
    model = tmp_path / "model"
    model.mkdir()
    build = dict.fromkeys(("plan_sha256", "callable_sha256", "runner_sha256"), "sample")
    common = dict(device=0, runtime_sha256={"host": "pinned"}, build=build)
    (model / "summary.json").write_text(json.dumps(dict(
        **common, capacities=saved.CAPACITIES, t25_block_num=54, quantum_ns=100, lower_bound_mean_us=1.0)))
    for level in (0, 2):
        folder = tmp_path / f"L{level}"
        folder.mkdir()
        result = dict(runtime="percounter", profiling_level=level, warmup=1, rounds=10,
                      numerical_validation=True, aicore_samples_ms=[0.002] * 10, device_mean_ms=0.003)
        (folder / "summary.json").write_text(json.dumps(dict(
            **common, case="swa", status="passed", platform="a6", results=[result])))
    (model / "tasks.csv").write_text("task_id,source_task,block_num,sync_start\n3,25,1,0\n")
    (model / "edges.csv").write_text("pred_task_id,succ_task_id\n")
    (model / "blocks.csv").write_text(
        "round,source_task,task_id,block_idx,subtask_slot,core_type,worker,func_id,"
        "start_cycles,kernel_end_cycles,clock_hz,duration_ticks\n"
        + "".join(f"{i},25,3,0,1,aiv,54,20,200,1200,1000000000,10\n" for i in range(1, 11)))
    for i in range(1, 11):
        folder = tmp_path / f"L2/percounter/rank0/run{i}"
        folder.mkdir(parents=True)
        capture = folder / "chip_swimlane_records.json"
        raw = {"chip_swimlane_level": 2, "metadata": {"runtime": "percounter", "clock_freq_hz": 10**9,
               "core_types": ["aic"] * 54 + ["aiv"] * 54}, "aicore_tasks": [[54, 3, 1, 200, 1250, 20, i]],
               "scheduler_tasks": {"producer": "aicore", "records": [[54, 1, 180, 1250, i]]}}
        capture.write_text(json.dumps(raw))
    summary = saved.report(tmp_path)
    assert summary["fixed_order_valid_rounds"] == 10
    assert summary["fixed_order_mean_us"] == summary["l2_kernel_span_mean_us"] == 1.0
    assert summary["device_l0_mean_us"] == 3.0
    raw["scheduler_tasks"]["records"][0][2] = 250
    capture.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="Invalid block timing"):
        saved.report(tmp_path)


def test_sensitivity_uses_matching_work_and_clips_early_claim(monkeypatch):
    pytest.importorskip("ortools")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent / "analysis"))
    tool = importlib.import_module("task_sensitivity")
    row_type = importlib.import_module("swa_sync_bound").KernelExecution
    rows = [row_type(1, 25, 25, b, 1, "aiv", b, 20, 2000, 3000 + 100 * (b < 10), 10**9,
                     10 + int(b < 10), 1900, 3200) for b in range(54)]
    rows.append(row_type(1, 22, 22, 0, 0, "aic", 54, 18, 1700, 1800, 10**9, 1, 1600, 1810))
    raw = {"percounter_task_events": {"records": [
        dict(task_id=22, kind="claim", block_index=0, cycles=900, claim_start_cycles=800),
        *[dict(task_id=22, kind=kind, block_index=0, worker_id=54, cycles=cycles)
          for kind, cycles in (("inputs_ready", 1100), ("entry_commit", 1200), ("ready", 1500))],
    ]}}
    chain = [dict(task=22, block=0, worker=54, prior_kernel_end_cycles=1000,
                  dispatch_cycles=1600, gap_before_dispatch_us=0.6)]
    quant, mix = tool.task_windows(rows, raw, chain, 54)
    assert quant["p50_us"] == {1: 1.0, 2: 1.1}
    assert quant["last_blocks"] == list(range(10))
    assert mix["in_owner_claim_us"] == 0 and mix["after_owner_claim_us"] == pytest.approx(0.6)
    assert mix["detailed_hits"] == 1 and mix["to_ready_us"] == pytest.approx(0.3)
    nodes = {22: {"sync": True, "units": []}, 25: {"sync": False, "units": []}}
    gains = tool.sensitivity(nodes, [(22, 25)], rows, {"aic": 1, "aiv": 54}, 1.2, 5)
    assert gains[25] == pytest.approx((0.2, 0.2))
