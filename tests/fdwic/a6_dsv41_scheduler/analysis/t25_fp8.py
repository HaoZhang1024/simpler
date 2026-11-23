# Copyright (c) PyPTO Contributors.
# Licensed under the CANN Open Software License Agreement Version 2.0. See LICENSE.
"""Matched live-output controls for the SWA func20 Rows=80 vector loop."""

from collections import Counter


STAGES = ("raw", "norm", "clip", "cast", "pack", "keep", "store")
PAIRS = (("normalize", "raw", "norm"), ("clamp", "norm", "clip"),
         ("fp8", "clip", "cast"), ("pack", "cast", "pack"), ("ub-store", "keep", "store"))
CASES = [("full72-open", 256 + 72)]
for active_rows in (24, 72):
    for mode, stage in enumerate(STAGES, start=3):
        CASES.append((f"{stage}{active_rows}", mode * 256 + active_rows))
CASES.append(("full72-close", 256 + 72))


def variants(full):
    functions = []
    dispatch = []
    for i, name in enumerate(STAGES):
        source = full.replace("split_full_vf", f"out_{name}_vf")
        begin = source.index("                vselr((RegTensor<uint32_t>&)exponent")
        cast = source.index("                vector_f8e4m3 p0")
        pack = source.index("                vor((RegTensor<uint8_t>&)p0")
        store = source.index("                vsts((RegTensor<uint8_t>&)p0")
        scale = source.index("                RegTensor<uint32_t> e0, e1;")
        if name in ("keep", "store"):
            if name == "keep":
                source = source[:store] + source[scale:]
            # Make packed bytes observable through the existing scale scatter in both arms.
            anchor = "                vscatter(pairs, scale_base, scatter_offset, four);"
            if source.count(anchor) != 1:
                raise ValueError("Expected one active-row scale scatter")
            source = source.replace(anchor, """                vor((RegTensor<uint8_t>&)pairs, (RegTensor<uint8_t>&)pairs,
                    (RegTensor<uint8_t>&)p0, all8);
""" + anchor)
        else:
            boundary = {"raw": begin, "norm": cast, "clip": cast, "cast": pack, "pack": store}[name]
            reg = "p" if name in ("cast", "pack") else "x"
            sinks = "".join(
                f"                vsts((RegTensor<uint8_t>&){reg}{lane}, dst, "
                f"(row * 512 + chunk * 256) ^ {lane * 256}, NORM_B8, all8);\n" for lane in range(4))
            source = source[:boundary] + sinks + source[scale:]
            if name == "norm":
                source = "\n".join(line for line in source.split("\n")
                                   if ", low, all," not in line and ", high, all," not in line)
        functions.append(source)
        dispatch.append(f"""        if (Rows == 80 && (mode >> 8) == {i + 3}) {{
            o_quant::out_{name}_vf<decltype(output), decltype(scales), Input>(
                output.data(), scales.data(), input.data(), mode & 255, rows);
        }} else """)
    return "".join(functions), "".join(dispatch)


def active_opcodes(name, rows):
    loops = [i for i, (_, _, op, _) in enumerate(rows) if op.startswith("VLOOP")]
    if len(loops) != 2:
        raise ValueError(f"{name}: expected separate active-row and padding loops")
    ops = Counter(op.upper() for _, _, op, _ in rows[loops[0] + 1:loops[1]])
    actual = (ops["VDIV.F32"], ops["VMUL.F32"], ops["VMIN.F32"], ops["VCVTFF.F322E4M3"],
              ops["VOR.B8"], ops["VST"] + ops["VSTS"])
    expected = {
        "raw": (0, 0, 0, 0, 0, 8), "norm": (8, 8, 0, 0, 0, 8),
        "clip": (8, 8, 8, 0, 0, 8), "cast": (8, 8, 8, 8, 0, 8),
        "pack": (8, 8, 8, 8, 6, 8), "keep": (8, 8, 8, 8, 8, 0),
        "store": (8, 8, 8, 8, 8, 2),
    }[name]
    if actual != expected or ops["VSCATTER.B16"] != 2:
        raise ValueError(f"{name}: unexpected active-row code {actual} vs {expected}; scale scatter={ops['VSCATTER.B16']}")
    return f"{name} active-row div/mul/min/fp8/or8/ub-stores=" + "/".join(map(str, actual))


def contrasts(medians):
    for label, low, high in PAIRS:
        d24, d72 = (medians[f"{high}{n}"] - medians[f"{low}{n}"] for n in (24, 72))
        yield f"{label} delta24={d24:+.4f} us delta72={d72:+.4f} us delta_slope={(d72-d24)/.048:+.2f} ns/row"
