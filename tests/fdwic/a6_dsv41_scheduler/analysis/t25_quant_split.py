#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Run the SWA t25 quantization controls on a single 64-block prepared graph."""

import argparse
import gzip
import json
import os
import struct
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from t25_phases import ROOT, SUITE, allocated_device, build_probe, check_device, digest

CASES = (("full72-open", 256 + 72), ("fence", 0), ("pad8", 256), ("full24", 256 + 24),
         ("scale72", 512 + 72), ("full48", 256 + 48), ("scale24", 512 + 24), ("full72-close", 256 + 72))


def replace_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError(f"Unexpected func20 source at {anchor}")
    return source.replace(anchor, replacement)


def split_sources(cpp, header):
    start = header.index("template <typename Output")
    end = header.index("#endif", start)
    full = replace_once(header[start:end], "void quant_vf(", "void split_full_vf(")
    full = replace_once(full, "uint16_t active_rows)", "uint16_t active_rows, uint16_t pad_start)")
    full = replace_once(full, "row = active_rows;", "row = pad_start;")
    scale = full.replace("split_full_vf", "split_scale_vf")
    # Keep the reduction, compact exponent and the original scale scatter.
    lo = scale.index("                vselr((RegTensor<uint32_t>&)exponent")
    hi = scale.index("                RegTensor<uint32_t> e0, e1;", lo)
    header = header[:end] + full + scale[:lo] + scale[hi:] + header[end:]
    anchor = "        o_quant::quant_vf<"
    trial = """        if (mode >= 512) {
            o_quant::split_scale_vf<decltype(output), decltype(scales), Input>(
                output.data(), scales.data(), input.data(), mode & 255, rows);
        } else if (mode >= 256) {
            o_quant::split_full_vf<decltype(output), decltype(scales), Input>(
                output.data(), scales.data(), input.data(), mode & 255, rows);
        }
        set_flag(PIPE_V, PIPE_MTE3, EVENT_ID0); wait_flag(PIPE_V, PIPE_MTE3, EVENT_ID0);
        set_flag(PIPE_V, PIPE_S, EVENT_ID7); wait_flag(PIPE_V, PIPE_S, EVENT_ID7);
        trial_end = t25_clock();
"""
    cpp = replace_once(cpp, anchor, trial + anchor)
    cpp = replace_once(cpp, "uint64_t start = t25_clock()", "int mode = args[9];\n    uint64_t trial_end, start = t25_clock()")
    cpp = replace_once(cpp, "row[1] = loaded; row[2] = rotated;", "row[1] = rotated; row[2] = trial_end;")
    return cpp, header


def stats(values):
    values = sorted(values)
    def percentile(p):
        k = (len(values) - 1) * p
        i = int(k)
        return round(values[i] + (k - i) * (values[min(i + 1, len(values) - 1)] - values[i]), 4)
    return [percentile(p) for p in (0.1, 0.5, 0.9)]


def instruction_report(out):
    from t25_quant_asm import disassemble, extract_text_section

    payload = (out / "func20.bin").read_bytes()
    elf = next((p for p in out.glob("*.elf") if extract_text_section(p) == payload), None)
    if elf is None:
        raise ValueError("No linked ELF matches the split func20 payload")
    lines = []
    for name in ("quant_vf", "split_full_vf", "split_scale_vf"):
        _, _, rows = disassemble(elf, name)
        counts = Counter(op.upper().split(".")[0] for _, _, op, _ in rows)
        listing = "\n".join(f"+{off:04x} {word} {op} {args}" for off, word, op, args in rows)
        (out / f"{name}.asm.txt").write_text(listing + "\n")
        lines.append(f"{name} instructions={len(rows)} " + " ".join(
            f"{op}={counts[op]}" for op in ("VCGMAX", "VCGMAXV2", "VPACKV2", "VDIV", "VSCATTER")))
        if not (counts["VCGMAX"] + counts["VCGMAXV2"] and counts["VSCATTER"]):
            raise ValueError(f"{name}: missing reduction or scale scatter; inspect {name}.asm.txt")
        if bool(counts["VDIV"]) != (name != "split_scale_vf"):
            raise ValueError(f"{name}: unexpected division path; inspect {name}.asm.txt")
    return lines


def read_round(run, workers):
    records = run / "chip_swimlane_records.json"
    rec = json.loads(records.read_bytes() if records.exists() else gzip.decompress(records.with_suffix(".json.gz").read_bytes()))
    hz = rec["metadata"]["clock_freq_hz"]
    if rec["chip_swimlane_level"] != 4 or hz <= 0:
        raise ValueError(f"Invalid L4 clock in {run}")
    data = (run / "t25-stamps.bin").read_bytes()
    if len(data) != 4096:
        raise ValueError(f"Expected 64 cache lines in {run}")
    by_core = defaultdict(list)
    for block, (start, begin, middle, end, stored, core, idx, valid) in enumerate(struct.iter_unpack("<8Q", data)):
        if not (0 < start < begin < middle < end < stored and block == idx and valid == 1):
            raise ValueError(f"Incomplete timestamps in {run}, block {block}")
        by_core[core].append((start, block, (middle - begin) * 1e6 / hz, (end - middle) * 1e6 / hz))
    if sorted(map(len, by_core.values())) != [1] * (2 * workers - 64) + [2] * (64 - workers):
        raise ValueError(f"Unexpected t25 worker population in {run}")
    waves = defaultdict(list)
    for core, calls in by_core.items():
        for wave, (_, block, trial, ref) in enumerate(sorted(calls)):
            waves[wave].append(dict(block=block, core=core, trial_us=trial, ref_us=ref))
    summary = {label: {key: stats([call[key] for call in waves[i]]) for key in ("trial_us", "ref_us")}
               for i, label in enumerate(("first", "later")) if i in waves}
    return dict(hz=hz, summary=summary, blocks=dict(waves))


