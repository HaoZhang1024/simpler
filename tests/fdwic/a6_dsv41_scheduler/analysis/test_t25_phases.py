# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
import json
import struct
import tempfile
import unittest
from pathlib import Path

from t25_phases import SUITE, instrument, summarize


class PhaseTest(unittest.TestCase):
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
