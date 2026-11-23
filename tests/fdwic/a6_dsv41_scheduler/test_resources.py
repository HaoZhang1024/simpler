#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Check SWA resource admission against the actual archived and converted plans."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("swa_prepare", HERE / "prepare.py")
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


class ResourceCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        cls.original = root / "bundle" / "plan-rank0.bin"
        cls.converted = root / "plan-a6.bin"
        PREPARE.unpack_fixture(cls.original.parent)
        suffix = ".exe" if os.name == "nt" else ""
        cls.checker = root / f"check-resources{suffix}"
        adapter = root / f"adapt-plan{suffix}"
        flags = [
            os.environ.get("CXX", "g++"),
            "-std=c++17",
            "-O1",
            f"-I{REPO / 'tests/fdwic/dsv41_scheduler/production'}",
            f"-I{REPO / 'src/common'}",
            f"-I{REPO / 'src/common/task_interface'}",
            f"-I{REPO / 'src/a5/runtime/percounter/host'}",
        ]
        if os.name == "nt":
            flags.append("-static")
        for source, target in (("check_resources.cpp", cls.checker), ("adapt_plan.cpp", adapter)):
            subprocess.run(
                [*flags, str(HERE / source), "-o", str(target)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        subprocess.run(
            [str(adapter), str(cls.original), str(cls.converted)], check=True, capture_output=True, timeout=20
        )

    def run_check(self, plan, clusters, vectors):
        return subprocess.run(
            [str(self.checker), str(plan), str(clusters), str(vectors)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_converted_plan_preserves_sync_and_reports_waves(self):
        result = self.run_check(self.converted, 54, 1)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["tasks"], report["executions"], report["minimum_clusters"]), (16, 570, 48))
        self.assertFalse(report["runtime_executed"])
        tasks = {task["id"]: task for task in report["task_resources"]}
        self.assertEqual(tasks[22], {"id": 22, "blocks": 48, "mask": 3, "sync_start": 1, "isolated_waves": 1})
        for task_id in (9, 25, 35):
            self.assertEqual(tasks[task_id]["sync_start"], 0)
            self.assertEqual(tasks[task_id]["isolated_waves"], 2)

    def test_sync_boundary_uses_available_pairs(self):
        result = self.run_check(self.converted, 47, 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Task 22: sync_start requires 48 clusters; available 47", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.run_check(self.converted, 48, 1).returncode, 0)

    def test_original_plan_retains_a5_resource_requirements(self):
        result = self.run_check(self.original, 36, 2)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["tasks"], report["executions"], report["minimum_clusters"]), (16, 578, 24))

    def test_original_three_lane_mix_is_rejected_for_single_vector(self):
        result = self.run_check(self.original, 54, 1)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Task 22: kernel mask 7", result.stderr)

    def test_invalid_resource_arguments_are_rejected(self):
        for clusters, vectors in ((0, 1), (54, 0), (54, 3), (-1, 1), ("54x", 1), (4294967296, 1)):
            with self.subTest(clusters=clusters, vectors=vectors):
                result = self.run_check(self.converted, clusters, vectors)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_missing_and_truncated_plans_are_rejected(self):
        missing = Path(self.temporary.name) / "missing.bin"
        self.assertNotEqual(self.run_check(missing, 54, 1).returncode, 0)
        truncated = Path(self.temporary.name) / "truncated.bin"
        truncated.write_bytes(self.converted.read_bytes()[:32])
        self.assertNotEqual(self.run_check(truncated, 54, 1).returncode, 0)


if __name__ == "__main__":
    unittest.main()
