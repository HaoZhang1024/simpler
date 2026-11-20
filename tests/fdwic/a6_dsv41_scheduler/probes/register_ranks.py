#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Aggregate one fixed concurrent-access experiment by within-round finish rank."""

import argparse
import csv
import math
import sys
from collections import defaultdict
from statistics import mean


def percentile(ordered, fraction):
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    return ordered[lower] + (ordered[math.ceil(index)] - ordered[lower]) * (index - lower)


def write_ranks(rows, output, workers, rounds, tick_hz):
    if min(workers, rounds, tick_hz) < 1:
        raise ValueError("workers, rounds and tick frequency must be positive")
    samples = defaultdict(dict)
    for row in rows:
        epoch = int(row["round"])
        worker = (row["die"], row["core_type"], row["worker"])
        start, end = int(row["start_tick"]), int(row["end_tick"])
        if not all(worker) or worker[1] not in ("AIC", "AIV") or min(start, end - start) < 0:
            raise ValueError(f"invalid worker or timestamps in round {epoch}: {row}")
        if worker in samples[epoch]:
            raise ValueError(f"duplicate worker {worker} in round {epoch}")
        samples[epoch][worker] = (start, end)
    if len(samples) != rounds:
        raise ValueError(f"expected {rounds} rounds, found {len(samples)}")
    roster = set(next(iter(samples.values())))
    columns = [[] for _ in range(workers)]
    for epoch, entries in samples.items():
        if len(entries) != workers or entries.keys() != roster:
            raise ValueError(f"unexpected worker count or roster in round {epoch}")
        zero = min(start for start, _ in entries.values())
        for rank, end in enumerate(sorted(end for _, end in entries.values())):
            columns[rank].append((end - zero) * 1_000_000 / tick_hz)
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("rank", "mean_us", "p10_us", "p90_us", "mean_gap_from_previous_ns"))
    previous = None
    for rank, values in enumerate(columns, 1):
        values.sort()
        avg = mean(values)
        gap = "" if previous is None else f"{(avg - previous) * 1000:.4f}"
        writer.writerow((rank, f"{avg:.6f}", f"{percentile(values, 0.1):.6f}", f"{percentile(values, 0.9):.6f}", gap))
        previous = avg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_csv", help="one validated arm, width, topology and measured batch")
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=192)
    parser.add_argument("--tick-hz", type=int, required=True, help="frequency of the shared timestamp source")
    args = parser.parse_args()
    with open(args.raw_csv, newline="", encoding="utf-8-sig") as source:
        write_ranks(csv.DictReader(source), sys.stdout, args.workers, args.rounds, args.tick_hz)


if __name__ == "__main__":
    main()
