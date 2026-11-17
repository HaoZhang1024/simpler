#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Export a fixed SWA fixture or compile only its required C++ kernels."""

import argparse
import gzip
import hashlib
import io
import json
import shlex
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUITE = HERE.parent / "dsv41_scheduler"
FIXTURE = HERE / "fixtures"
FLAVOR = "pypto_lib_latest"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def capture(command):
    return subprocess.check_output([str(arg) for arg in command], text=True)


def selected_records(tools, plan):
    records = json.loads(capture([tools / "record-tool", "--records-json", plan]))
    begin = next(i for i, r in enumerate(records) if r["op"] == 2 and r["id"] == 8)
    end = next(i + 1 for i, r in enumerate(records) if r["op"] == 2 and r["id"] == 35)
    tasks = [r for r in records[begin:end] if r["op"] == 2]
    executions = sum(r["blocks"] * sum(k >= 0 for k in r["kernels"]) for r in tasks)
    if len(tasks) != 16 or executions != 578:
        raise ValueError("Expected the original SWA: 16 tasks and 578 kernel instances")
    return sorted({k for r in tasks for k in r["kernels"] if k >= 0})


def export_fixture(args):
    source, destination = args.bundle.resolve(), args.output.resolve()
    case = json.loads((source / "case.json").read_text())
    if (case["flavor"], case["case"], case["device_count"]) != (FLAVOR, "swa", 1):
        raise ValueError("Export requires a materialized pypto_lib_latest/swa bundle")
    lines = (source / "rank0.txt").read_text().splitlines()
    if lines[:2] != ["DSV41_NATIVE_V1", "1 0"] or (source / "slice.txt").read_text().split() != ["8", "35"]:
        raise ValueError("Expected single-device SWA without communication")
    signature = json.loads(capture([args.tools / "native-runner", "--describe-callable", source / "callable.bin"]))
    used = selected_records(args.tools, source / "plan-rank0.bin")
    files = {
        name: (source / name).read_bytes() for name in ("rank0.txt", "slice.txt", "snapshot.txt", "plan-rank0.bin")
    }
    for line in lines[3 : 3 + int(lines[2])]:
        name = shlex.split(line)[-1]
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Input files must be relative to the source bundle")
        files[name] = (source / name).read_bytes()
    for path in sorted((source / "reference").glob("*.bin")):
        files[path.relative_to(source).as_posix()] = path.read_bytes()
    if not any(name.startswith("reference/") for name in files):
        raise ValueError("Missing original reference outputs")
    files["case.json"] = (json.dumps({"case": "swa", "flavor": FLAVOR, "device_count": 1}) + "\n").encode()
    metadata = {
        "case": "swa",
        "flavor": FLAVOR,
        "device_count": 1,
        "tasks": 16,
        "executions": 578,
        "source_model": json.loads((SUITE / "kernels" / FLAVOR / "manifest.json").read_text())["origin"],
        "source_callable_sha256": digest((source / "callable.bin").read_bytes()),
        "source_plan_sha256": digest(files["plan-rank0.bin"]),
        "capture_abi": "dsv41/record.h TensorData; validate before rebuilding on another architecture",
        "signature": signature["signature"],
        "kernel_ids": used,
        "files": {name: {"bytes": len(data), "sha256": digest(data)} for name, data in sorted(files.items())},
    }
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / "swa.tar.gz").open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode = len(data), 0o644
                    archive.addfile(info, io.BytesIO(data))
    save(destination / "fixture.json", metadata)
    print(f"Exported {len(files)} input/plan/reference files; no kernel binaries")