def run_cases(out, lib, device, platform, report_only=False):
    feedback = out / ("feedback-offline.txt" if report_only else "feedback.txt")
    feedback.write_text("")
    env = dict(os.environ, TASK_DEVICE=str(device), DSV41_PYTHON=sys.executable, DSV41_RUNNER=str(out / "host/native-runner"))
    workers = 54 if platform == "a6" else 64
    def emit(line):
        print(line, flush=True)
        with feedback.open("a") as stream:
            print(line, file=stream)
    emit(f"{platform} device={device} func20={digest(out/'func20.bin')} first={workers} later={64-workers} us")
    for line in (out / "opcodes.txt").read_text().splitlines():
        emit(line)
    medians = {}
    for label, mode in CASES:
        dest = out / label
        try:
            if not report_only:
                subprocess.run(["bash", SUITE / "production/run.sh", out / "bundle", lib, dest, "4", "1", "3",
                                "--runtime=percounter"], env=dict(env, DSV41_T25_QUANT_MODE=str(mode)), check=True)
            rank = dest / "rank0"
            result = json.loads((rank / "result.json").read_bytes())
            if not (result["passed"] and result["validated_against_fused_prefix"] and result["device"] == device
                    and result["runtime"] == "percounter" and result["warmup"] == 1 and result["rounds"] == 3):
                raise ValueError(f"Invalid replay result in {rank}")
            rounds = [read_round(rank / f"run{i}", workers) for i in (1, 2, 3)]
            (dest / "blocks.json").write_text(json.dumps(rounds))
            first = [r["summary"]["first"] for r in rounds]
            def field(wave, key, index):
                return round(median(r["summary"][wave][key][index] for r in rounds), 4)
            later = field("later", "trial_us", 1) if workers < 64 else None
            medians[label] = field("first", "trial_us", 1)
            emit(f"{label} golden=PASS first_p50={[r['trial_us'][1] for r in first]} "
                 f"first_p10/p90={field('first','trial_us',0)}/{field('first','trial_us',2)} "
                 f"ref72={field('first','ref_us',1)} later_p50={later}")
        except Exception as exc:
            emit(f"{label} ERROR {exc}; see {dest}/rank0/console.log")
            raise
    full72 = (medians["full72-open"] + medians["full72-close"]) / 2
    emit("first-wave ns/active-row "
         f"full24-48={(medians['full48'] - medians['full24']) * 1000 / 24:.2f} "
         f"full48-72={(full72 - medians['full48']) * 1000 / 24:.2f} "
         f"scale24-72={(medians['scale72'] - medians['scale24']) * 1000 / 48:.2f}")
    emit(f"full72 close-open={medians['full72-close'] - medians['full72-open']:+.4f} us")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("case", type=Path)
    p.add_argument("l4_lib", type=Path)
    p.add_argument("--platform", choices=("a5", "a6"), default="a6")
    p.add_argument("--device", type=int)
    p.add_argument("--a6-query", type=Path)
    p.add_argument("--pto-isa", type=Path, default=ROOT / "build/pto-isa")
    p.add_argument("--prepare-only", action="store_true", help="Build outside the device allocation")
    p.add_argument("--prepared", type=Path, help="Run a split probe previously built with --prepare-only")
    p.add_argument("--report-only", action="store_true", help="Read existing captures under --prepared on the host")
    args = p.parse_args()
    case = args.case.resolve()
    if args.prepared and args.prepare_only:
        p.error("select either --prepare-only or --prepared")
    if args.report_only and not args.prepared:
        p.error("--report-only requires --prepared")
    if args.prepared:
        out = args.prepared.resolve()
        identity = json.loads((out / "split.json").read_bytes())
        if identity != [args.platform, digest(case / "build.json"), digest(out / "func20.bin"), digest(out / "bundle/callable.bin")]:
            p.error("prepared probe does not match the selected platform or case")
    else:
        out = Path(tempfile.mkdtemp(prefix="t25-quant-split-", dir=case.parent))
        print(f"Output: {out}", flush=True)
        build_probe(case, out, args.pto_isa.resolve(), args.platform, quant_split=True)
        (out / "opcodes.txt").write_text("\n".join(instruction_report(out)) + "\n")
        (out / "split.json").write_text(json.dumps([args.platform, digest(case / "build.json"), digest(out / "func20.bin"),
                                                    digest(out / "bundle/callable.bin")]))
    if args.prepare_only:
        return
    if args.report_only:
        device = json.loads((out / CASES[0][0] / "rank0/result.json").read_bytes())["device"]
        run_cases(out, args.l4_lib, device, args.platform, report_only=True)
        return
    device = allocated_device(p, args.device) if "TASK_DEVICE" in os.environ else args.device
    if device is None or device < 0 or (args.platform == "a5" and "TASK_DEVICE" not in os.environ):
        p.error("select the allocated device")
    if args.platform == "a6" and not args.a6_query:
        p.error("provide --a6-query")
    check_device(p, args, device)
    if (out / "feedback.txt").exists():
        p.error("this probe has an existing capture; select a fresh output")
    print(f"Feedback: {out}/feedback.txt", flush=True)
    run_cases(out, args.l4_lib.resolve(), device, args.platform)


if __name__ == "__main__":
    main()
