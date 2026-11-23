# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
import gzip
import json
import struct
import tempfile
import unittest
from pathlib import Path

from t25_phases import SUITE, instrument, reciprocal_quant, summarize
from t25_blocks import analyze, mark_block


class PhaseTest(unittest.TestCase):
    def test_quant_reciprocal(self):
        header = (SUITE / "kernels/pypto_lib_latest/vendor/external/o_quant_vf.hpp").read_text()
        alt = reciprocal_quant(header)
        self.assertNotIn("vdiv(", alt)
        self.assertEqual(alt.count(", divisor, all, MODE_ZEROING);"), 4)
        self.assertEqual(alt.count(", floor_mask, all, MODE_ZEROING);"), 4)
        for exponent in range(1, 248):
            divisor = struct.unpack("<f", struct.pack("<I", exponent << 23))[0]
            inverse = struct.unpack("<f", struct.pack("<I", (254-exponent) << 23))[0]
            self.assertEqual(divisor * inverse, 1.0)

    def test_54_block_identity_and_tail(self):
        src = (SUITE / "kernels/pypto_lib_latest/vendor/external/o_quant_vf.cpp").read_text()
        self.assertIn("row[3] = get_block_num(args);", mark_block(src))
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            stamps = bytearray(4096)
            rows, streams = [], []
            for block in range(54):
                worker = 53 - block
                duration = 100 if block >= 10 else 200
                start = 1300 if block == 52 else 1000
                rows.append([worker, 425, 1, start, start + duration, 25, 2])
                streams.append(dict(physical_core_id=worker+200, worker_id=worker, producer="aicore", core_type="aiv"))
                struct.pack_into("<4Q", stamps, 64*block, start+50, 0x1000+worker+200, block, 54)
            records = dict(chip_swimlane_level=4, metadata=dict(core_types=["aiv"]*54, clock_freq_hz=1e9),
                           aicore_tasks=rows + [[0, 424, 2, 10, 20, 0, 2]]*506,
                           scheduler_records=dict(streams=streams))
            (run / "chip_swimlane_records.json").write_text(json.dumps(records))
            (run / "source-task-map.txt").write_text("25 425\n")
            old, _ = analyze(run)
            self.assertEqual((old["identity"], old["tails"][0]["worker"], old["tails"][0]["block_idx"]),
                             ("missing", 1, None))
            stamp = run / "t25-stamps.bin"
            stamp.write_bytes(stamps)
            summary, details = analyze(run)
            self.assertEqual((summary["single"]["n"], summary["single"]["median_us"]), (44, 0.1))
            self.assertEqual((summary["double"]["n"], summary["double"]["median_us"]), (10, 0.2))
            self.assertEqual(summary["tails"][0]["block_idx"], 52)
            self.assertEqual(details[9]["heads"], [9, 63])
            struct.pack_into("<Q", stamps, 0, 9999)
            stamp.write_bytes(stamps)
            with self.assertRaisesRegex(ValueError, "outside"):
                analyze(run)
            stamp.unlink()
            rows[9][4] = rows[52][4]
            records["aicore_execution_identities"] = {"records": [
                dict(core_id=r[0], task_id=r[1], reg_task_id=r[2], run_epoch=r[6], executed=True,
                     block_num=54, block_idx=i) for i, r in enumerate(rows)]}
            raw = run / "chip_swimlane_records.json"
            raw.unlink()
            raw.with_suffix(".json.gz").write_bytes(gzip.compress(json.dumps(records).encode()))
            old_with_ids, _ = analyze(run)
            self.assertEqual([r["block_idx"] for r in old_with_ids["tails"]], [9, 52])

    def test_generated_kernel(self):
        source = (SUITE / "kernels/pypto_lib_latest/vendor/external/o_quant_vf.cpp").read_text()
        code = instrument(source)
        markers = ["start = t25_clock()", "TLOAD(tail", "loaded = t25_clock()", "rotate_tail<Rows>(",
                   "rotated = t25_clock()", "o_quant::quant_vf", "quantized = t25_clock()", "TSTORE(scale_gm",
                   "stored = t25_clock()", "dcci(row"]
        positions = [code.index(token) for token in markers]
        self.assertEqual(positions, sorted(positions))
        with self.assertRaises(ValueError):
            instrument(source.replace("rotate_tail<Rows>", "other"))

    def test_first_blocks_and_missing_stamp(self):
        for workers in (54, 64):
            with self.subTest(workers=workers), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = bytearray()
                events = []
                for block in range(64):
                    # Later blocks get lower logical IDs than first blocks on reused cores.
                    later = block < 64 - workers
                    start = 5000 if later else 1000
                    dt = 200 if later else 100
                    times = [start + i * dt for i in range(5)]
                    data.extend(struct.pack("<8Q", *times, block % workers, block, 1))
                    events.append([block % workers, 425, block, start - 10, times[-1] + 40, 0, 1])
                (root / "source-task-map.txt").write_text("25 425\n")
                (root / "chip_swimlane_records.json").write_text(json.dumps({
                    "metadata": {"clock_freq_hz": 1e9}, "chip_swimlane_level": 4, "aicore_tasks": events}))
                stamp = root / "t25-stamps.bin"
                stamp.write_bytes(data)
                got = summarize(root, workers)
                self.assertEqual(got, dict(first=workers, later=64-workers, load=0.1, rotate=0.1, quant=0.1,
                                           store=0.1, inner=0.4, outer_L4=0.45))
                data[56:64] = bytes(8)
                stamp.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "block 0"):
                    summarize(root, workers)


if __name__ == "__main__":
    unittest.main()
