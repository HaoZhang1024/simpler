#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Time the four stages of SWA func20 in the existing 64-block percounter replay."""

import argparse
import gzip
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import median

SWA = Path(__file__).resolve().parents[1]
SUITE = SWA.parent / "dsv41_scheduler"
ROOT = SWA.parents[2]
sys.path.insert(0, str(SWA))
from run import allocated_device, check_device  # noqa: E402


def instrument(source):
    # Retain all original operations. Read the scalar clock after the issuing
    # pipe signals S, so an asynchronous enqueue cannot masquerade as completion.
    def after(pipe, var):
        return (f"set_flag(PIPE_{pipe}, PIPE_S, EVENT_ID7); "
                f"wait_flag(PIPE_{pipe}, PIPE_S, EVENT_ID7); {var} = t25_clock();")

    ticks = """__aicore__ inline uint64_t t25_clock() {
    uint64_t tick;
    asm volatile("MOV %0, SYS_CNT" : "=l"(tick) : : "memory");
    return tick;
}
"""
    insertions = [
        ("template <int Rows>\n__aicore__ inline void run_native", ticks, True),
        ("    int active = args[5], groups =", "    uint64_t start = t25_clock(), loaded, rotated, quantized;\n", True),
        ("        rotate_tail<Rows>", "        " + after("MTE2", "loaded") + "\n", True),
        ("        o_quant::quant_vf", "        " + after("V", "rotated") + "\n", True),
        ("        int group = h / 8", "        " + after("V", "quantized") + "\n", True),
        ("    wait_flag(PIPE_MTE3, PIPE_MTE2, EVENT_ID0);\n    pipe_barrier(PIPE_ALL);",
         "\n    uint64_t stored;\n    " + after("MTE3", "stored") + """
    int block = get_block_idx(args);
    auto *row = reinterpret_cast<__gm__ uint64_t *>(args[8]) + 8 * block;
    row[0] = start; row[1] = loaded; row[2] = rotated; row[3] = quantized; row[4] = stored;
    row[5] = get_coreid(); row[6] = block; row[7] = 1;
    dcci(row, SINGLE_CACHE_LINE, CACHELINE_OUT);
    dsb(DSB_DDR);""", False),
    ]
    for anchor, addition, before in insertions:
        if source.count(anchor) != 1:
            raise ValueError(f"func20 changed at {anchor.strip()}")
        source = source.replace(anchor, addition + anchor if before else anchor + addition)
    return source


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_probe(case, out, isa, platform):
    sys.path[:0] = [str(ROOT), str(ROOT / "python")]
    from simpler_setup.elf_parser import extract_text_section
    from simpler_setup.kernel_compiler import KernelCompiler

    build = json.loads((case / "build.json").read_bytes())
    source_bundle = case / "bundle"
    if build["platform"] != platform or build["executions"] != (570 if platform == "a6" else 578):
        raise ValueError("Expected the original 64-block prepared case")
    if subprocess.check_output(["git", "-C", isa, "rev-parse", "HEAD"], text=True).strip() != build["pto_isa_commit"]:
        raise ValueError("PTO-ISA differs from the prepared case")
    for filename, key in (("plan-rank0.bin", "plan_sha256"), ("callable.bin", "callable_sha256")):
        if digest(source_bundle / filename) != build[key]:
            raise ValueError(f"Prepared {filename} differs from build.json")
    source_root = SUITE / "kernels/pypto_lib_latest"
    manifest = json.loads((source_root / "manifest.json").read_bytes())
    kernel, = (k for k in manifest["kernels"] if k["func_id"] == 20)
    source = source_root / kernel["source"]
    host = out / "host"
    subprocess.run(["cmake", "-S", SUITE / "production", "-B", host, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                    f"-DSIMPLER_ROOT={ROOT}", f"-DDSV41_ARCH={platform}",
                    "-DCMAKE_CXX_FLAGS=-DDSV41_T25_PHASE_PROBE"], check=True)
    subprocess.run(["cmake", "--build", host, "--target", "native-runner", "replay", "--parallel", "4"], check=True)
    sig = json.loads(subprocess.check_output([host / "native-runner", "--describe-callable", source_bundle / "callable.bin"]))
    compiler = KernelCompiler(platform)
    includes = compiler.get_orchestration_include_dirs("host_build_graph") + [str(source_root / d) for d in kernel["include_dirs"]]

    def compile_kernel(path):
        return extract_text_section(compiler.compile_incore(str(path), core_type="aiv", pto_isa_root=str(isa),
                                                           extra_include_dirs=includes, build_dir=str(out)))

    records = {k["id"]: k for k in build["kernels"]}
    original = records[20]
    if digest(source) != original["source_sha256"] or hashlib.sha256(compile_kernel(source)).hexdigest() != original["binary_sha256"]:
        raise ValueError("func20 source or rebuilt control machine code differs from the measured case")
    diag = out / source.name
    diag.write_text(instrument(source.read_text()))
    binary = out / "func20.bin"
    binary.write_bytes(compile_kernel(diag))

    def directions(values):
        return " ".join(map(str, [len(values), *values]))

    rows = [directions(sig["signature"]), str(len(sig["kernels"]))]
    for child in sig["kernels"]:
        kid = child["id"]
        record = records[kid]
        path = case / "kernels" / record["file"]
        if digest(path) != record["binary_sha256"]:
            raise ValueError(f"Prepared kernel {kid} changed")
        rows.append(f'{kid} {directions(child["signature"])} {json.dumps(str(binary if kid == 20 else path), ensure_ascii=False)}')
    assembly = out / "assembly.txt"
    assembly.write_text("\n".join(rows) + "\n")
    bundle = out / "bundle"
    bundle.mkdir()
    for path in source_bundle.iterdir():
        if path.name != "callable.bin":
            (bundle / path.name).symlink_to(path, target_is_directory=path.is_dir())
    subprocess.run([host / "native-runner", "--assemble-orchestration", assembly, host / "libreplay.so",
                    bundle / "callable.bin"], check=True)


