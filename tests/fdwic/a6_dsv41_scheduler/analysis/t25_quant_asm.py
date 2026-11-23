#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Disassemble the Rows=80 vector function from the saved A6 ABBA artifacts."""

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "simpler_setup"))
from elf_parser import extract_text_section  # noqa: E402

# B1's original feedback records only the prefix. The ELF check uses the full payload.
MEASURED = {"A1": "27446f3f09c89d8914a8a56ce6b41274d13b679d1318f6912d64963aaca3ce72", "B1": "6f72ab89"}
REFERENCE = Path(__file__).resolve().parents[1] / "results/2026-11-23-t25-quant/quant-vf-80.asm.txt"


def batch_dir(abba, label):
    log = (abba / f"{label}.log").read_text(errors="replace")
    paths = re.findall(r"^Output: (.+)$", log, re.MULTILINE)
    if len(paths) != 1:
        raise ValueError(f"expected one Output: directory in {label}.log, found {len(paths)}")
    saved = Path(paths[0].strip())
    # The log and its sibling phase directory can move together.
    sibling = abba.parent / saved.name
    return sibling if sibling.is_dir() else saved


def output(args, **kwargs):
    proc = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if proc.returncode:
        raise ValueError(f"{args[0]} exited {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def disassemble(elf, function="quant_vf"):
    symbols = output(["readelf", "-sW", elf])
    demangled = output(["c++filt"], input=symbols)
    matches = set()
    for line in demangled.splitlines():
        fields = line.split(None, 7)
        if len(fields) == 8 and fields[3] == "FUNC" and f"o_quant::{function}<" in fields[7]:
            if re.search(r"__fp8e4m3,\s*80,\s*512,", fields[7]):
                matches.add((int(fields[1], 16), int(fields[2], 0), fields[7]))
    if len(matches) != 1:
        raise ValueError(f"{elf.name}: expected one {function}<Rows=80> symbol, found {len(matches)}")
    start, size, symbol = matches.pop()
    dump = output([os.environ.get("LLVM_OBJDUMP", "llvm-objdump"), "-d", f"--start-address={start}",
                   f"--stop-address={start + size}", elf])
    rows = [(int(addr, 16) - start, word.lower(), op, args.strip()) for addr, word, op, args in
            re.findall(r"^\s*([\da-fA-F]+):[ \t]+([\da-fA-F]{8})[ \t]+(\S+)([^\n]*)$", dump, re.MULTILINE)]
    if not size or size % 4 or [r[0] for r in rows] != list(range(0, size, 4)):
        raise ValueError(f"{elf.name}: incomplete decoding of {size} bytes; check CANN llvm-objdump")
    if any(not re.fullmatch(r"[A-Za-z][\w.]*", r[2]) or "unknown" in r[2].lower() for r in rows):
        raise ValueError(f"{elf.name}: undecoded opcode; check CANN llvm-objdump")
    return start, symbol, rows


def inspect(phase, prefix, listing):
    payload = (phase / "func20.bin").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if not digest.startswith(prefix):
        raise ValueError(f"{phase.name}/func20.bin sha256={digest}, expected {prefix}")
    elfs = sorted(phase.glob("*.elf"))
    for elf in elfs:
        if extract_text_section(elf) == payload:
            break
    else:
        raise ValueError(f"{phase.name}: {len(elfs)} linked ELF candidates, none matches func20.bin ({digest})")
    start, symbol, rows = disassemble(elf)
    lines = [f"+{off:04x}    {word}  {op} {args}".rstrip() for off, word, op, args in rows]
    listing.write_text(f"{elf.name} .text sha256={digest}\n{symbol} @0x{start:x}\n" + "\n".join(lines) + "\n")
    counts = Counter(r[2].upper().split(".")[0] for r in rows)
    focus = ("VCGMAX", "VCGMAXV2", "VPACKV2", "VDIV", "VMUL")
    report = [f"func20={digest} elf={elf.name} .text_match=yes",
              f"Rows=80 start=0x{start:x} bytes={4 * len(rows)} instructions={len(rows)}",
              "whole_symbol " + " ".join(f"{op}={counts[op]}" for op in focus)]
    for index, (_, _, op, _) in enumerate(rows):
        if op.upper().startswith("VCGMAX"):
            report.append("  " + " | ".join(lines[index:index + 4]))
    return report, [r[1] for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("abba", type=Path, help="Archived quant-abba directory with A1.log and B1.log")
    abba = parser.parse_args().abba.resolve()
    if not abba.is_dir():
        parser.error(f"archive directory missing: {abba}")
    dest = abba / "quant-vf-80"
    dest.mkdir(exist_ok=True)
    reference = REFERENCE.read_text().split("A6  quant_vf<Rows=80>")[1]
    expected = re.findall(r"^\+[\da-f]+\s+([\da-f]{8}) ", reference, re.MULTILINE)
    report = []
    failed = False
    for label, prefix in MEASURED.items():
        report.append(label)
        try:
            details, words = inspect(batch_dir(abba, label), prefix, dest / f"{label}.asm.txt")
            report.extend(details)
            if label == "A1":
                report.append(f"same_words_as_blue_a6_baseline={'yes' if words == expected else 'no'}")
        except (ValueError, OSError) as exc:
            report.append(f"ERROR {exc}")
            failed = True
    feedback = "\n".join(report) + "\n"
    (dest / "feedback.txt").write_text(feedback)
    print(feedback, end="")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
