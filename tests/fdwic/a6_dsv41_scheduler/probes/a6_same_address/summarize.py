# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Validate the capture and summarize each fixed-concurrency finish rank (SYS_CNT = 1 GHz)."""

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, quantiles

# Published A5 rank-96 means (us), results/002-hbg-same-address-access at 0d76a7d55.
BASELINE = {
    "gm_ldst_read": 1.660,
    "gm_atomic_read": 16.387,
    "gm_ldst_write": 8.931,
    "gm_atomic_write": 16.385,
    "cnt_notify_read": 1.199,
    "cnt_notify_write": 1.447,
}
WORKERS = 96
ROUNDS = 193


def summarize_csv(path, expected, cubes=48):
    samples = {name: {} for name in expected}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            name = row["scenario"]
            epoch, slot, vector, start, end = (
                int(row[key]) for key in ("round", "slot", "is_vector", "begin_tick", "end_tick")
            )
            if name not in samples or not 0 <= epoch < ROUNDS or not 0 <= slot < WORKERS:
                raise ValueError(f"Unexpected scenario, round or slot in {path}: {name}/{epoch}/{slot}")
            batch = samples[name].setdefault(epoch, {})
            if slot in batch or vector != int(slot >= cubes) or not 0 < start < end:
                raise ValueError(f"Invalid worker or timestamps: {name}/{epoch}/{slot}")
            batch[slot] = (start, end)

    results = {}
    for name, epochs in samples.items():
        if len(epochs) != ROUNDS or any(len(batch) != WORKERS for batch in epochs.values()):
            raise ValueError(f"Incomplete capture for {name}, expected {ROUNDS} x {WORKERS}")
        ranks, skews = [], []
        for epoch in range(1, ROUNDS):
            starts, ends = zip(*epochs[epoch].values())
            first = min(starts)
            skews.append((max(starts) - first) / 1000)
            ranks.append([(end - first) / 1000 for end in sorted(ends)])
        points = []
        for index, column in enumerate(zip(*ranks), 1):
            deciles = quantiles(column, n=10, method="inclusive")
            points.append(dict(rank=index, mean_us=mean(column), p10_us=deciles[0], p90_us=deciles[-1]))
        results[name] = {
            "ranks": points,
            "mean_start_skew_us": mean(skews),
            "mean_adjacent_ns": mean((r[-1] - r[0]) * 1000 / (WORKERS - 1) for r in ranks),
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    out = parser.parse_args().directory
    results = {}
    for group in ("gm", "cnt_notify"):
        names = [name for name in BASELINE if name.startswith(group + "_")]
        results.update(summarize_csv(out / f"{group}.csv", names))

    (out / "ranks.json").write_text(
        json.dumps(dict(clock_hz=1000000000, warmup=1, rounds=192, cube=48, vector=48, scenarios=results), indent=2)
        + "\n"
    )
    lines = [
        "# A6 同址六组测试结果",
        "",
        "48 AIC + 48 AIV，192 个正式轮次。时延单位为 µs，相邻间隔单位为 ns。",
        "",
        "| 场景 | 第1名 | 第48名 | 第96名 | 第96名 P10 / P90 | 起跑分散 | 相邻间隔 | A5 第96名 | A6 − A5 |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for name, a5 in BASELINE.items():
        series = results[name]
        first, middle, tail = (series["ranks"][i] for i in (0, 47, 95))
        last = tail["mean_us"]
        lines.append(
            f"| {name} | {first['mean_us']:.3f} | {middle['mean_us']:.3f} | {last:.3f} | "
            f"{tail['p10_us']:.3f} / {tail['p90_us']:.3f} | {series['mean_start_skew_us']:.3f} | "
            f"{series['mean_adjacent_ns']:.1f} | {a5:.3f} | {last - a5:+.3f} |"
        )
    (out / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
