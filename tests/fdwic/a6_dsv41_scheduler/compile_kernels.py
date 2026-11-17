#!/usr/bin/env python3
# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Compile/link the fixed SWA kernels without building or launching a runtime."""

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCES = HERE.parent / "dsv41_scheduler/kernels/pypto_lib_latest"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("a5", "a6"), default="a6")
    parser.add_argument("--pto-isa", type=Path, default=REPO / "build/pto-isa")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1 or not (args.pto_isa / "include/pto").is_dir():
        parser.error("Need positive --jobs and --pto-isa containing include/pto")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(REPO), str(REPO / "python")]
    from simpler_setup.compile_paths import compiler_visible_path  # noqa: PLC0415
    from simpler_setup.elf_parser import extract_text_section  # noqa: PLC0415
    from simpler_setup.kernel_compiler import KernelCompiler  # noqa: PLC0415
    from simpler_setup.toolchain import CCECToolchain  # noqa: PLC0415

    # Reuse the captured kernel argument ABI headers, not the A5 target or runtime.
    # A6 HBG must separately establish compatibility before these kernels can run.
    headers = KernelCompiler("a5")
    includes = [str(args.pto_isa.resolve() / name) for name in ("include", "include/pto", "pkg_inc")]
    includes += headers.get_incore_include_dirs() + headers.get_orchestration_include_dirs("host_build_graph")
    includes += headers.get_ascend_incore_include_dirs()
    toolchain = CCECToolchain(args.platform)
    fixture = json.loads((HERE / "fixtures/fixture.json").read_text())
    manifest = json.loads((SOURCES / "manifest.json").read_text())
    kernels = [k for k in manifest["kernels"] if k["func_id"] in fixture["kernel_ids"]]
    if sorted(k["func_id"] for k in kernels) != fixture["kernel_ids"]:
        raise ValueError("Selected SWA kernels differ from the fixture")

    def compile_one(kernel):
        source = SOURCES / kernel["source"]
        prefix = output / f"kernel-{kernel['func_id']}"
        object_path, elf_path, binary_path = (prefix.with_suffix(s) for s in (".o", ".elf", ".bin"))
        command = [toolchain.cxx_path, *toolchain.get_compile_flags(core_type=kernel["core_type"])]
        command += [
            f"-I{compiler_visible_path(p)}" for p in [*includes, *(str(SOURCES / p) for p in kernel["include_dirs"])]
        ]
        command += ["-o", str(object_path), str(compiler_visible_path(source))]
        link = [toolchain.linker_path, "-e", "kernel_entry", "-o", str(elf_path), str(object_path)]
        # Exact commands and full diagnostics remain local; summary uses relative paths.
        prefix.with_suffix(".commands.json").write_text(json.dumps([command, link], indent=2) + "\n")
        result = {
            "id": kernel["func_id"],
            "name": kernel["name"],
            "core": kernel["core_type"],
            "source": source.relative_to(REPO).as_posix(),
            "source_sha256": sha256(source),
            "stage": "compile",
            "passed": False,
        }
        with prefix.with_suffix(".log").open("w") as log:
            for stage, argv in (("compile", command), ("link", link)):
                result["stage"] = stage
                completed = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=False)
                if completed.returncode:
                    result["returncode"] = completed.returncode
                    break
            else:
                result["stage"] = "text-extraction"
                try:
                    binary_path.write_bytes(extract_text_section(elf_path.read_bytes()))
                except (ValueError, RuntimeError) as error:
                    log.write(str(error) + "\n")
                else:
                    result.update(passed=True, bytes=binary_path.stat().st_size, binary_sha256=sha256(binary_path))
        print(
            f"{kernel['func_id']:2}: {'PASS' if result['passed'] else 'FAIL'} {kernel['name']} ({result['stage']})",
            flush=True,
        )
        return result

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(compile_one, kernels))
    forbidden = [n for n in sys.modules if n.split(".")[0] in ("pypto", "torch")]
    if forbidden:
        raise RuntimeError(f"Unexpected model dependencies: {forbidden}")
    summary = {
        "platform": args.platform,
        "runtime_executed": False,
        "kernel_argument_headers": "src/a5/runtime/host_build_graph/common (compatibility unverified on A6)",
        "source_commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "pto_isa_commit": subprocess.check_output(
            ["git", "-C", str(args.pto_isa), "rev-parse", "HEAD"], text=True
        ).strip(),
        "compiler": subprocess.check_output([toolchain.cxx_path, "--version"], text=True).strip(),
        "flags": {core: toolchain.get_compile_flags(core_type=core) for core in ("aic", "aiv")},
        "fixture_sha256": sha256(HERE / "fixtures/swa.tar.gz"),
        "kernels": results,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    passed = sum(r["passed"] for r in results)
    print(f"{passed}/{len(results)} kernels compiled, linked and extracted; no device execution.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