def unpack_fixture(directory):
    metadata = json.loads((FIXTURE / "fixture.json").read_text())
    with tarfile.open(FIXTURE / "swa.tar.gz", "r:gz") as archive:
        members = archive.getmembers()
        if sorted(member.name for member in members) != sorted(metadata["files"]):
            raise ValueError("Fixture member list differs from its manifest")
        for member in members:
            path = Path(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError("Invalid fixture member")
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            expected = metadata["files"][member.name]
            if len(data) != expected["bytes"] or digest(data) != expected["sha256"]:
                raise ValueError(f"Fixture content changed: {member.name}")
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return metadata


def build(args):
    # Compiler helpers are imported only for building, never for fixture checks.
    sys.path[:0] = [str(REPO), str(REPO / "python")]
    from simpler_setup.compile_pool import compile_slot, compile_worker_budget  # noqa: PLC0415
    from simpler_setup.elf_parser import extract_text_section  # noqa: PLC0415
    from simpler_setup.kernel_compiler import KernelCompiler  # noqa: PLC0415

    if args.jobs < 1 or not (args.pto_isa / "include/pto").is_dir():
        raise ValueError("Need positive --jobs and --pto-isa containing include/pto")
    build_dir = args.build_dir.resolve()
    bundle, tools = build_dir / "bundle", build_dir / "host"
    if bundle.exists():
        raise ValueError("Bundle already exists; use a new --build-dir for another build")
    build_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "cmake",
            "-S",
            str(SUITE / "production"),
            "-B",
            str(tools),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DSIMPLER_ROOT={REPO}",
        ],
        check=True,
    )
    subprocess.run(
        [
            "cmake",
            "--build",
            str(tools),
            "--target",
            "native-runner",
            "replay",
            "record-tool",
            "--parallel",
            str(args.jobs),
        ],
        check=True,
    )
    metadata = unpack_fixture(bundle)
    if selected_records(tools, bundle / "plan-rank0.bin") != metadata["kernel_ids"]:
        raise ValueError("Captured plan does not match the selected SWA kernels")
    compiler = KernelCompiler(args.platform)
    sources = SUITE / "kernels" / FLAVOR
    manifest = json.loads((sources / "manifest.json").read_text())
    kernels = [k for k in manifest["kernels"] if k["func_id"] in metadata["kernel_ids"]]
    if sorted(k["func_id"] for k in kernels) != metadata["kernel_ids"]:
        raise ValueError("SWA kernel sources are incomplete")
    binary_dir = build_dir / "kernels"
    binary_dir.mkdir(exist_ok=True)

    def compile_one(kernel):
        source = sources / kernel["source"]
        includes = compiler.get_orchestration_include_dirs("host_build_graph")
        includes += [str(sources / item) for item in kernel["include_dirs"]]
        with compile_slot():
            binary = extract_text_section(
                compiler.compile_incore(
                    str(source),
                    core_type=kernel["core_type"],
                    pto_isa_root=str(args.pto_isa.resolve()),
                    extra_include_dirs=includes,
                )
            )
        target = binary_dir / f"kernel-{kernel['func_id']}.bin"
        target.write_bytes(binary)
        print(f"Compiled SWA kernel {kernel['func_id']}: {kernel['name']}", flush=True)
        return {
            "id": kernel["func_id"],
            "source": source.relative_to(REPO).as_posix(),
            "source_sha256": digest(source.read_bytes()),
            "binary_sha256": digest(binary),
            "bytes": len(binary),
            "file": target.name,
        }

    with compile_worker_budget(args.jobs), ThreadPoolExecutor(max_workers=args.jobs) as pool:
        compiled = list(pool.map(compile_one, kernels))

    def signature(values):
        return f"{len(values)} " + " ".join(map(str, values))

    rows = [signature(metadata["signature"]), str(len(kernels))]
    for kernel, record in zip(kernels, compiled, strict=True):
        rows.append(
            f"{kernel['func_id']} {signature(kernel['signature'])} "
            + json.dumps(str(binary_dir / record["file"]), ensure_ascii=False)
        )
    assembly = build_dir / "assembly.txt"
    assembly.write_text("\n".join(rows) + "\n")
    subprocess.run(
        [
            str(tools / "native-runner"),
            "--assemble-orchestration",
            str(assembly),
            str(tools / "libreplay.so"),
            str(bundle / "callable.bin"),
        ],
        check=True,
    )
    save(
        build_dir / "build.json",
        {
            "platform": args.platform,
            "source_commit": capture(["git", "-C", REPO, "rev-parse", "HEAD"]).strip(),
            "pto_isa_commit": capture(["git", "-C", args.pto_isa, "rev-parse", "HEAD"]).strip(),
            "fixture_sha256": digest((FIXTURE / "swa.tar.gz").read_bytes()),
            "callable_sha256": digest((bundle / "callable.bin").read_bytes()),
            "kernels": compiled,
            "tasks": 16,
            "executions": 578,
            "replay_sha256": digest((tools / "libreplay.so").read_bytes()),
            "runner_sha256": digest((tools / "native-runner").read_bytes()),
        },
    )
    if any(name in {"torch", "pypto"} or name.startswith(("torch.", "pypto.")) for name in sys.modules):
        raise RuntimeError("Unexpected model Python dependency during SWA build")
    print(f"Ready: {bundle}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Maintainer: export the existing SWA snapshot once")
    export.add_argument("--bundle", type=Path, required=True)
    export.add_argument("--tools", type=Path, required=True)
    export.add_argument("--output", type=Path, default=FIXTURE)
    compile_case = commands.add_parser("build", help="Compile only SWA and the native replay tools")
    compile_case.add_argument("--platform", choices=["a5"], default="a5")
    compile_case.add_argument("--pto-isa", type=Path, default=REPO / "build/pto-isa")
    compile_case.add_argument("--build-dir", type=Path, default=HERE / "build/a5")
    compile_case.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.command == "export":
        export_fixture(args)
    else:
        build(args)


if __name__ == "__main__":
    main()