def summarize(run, expected_workers):
    raw = run / "chip_swimlane_records.json"
    records = json.loads(raw.read_bytes() if raw.exists() else gzip.decompress(raw.with_suffix(".json.gz").read_bytes()))
    hz = records["metadata"]["clock_freq_hz"]
    if records["chip_swimlane_level"] != 4 or hz <= 0:
        raise ValueError("Missing L4 clock")
    mapping = dict(map(int, line.split()) for line in (run / "source-task-map.txt").read_text().splitlines() if line.strip())
    outer = defaultdict(list)
    for core, task, seq, start, end, *rest in records["aicore_tasks"]:
        if task == mapping[25]:
            outer[core].append((start, end))
    groups = defaultdict(list)
    data = (run / "t25-stamps.bin").read_bytes()
    if len(data) != 4096:
        raise ValueError("Expected 64 cache lines")
    for block, row in enumerate(struct.iter_unpack("<8Q", data)):
        if row[6:] != (block, 1) or row[0] == 0 or any(b <= a for a, b in zip(row[:4], row[1:5])):
            raise ValueError(f"Incomplete or unordered t25 stamps in block {block}")
        groups[row[5]].append(row[:5])
    expected = [1] * (2 * expected_workers - 64) + [2] * (64 - expected_workers)
    if any(sorted(map(len, groups_.values())) != expected for groups_ in (outer, groups)):
        raise ValueError("Unexpected first/later block counts")
    rows = [sorted(group)[0] for group in groups.values()]
    to_us = 1e6 / hz
    summary = {key: round(median(r[i + 1] - r[i] for r in rows) * to_us, 3)
               for i, key in enumerate(("load", "rotate", "quant", "store"))}
    summary["inner"] = round(median(r[-1] - r[0] for r in rows) * to_us, 3)
    summary["outer_L4"] = round(median(end - start for start, end in (min(g) for g in outer.values())) * to_us, 3)
    return dict(first=len(rows), later=64-len(rows), **summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Measured 64-block case directory with build.json")
    parser.add_argument("l4_lib", type=Path, help="Verified L4 onboard libraries")
    parser.add_argument("--platform", choices=["a5", "a6"], default="a6")
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--a6-query", type=Path)
    parser.add_argument("--pto-isa", type=Path, default=ROOT / "build/pto-isa")
    args = parser.parse_args()
    if args.device < 0 or (args.platform == "a6" and not args.a6_query):
        parser.error("Provide the assigned device and the A6 query executable")
    if "TASK_DEVICE" in os.environ:
        allocated_device(parser, args.device)
    elif args.platform == "a5":
        parser.error("Run the A5 control inside the device allocation")
    check_device(parser, args, args.device)
    case = args.case.resolve()
    out = Path(tempfile.mkdtemp(prefix="t25-phases-", dir=case.parent))
    print(f"Output: {out}", flush=True)
    build_probe(case, out, args.pto_isa.resolve(), args.platform)
    dest = out / "capture"
    env = dict(os.environ, TASK_DEVICE=str(args.device), DSV41_RUNNER=str(out / "host/native-runner"), DSV41_PYTHON=sys.executable)
    subprocess.run(["bash", SUITE / "production/run.sh", out / "bundle", args.l4_lib.resolve(), dest,
                    "4", "1", "3", "--runtime=percounter"], env=env, check=True)
    rank = dest / "rank0"
    result = json.loads((rank / "result.json").read_bytes())
    if not (result["passed"] and result["validated_against_fused_prefix"] and result["runtime"] == "percounter"
            and result["device"] == args.device and result["warmup"] == 1 and result["rounds"] == 3):
        raise ValueError("Expected three validated formal rounds")
    lines = [f"{args.platform} device={args.device} warmup=1 rounds=3 golden=PASS unit=us " +
             f"source={subprocess.check_output(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'], text=True).strip()}"]
    for i in (1, 2, 3):
        row = summarize(rank / f"run{i}", 54 if args.platform == "a6" else 64)
        lines.append(f"run{i} " + json.dumps(row))
    feedback = "\n".join(lines) + "\n"
    (out / "feedback.txt").write_text(feedback)
    print(feedback + f"Feedback: {out}/feedback.txt")


if __name__ == "__main__":
    main()
