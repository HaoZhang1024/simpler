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
        "scheduler_tasks": {
            "producer": "aicore",
            "execution_blocks": [[54, 1, 2, 0, 1, 500], [0, 1, 2, 0, 0, 900], [54, 2, 2, 0, 1, 1800]],
        },
    }
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
    assert len(rows) == 3
    solved = bound.solve_model(nodes, edges, bound.CAPACITIES, 2)
    assert solved["optimal"] and solved["lower_ticks"] == 16

    raw["aicore_tasks"][0][3] = 800
    record_path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="early release at t25"):
        bound.read_round(tmp_path, plan, 1)
