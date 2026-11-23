# A6 percounter SWA 性能分析与每日进展

## 当前状态与反馈位置

**11 月 23 日，两端的 t25 已用同一探针对齐。** A6 每个首块的量化比 A5 多 3.548 µs，占核内总差的约 78%。[分段结果](#1a-t25-首块分段)

**黄区下一项**是从 54 块 B1 的三个正式轮识别末块，分别统计 10 个双 head 块和 44 个单 head 块。先读旧档，缺逻辑块号时只采 54 块 L4。[执行命令与回填位置](#54-块按-block_idx-分组)

**蓝区已完成 t25 量化指令对照和 A5 除法对照实验。** 两端每个有效行都执行 8 条向量除法，A6 每行在分组求最大值后多执行 2 条打包指令。A5 上替换除法的配对净收益为 0.066–0.072 µs。[机器码与分段实测](#quant_vf-指令与除法对照)

| 项目 | 本轮结果 | 记录 |
| --- | --- | --- |
| t25 单块分段 | 两端各 3 轮 golden 通过，A5 / A6 量化分别为 4.260 / 7.808 µs | [两端对照](#1a-t25-首块分段) · [A6 原始输出](#黄区任务-t25-单块分段计时) |
| t35 同核接块 | 每轮 10 个复用核的记录齐全，接块间隔内均无其他 kernel | [三轮 t35 输出](#黄区任务-t35-接块与-t22-启动) |
| t22 启动 | 每轮均取得 48 个 AIC 和 48 个 AIV 的 dispatch 时间 | [三轮 t22 输出](#黄区任务-t35-接块与-t22-启动) |

| 项目 | 状态 | 回填位置 |
| --- | --- | --- |
| t25 L0 | 已收，四批 golden 通过 | 见下方四批均值 |
| A6 TCM 接口 | 本机 SDK 与 PTO-ISA 检索已收 | 见下方检索范围 |
| t25 L4 与全图对照 | 已收，A/B 各 3 个正式轮 | [蓝区复核](#t25-结果复核) · [黄区摘要与归档位置](#黄区-l4-结果) |

### 1A t25 首块分段

两端使用相同 SWA 输入、原始 64 块 plan、72 个有效行、8 组和容量 80。每块处理 1 个 head。先核对原始 func20 重编的机器码，再给四段加时间戳。每端预热 1 轮、测 3 轮。每轮取每个 AIV 在 t25 上执行的第一个块，先算这些块的中位数，再取三轮中位数。A5 每轮有 64 个首块，A6 每轮有 54 个首块和 10 个后续块。

| 首块窗口（µs） | A5 | A6 | A6 − A5 |
| --- | ---: | ---: | ---: |
| 输入搬运及准备 | 1.194 | 1.605 | +0.411 |
| 旋转 `rotate_tail` | 0.370 | 0.676 | +0.306 |
| 量化 `o_quant::quant_vf` | 4.260 | 7.808 | **+3.548** |
| 写回及排空 | 0.565 | 0.874 | +0.309 |
| 核内总计 `inner` | 6.410 | 10.968 | **+4.558** |
| 包住 kernel 调用的 L4 窗口 | 7.276 | 11.834 | +4.558 |

量化占核内差值的 3.548 / 4.558 ≈ 78%。各阶段与总时长分别取中位数，分项之和会略有偏差。探针在每段末尾等待流水线完成。与原 L4 首块相比，外层窗口在 A5 上增加约 0.77 µs，在 A6 上增加约 0.80–0.82 µs。[量化指令对照与 A5 单项实验](#quant_vf-指令与除法对照)

A5 蓝区卡 1，任务 `task_20261123_094813_191159825561`，诊断源码 `1cb9d9448`，沿用 A5 基线 L4 runtime、输入和其余 18 个 kernel。三轮均通过 SWA golden。A6 原始三轮见下方黄区记录。

| A5 轮次 | 首块 / 后续 | load | rotate | quant | store | inner | outer_L4 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 64 / 0 | 1.194 | 0.370 | 4.257 | 0.565 | 6.410 | 7.276 |
| 2 | 64 / 0 | 1.194 | 0.370 | 4.283 | 0.579 | 6.454 | 7.360 |
| 3 | 64 / 0 | 1.188 | 0.370 | 4.260 | 0.559 | 6.388 | 7.213 |

### quant_vf 指令与除法对照

固定原始 64 块 plan，每块处理 1 个 head。对 func20 的设备 ELF 按符号地址与长度反汇编，取实际走到的 `quant_vf<Rows=80>`。每个 head 有 72 个有效行、8 个补零行，每个有效行处理两个 256 元素的 chunk。下表数的是反汇编指令，按一个有效行列数。FP8 数据和 scale 在此段写入 UB，后续 UB 到 GM 的写回另计。[两端逐条指令、相对地址与编码](../results/2026-11-23-t25-quant/quant-vf-80.asm.txt)

| 量化步骤 | A5 | A6 | 对差距的判断 |
| --- | --- | --- | --- |
| 读 UB 输入，BF16 转 FP32 | 2 条 VLD、8 条 BF16→FP32 转换 | 同数量 | 输入元素数和转换指令数一致 |
| 分组求最大值，准备 scale | 2 条 VCGMAX 后直接取指数 | 2 组 VCGMAXV2 → VPACKV2 后取指数 | 每个 chunk 多 1 条 VPACKV2，处在归约结果到 scale 的依赖上 |
| 按 scale 归一化、限幅 | 8 条 VDIV.f32、8 条 VMUL.f32 | 同数量 | 每个 head 各执行 576 条向量除法，单条吞吐和相关等待仍可不同 |
| 转 FP8、打包和保存 | 8 条 FP32→FP8、6 条 VOR.b8、2 条 VST、2 条 VSCATTER | 同数量 | payload 与 scale 的 UB 存储次数一致 |
| 每个有效行的完整循环体 | 110 条 | 112 条 | 72 行多执行 144 条指令，位置是上述两处归约后打包 |

整个向量函数 A5 为 155 条 / 620 B，A6 为 158 条 / 632 B。还有 1 条额外的标量立即数装载在循环外。有效行循环体的静态指令数增加约 1.8%，实测量化窗口由 4.260 增到 7.808 µs，增加约 83%。窗口还包含向量函数启动及等待向量流水线完成。现有证据能定位新增指令及其依赖，无法给单条 VPACK、VDIV 或流水线等待分配微秒数。

**机器码核验。** 蓝区同一 CANN 编译环境、PTO-ISA `83b1b2b5`、相同源码与 case 参数，分别生成 `dav-c310-vec`、`dav-920r1-vec`。两端重编原版的整个 `.text` 分别与蓝区 A5 实测包和蓝区 A6 离线归档包逐字节一致。对每个目标另编分段探针，`quant_vf<80>` 函数体与该目标原版也逐字节一致。A5 分段版整个 func20 与实测包一致。黄区 A6 分段版的跨区指纹仍待核对。54 块任务完成后，可离线运行下面一行。两行预期值依次为 `8b64230a47d5e3a4a4f7c2a373e464549893d914434c5867e04d70cc9ac67f23`、`fa7da38a7c55e17b314454b3cb343fa0ff7f35ff81c5fb9dc320c253f988e543`。若不同，蓝区按现场 ELF 重新核对指令。

```bash
sha256sum "${SWA_RUN:?原 64 块 SWA 目录}/case/kernels/kernel-20.bin" "${T25_PHASES:?原 t25-phases-3t468wbh 目录}/func20.bin"
```

**蓝区 A5 同卡分段实验。** A 保留 VDIV。B 用非零的 FP32 指数构造精确的二次幂倒数，再以 VMUL 做缩放，保留零值处理、限幅、FP8 舍入及 scale 写出。两端 B 的有效行循环里均为 0 条 VDIV、16 条 VMUL，其中 8 条承担原来的除法；每行另增 4 条倒数指数运算。下表给出整个替换的净效果。设备 1，任务 `task_20261123_115108_370378427149`，同一分配内按 A1、B1、B2、A2 运行。每批预热 1 轮、正式 3 轮，每轮 64 个首块，SWA golden 全过。[十二轮四段与 L4 外层原始结果](../results/2026-11-23-t25-quant/a5-quant-reciprocal.json)

| A5 批次 | 三轮首块量化中位数（µs） | 批中位数（µs） |
| --- | --- | ---: |
| A1 原版 | 4.282 / 4.277 / 4.245 | 4.277 |
| B1 倒数 | 4.210 / 4.205 / 4.205 | 4.205 |
| B2 倒数 | 4.207 / 4.216 / 4.213 | 4.213 |
| A2 原版 | 4.279 / 4.261 / 4.290 | 4.279 |

A1−B1 为 0.072 µs，A2−B2 为 0.066 µs。A5 上这个替换只改变约 0.07 µs。3.548 µs 是**两端原版**的差；要算此替换能缩小多少，应取 `(A6 原版−A6 倒数版) − (A5 原版−A5 倒数版)`。两端同批控制组优先于历史均值。对照结果包含除法替换、指数运算和编译器调度的共同影响。

**后续 A6 对照入口（54 块任务完成后使用）。** 在原 64 块单块分段命令末尾加 `--quant-reciprocal` 即可测 B；原命令测 A。固定 `SWA_RUN`、`L4_LIB` 和卡号，按 A–B–B–A 各执行一次，记录四份 `feedback.txt` 的 quant 三轮值及 golden。若 A6 也只省约 0.07 µs，下一项优先查分组最大值到 scale 的链条，以及向量函数启动与等待。若 A6 省得更多，用上式报告缩小的差距，保留余量继续定位。

| A6 回填（原 64 块） | 结果 |
| --- | --- |
| 原版 / 分段版 func20 指纹 | 待填两行 |
| A1 / B1 / B2 / A2 三轮 quant 和 golden | 待填 |

```bash
(
  set -e
  for group in A1 B1 B2 A2; do
    flags=()
    if [[ "$group" == B* ]]; then flags+=(--quant-reciprocal); fi
    echo "$group"
    python tests/fdwic/a6_dsv41_scheduler/analysis/t25_phases.py \
      "${SWA_RUN:?64 块基线目录}/case" "${L4_LIB:?原 L4 运行库}" --platform a6 \
      --a6-query "$SWA_RUN/query/query" --device "${DEVICE:?同一张 A6 卡}" "${flags[@]}"
  done
)
```

### 1B 黄区沿用 54 块 replay

对本次冻结 SWA，黄区直接使用已通过 golden 的 `swa-t25-lk1vgyf9/t25-54`。A5 基线保留 64 块。黄区现有的 Simpler、PTO-ISA 和 prepared SWA 足以运行。

模型验证入口生成的 Host C++ 对 `quant_o_vf` 调用 `rt_available_aiv_count()`，把返回值限制在 1–64，再调用 `launch_spec.set_block_num(...)` 和 `rt_submit_aiv_task(...)`。已有 replay 在同一处用计划中的 `header.block_num` 设置提交参数。`t25_ab.py` 逐条检查 A6 的 A/B 计划，唯一变化是 t25 从 64 块改为 54 块。两条路径对本例给 func20 的工作分法相同。kernel 按实际 block 数跨步遍历 64 个 head，所以 54 块仍覆盖全部工作。黄区的验收依据是已完成的 replay 实测。[计划校验](../analysis/t25_ab.py) · [replay 提交](../../dsv41_scheduler/production/replay.cpp) · [四批实测](#t25-的-64--54-block-对照)

下次在黄区单独运行 54 块版本时，在仓库根目录加载原 A6 CANN 和 venv，沿用原来的 `SWA_RUN`、`T25_RUN` 和已分配的 `DEVICE`。其中 `T25_RUN` 指向包含 `t25-54/` 的实验目录。已有测试结果可直接用于此次交付。

```bash
python tests/fdwic/a6_dsv41_scheduler/run.py --platform a6 --runtime percounter \
  --device "${DEVICE:?已分配卡号}" --a6-query "${SWA_RUN:?SWA 基线目录}/query/query" \
  --runtime-lib "$SWA_RUN/lib/a6/onboard" --build-dir "${T25_RUN:?t25 实验目录}/t25-54" \
  --output "$T25_RUN/run54-$(date +%Y%m%d-%H%M%S)" --warmup 1 --rounds 10
```

### 54 块按 block_idx 分组

| 已有 B1 三轮 L4 | 蓝区能确认的结果 |
| --- | --- |
| t25 的 54 次调用 | 每轮 54 个 AIV 各跑一次。任务跨度中位数 29.271 µs，范围 28.802–31.195 µs。54 块混合统计的单次调用中位数为 11.047 µs。 |
| 单 head 块 | 逻辑块 10–53，各算同号 head。44 块的耗时等逐块身份回填。 |
| 双 head 块 | 逻辑块 0–9，各算 head `i` 和 `i+54`。10 块的耗时及每轮最后完成的逻辑块等逐块身份回填。 |

已有摘要保留了各轮的 worker 数和任务端点。此版 percounter 的 `aicore_tasks` 七列依次是 worker、任务号、核内记录序号、开始 tick、结束 tick、接收到开始的 tick 数和 epoch。任务号识别 t25，核内序号在每个 worker 上单独递增。把七列按 worker 或时长排序都无法恢复逻辑块号。[L4 写出代码](../../../../src/a5/runtime/percounter/host/profiling.cpp#L69) · [t25 按逻辑块遍历 head](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/o_quant_vf.cpp#L82)

**第一步，离线读旧档。** 在仓库根目录执行，`T25_L4` 指向此前归档的 `t25-l4-3evzw1k0`。脚本按同轮任务映射找出 t25，以最大结束 tick 识别最后完成的 worker，保留并列。现场若已有能与该次调用对应的设备执行身份，会直接打印两组结果。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t25_blocks.py "${T25_L4:?B1 归档目录}/B1/rank0"
```

**第二步，仅当旧档输出 `identity=missing`（JSON 字段 `"identity": "missing"`）时补采。** 在原 A6 卡与 CANN 环境运行下列命令。`SWA_RUN` 是原 64 块基线目录，`T25_RUN` 是已有的 `swa-t25-lk1vgyf9`，`L4_LIB` 是原 L4 percounter 库。脚本校验两份 plan 仅 t25 的块数不同，复用原输入、参考输出、18 个其余 kernel 和 runtime。只测 54 块，预热 1 轮、正式 3 轮，每轮验 golden。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t25_phases.py \
  "${SWA_RUN:?SWA 基线目录}/case" "${L4_LIB:?L4 运行库}" --platform a6 \
  --a6-query "$SWA_RUN/query/query" --device "${DEVICE:?已分配卡号}" \
  --block-plan "${T25_RUN:?原 54 块实验目录}/t25-54/bundle/plan-rank0.bin"
```

补采时 func20 在原计算和写回结束后记录逻辑块号、COREID 和一个时间戳。按本轮 L4 的物理核与 worker 映射关联，校验每个逻辑块恰好出现一次，时间戳落在对应调用内。时长取 L4 的结束减开始，包含标记写出开销。将新轮的任务跨度和旧轮并列观察扰动。旧轮的末块身份只有在旧档自身含映射时才能确认。蓝区已验证分组、并列末块的判定逻辑、错配拒绝和 54/64 两种 host 编译配置，带标记的 func20 已在蓝区用 A5 CCEC 编译。

**黄区回填在下表。** 两步脚本均打印 `t25-blocks-feedback.txt` 路径。请将文件的三行原文粘在表下。每组字段为样本数、最小、中位、最大耗时，单位 µs。`tails` 列出最大结束 tick 对应的 block_idx、head、worker、起止偏移与耗时，起止偏移以本轮首块开始为零。54 块逐项明细留在同目录 `t25-blocks.json`。

| 正式轮 | 旧档末 worker | 来源（旧档 / 补采） | 单 head 中位 µs | 双 head 中位 µs | 该来源的末块 block_idx / head / worker |
| --- | --- | --- | ---: | ---: | --- |
| 1 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 2 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 3 | 待填 | 待填 | 待填 | 待填 | 待填 |

### 黄区任务 t25 单块分段计时

复现命令使用已加载 A6 CANN 的项目 venv，工作目录为仓库根目录。沿用上轮的 `SWA_RUN`（包含原始 64 块的 `case/build.json` 与 `query/query`）、`L4_LIB`（上次 L4 的 `a6/onboard` 目录）和已分配的 `DEVICE`。PTO-ISA 位于 `build/pto-isa`；其他位置用 `--pto-isa` 指定。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t25_phases.py \
  "${SWA_RUN:?上轮 SWA 目录}/case" "${L4_LIB:?上轮 L4 运行库}" \
  --a6-query "$SWA_RUN/query/query" --device "${DEVICE:?已分配的卡号}"
```

脚本先按原参数重编 func20 并核对机器码，再编译带时间戳的 func20 和专用 Host runner、replay。新包沿用原 plan、其余 18 个 kernel 和现有 percounter。输出写入新建的 `t25-phases-*` 目录。A6 执行 1 轮预热、3 轮正式 L4，逐轮跑原 SWA golden。

| 输出字段（µs） | 时间边界 |
| --- | --- |
| `load` | 进入 `run_native` 至四次输入 TLOAD 完成，含参数准备和等待 |
| `rotate`、`quant` | 上一段结束至 `rotate_tail`、`quant_vf` 分别完成 |
| `store` | 量化完成至输出与 scales 两次 TSTORE 排空，含输出地址准备 |
| `inner`、`outer_L4` | 同一轮首块的核内总时长和 runtime 包住整个 kernel 调用的时长，各自取中位数。外层还包含入口、写出诊断记录、返回和 runtime 写屏障 |

每轮实测 54 个首块、10 个后续块。四段在设备上等对应流水线通知标量核再读钟，这会改变原有重叠。蓝区对照原 A6 首块 11.017–11.037 µs 评估扰动，用同方法的 A5 分段对照定位跨平台差值。外层与内层之差包含多项开销，末次 runtime 写屏障仍需独立证据。

内网输出目录：`build/swa-a6-MxF89z/t25-phases-3t468wbh/`

设备 0 预热 1 轮，3 个正式轮均通过 golden。以下为 `feedback.txt` 原始输出。

```text
a6 device=0 warmup=1 rounds=3 golden=PASS unit=us source=71a6b8e46
run1 {"first": 54, "later": 10, "load": 1.605, "rotate": 0.676, "quant": 7.809, "store": 0.88, "inner": 10.968, "outer_L4": 11.842}
run2 {"first": 54, "later": 10, "load": 1.607, "rotate": 0.676, "quant": 7.808, "store": 0.868, "inner": 10.963, "outer_L4": 11.815}
run3 {"first": 54, "later": 10, "load": 1.601, "rotate": 0.676, "quant": 7.807, "store": 0.874, "inner": 10.968, "outer_L4": 11.834}
```

### 黄区任务 t35 接块与 t22 启动

沿用上轮 `T25_L4`，指向含 `A1/rank0` 的 `t25-l4-3evzw1k0`。以下为归档数据的复现命令。输入为原始 records 与同轮任务映射。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t35_t22_l4.py "${T25_L4:?上轮 t25-l4 归档目录}"
```

- **t35** 每轮读取 10 个接第二块的 worker，按前块结束到后块开始裁剪事件。同名区间合并，分别报告 claim、resolve、prepare_subtask、publish_completion、async_seal。每项为“看见事件且采集完整的核数、这些核的中位耗时（µs）”。不同阶段可嵌套。`full_streams` 表示完整流数量，`with_other_kernel` 表示间隔内穿插其他 kernel 的核数，`tail_worker` 标出最后完成的核。逐核结果保留在内网 `t35-workers.json`。
- **t22** 用同轮 t18 最后一个 kernel 结束作零点。按 AIC/AIV 分别列出 t22 的 dispatch 时间和每次 dispatch 到该核 kernel 开始的耗时，四个值依次为最小、中位、P90、最大（µs），两组各期望 48 条。`t21_last_kernel_from_t18=null` 表示 t21 缺少 kernel 结束事件。第 48 次同步加一和首次读到阈值均需带同步索引的设备事件才能直接计时。

t35 / t22 六行结果（`t35-t22-feedback.txt` 原样，输入为上轮 t25-l4-3evzw1k0 的 A1 三份正式轮）：

```text
run1 t35 {"full_streams": 10, "with_other_kernel": 0, "tail_worker": 89, "phase_n_median": {"claim": [10, 2.157], "resolve": [10, 0.504], "prepare_subtask": [10, 2.428], "publish_completion": [10, 0.623], "async_seal": [10, 0.577]}}
run1 t22 {"aic": {"dispatch_n": 48, "dispatch_from_t18": [38.644, 44.317, 47.871, 48.608], "dispatch_to_own_start": [1.364, 1.992, 4.58, 6.421]}, "aiv": {"dispatch_n": 48, "dispatch_from_t18": [38.699, 46.15, 49.168, 50.723], "dispatch_to_own_start": [1.101, 1.603, 3.361, 4.538]}, "t21_last_kernel_from_t18": null}
run2 t35 {"full_streams": 10, "with_other_kernel": 0, "tail_worker": 71, "phase_n_median": {"claim": [10, 2.072], "resolve": [10, 0.506], "prepare_subtask": [10, 2.441], "publish_completion": [10, 0.544], "async_seal": [10, 0.597]}}
run2 t22 {"aic": {"dispatch_n": 48, "dispatch_from_t18": [40.265, 46.444, 49.376, 50.8], "dispatch_to_own_start": [1.369, 2.104, 5.579, 5.935]}, "aiv": {"dispatch_n": 48, "dispatch_from_t18": [40.595, 45.8, 48.794, 51.132], "dispatch_to_own_start": [0.994, 1.502, 3.638, 4.633]}, "t21_last_kernel_from_t18": null}
run3 t35 {"full_streams": 10, "with_other_kernel": 0, "tail_worker": 73, "phase_n_median": {"claim": [10, 2.201], "resolve": [10, 0.512], "prepare_subtask": [10, 2.43], "publish_completion": [10, 0.611], "async_seal": [10, 0.596]}}
run3 t22 {"aic": {"dispatch_n": 48, "dispatch_from_t18": [37.352, 45.094, 47.386, 50.817], "dispatch_to_own_start": [1.339, 2.321, 4.553, 7.409]}, "aiv": {"dispatch_n": 48, "dispatch_from_t18": [37.546, 44.187, 47.481, 50.542], "dispatch_to_own_start": [1.002, 1.577, 3.97, 5.067]}, "t21_last_kernel_from_t18": null}
```

逐核结果保留在内网：t35-workers.json（t25-l4-3evzw1k0 目录）

## 下一步要补齐的证据

以 t25=54 的 A6 实验方案与历史 A5 基线比较，L0 AICore 仍多 77.032 µs，Device 多 58.830 µs。下面优先用原来的 **64 块**做原因对照，让两端的 func20 每块各处理一个 head。A5 有一轮无预热的 L4，A6 有三轮预热后的 L4；分平台、分轮列数。

| 优先级与问题 | 已有证据 | 还缺什么、怎么判读 |
| --- | --- | --- |
| 1 · t25 量化为何更慢 | 同探针下量化多 3.548 µs。A6 每个 chunk 的归约后多一条打包指令；A5 倒数替换收益约 0.07 µs。 | 54 块任务完成后核验现场指纹，配对测出倒数替换在 A6 上的收益，与 A5 相减。[指令与实验](#quant_vf-指令与除法对照) |
| 1 · t35 同核再领一块，runtime 能省多少 | 64 块三轮中，每轮 10 个复用核的接块间隔中位数为 12.684–12.951 µs。A/B 六轮末块核的间隔为 13.465–14.422 µs，其中 claim 约 3 µs、prepare_subtask 约 2.5 µs。 | 蓝区检查 `percounter_claim_block`、`percounter_resolve`、`percounter_prepare_subtask` 的任务级字段和逐块字段。固定 t25/t35 均为 64 块、同一 plan 和 kernel，一次只改一处。用 L4 检查目标阶段和末块间隔，再用同卡 L0 A–B–B–A 和 golden 判断净收益。 |
| 2 · t22/t28 的 MIX 分工与启动等待 | t22 在 A6 拆成 48 个 1C1V block，单个 AIV gather 64 个 key；t28 由一条 AIV 承接同组的列分片。A6 的 t18 结束到 t22 首 dispatch 已有记录。 | 蓝区按同一逻辑块核对 head、key、列分片和 C/V 交接次数。t22 启动前若要归因，需对齐同轮 t21 完成、最后到达写者发出加一、首次观察到阈值和首 dispatch；分别标 worker、sync_index 和时钟。当前摘要保留了首 dispatch；t21 完成、第 48 次加一和首次读到 48 的时间仍待对齐。核内工作量与启动前等待分开记。 |

[func20 的搬运与计算](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/o_quant_vf.cpp#L82) · [runtime 参数准备](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L306) · [runtime 取票](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1029) · [两端已有 L4 端点](swa-l4-comparison.zh-CN.md)

### 两端首块与同核接块

在仓库根目录将 `T25_L4` 设为下方“黄区 L4 结果”中已归档的 `t25-l4-*` 目录。命令使用 A1（64 块）的三份正式轮与各自的源任务映射，只读取本地文件。

```bash
(
set -e
for r in 1 2 3; do
  echo "A64/run$r"
  python tests/fdwic/a6_dsv41_scheduler/analysis/compare_l4.py \
    "${T25_L4:?已有的配对采集目录}/A6-SWA-t25-64-run$r.json.gz" \
    "$T25_L4/A1/rank0/run$r/source-task-map.txt" --block-evidence
done
)
```

`first_kernel` 和 `later_kernel` 按**同一任务、同一 worker**内的执行先后区分。两者量 kernel 开始到结束；`same_task_gap` 量同核前块结束到下一块开始，可含中间其他工作。每组报样本数、中位数、P90（按名次向上取整）和最大值，时间单位 µs。A5 蓝区已用同一脚本复算，两项任务均有 64 个首块、0 个后续块。t25 首块中位数 / P90 / 最大为 **6.511 / 6.923 / 7.760**，t35 为 **7.330 / 8.077 / 9.185**。

**黄区已回填的六行原始输出**
A6 输入为黄区归档 `t25-l4-3evzw1k0` 的 A1 三个正式轮及各自的 `source-task-map`。

```text
A64/run1
t25 {"first_kernel": {"n": 54, "median_us": 11.033, "p90_us": 11.118, "max_us": 11.349}, "later_kernel": {"n": 10, "median_us": 10.992, "p90_us": 11.043, "max_us": 11.077}, "same_task_gap": {"n": 10, "median_us": 13.237, "p90_us": 14.045, "max_us": 14.524}}
t35 {"first_kernel": {"n": 54, "median_us": 9.011, "p90_us": 9.507, "max_us": 9.865}, "later_kernel": {"n": 10, "median_us": 8.901, "p90_us": 9.047, "max_us": 9.062}, "same_task_gap": {"n": 10, "median_us": 12.684, "p90_us": 13.465, "max_us": 13.853}}
A64/run2
t25 {"first_kernel": {"n": 54, "median_us": 11.037, "p90_us": 11.165, "max_us": 11.444}, "later_kernel": {"n": 10, "median_us": 11.001, "p90_us": 11.058, "max_us": 11.102}, "same_task_gap": {"n": 10, "median_us": 13.092, "p90_us": 13.805, "max_us": 14.617}}
t35 {"first_kernel": {"n": 54, "median_us": 9.047, "p90_us": 9.547, "max_us": 9.726}, "later_kernel": {"n": 10, "median_us": 8.909, "p90_us": 9.144, "max_us": 9.533}, "same_task_gap": {"n": 10, "median_us": 12.725, "p90_us": 13.365, "max_us": 13.753}}
A64/run3
t25 {"first_kernel": {"n": 54, "median_us": 11.017, "p90_us": 11.132, "max_us": 11.403}, "later_kernel": {"n": 10, "median_us": 11.012, "p90_us": 11.067, "max_us": 11.094}, "same_task_gap": {"n": 10, "median_us": 13.394, "p90_us": 13.752, "max_us": 13.91}}
t35 {"first_kernel": {"n": 54, "median_us": 8.998, "p90_us": 9.396, "max_us": 9.879}, "later_kernel": {"n": 10, "median_us": 8.911, "p90_us": 9.26, "max_us": 9.266}, "same_task_gap": {"n": 10, "median_us": 12.951, "p90_us": 13.733, "max_us": 13.798}}
```

**蓝区复核。** 每轮、每项任务均有 54 个首块、10 个后续块和 10 个同核间隔。下表取各轮中位数的范围，单位为 µs。

| 任务 | A5 首块 | A6 首块 | A6 后续块 | A6 同核间隔 |
| --- | ---: | ---: | ---: | ---: |
| t25 | 6.511 | 11.017–11.037 | 10.992–11.012 | 13.092–13.394 |
| t35 | 7.330 | 8.998–9.047 | 8.901–8.911 | 12.684–12.951 |

t25 首块多 4.506–4.526 µs，t35 首块多 1.668–1.717 µs。两项任务在 A6 上的后续块都与首块接近。缓存、搬运、计算或写回若同时影响两组，仍可能造成跨平台差距，分段计时才能继续区分。

A5 在这两项任务上每核各执行一块。A6 有 10 个核各接第二块，t35 的同核间隔还随轮次波动约 0.27 µs。多个核可以同时接块，整图收益要看末块提前多少，并用关闭插桩的 L0 验证。
## t25 的 64 / 54 block 对照

设备 0，复用此前通过的 SWA 输出目录（含 case/build.json、lib/a6/onboard、query/query），A=64 块 / B=54 块，均处理 64 个 head，按 A1、B1、B2、A2 各预热 1 轮、正式 10 轮。

**Golden：4 批全部 PASS**（各批 summary.json 中 status=passed、rounds=10、numerical_validation=true）。

| 批次        | AICore 均值（µs） | Device 均值（µs） |
| ----------- | ----------------: | ----------------: |
| A1（64 块） |           266.526 |           360.406 |
| B1（54 块） |           261.409 |           355.017 |
| B2（54 块） |           263.001 |           356.039 |
| A2（64 块） |           267.624 |           360.607 |

- AICore：**B1−A1 = −5.117 µs，B2−A2 = −4.623 µs**，A2−A1 = +1.098 µs
- Device：B1−A1 = −5.389 µs，B2−A2 = −4.568 µs，A2−A1 = +0.201 µs

两对 B−A 均为负，降幅（约 4.6~5.1 µs）明显大于 A2−A1 漂移与批内波动。40 个正式样本及各批 summary.json 已留存（脚本打印的实验目录）。

蓝区复算两批等权均值。AICore 从 267.075 降到 262.205 µs，减少 4.870 µs（1.82%）；Device 从 360.507 降到 355.528 µs，减少约 4.979 µs（1.38%）。相对历史 A5 AICore 基线 185.173 µs，B 仍高 77.032 µs。批内波动的判断来自黄区，Git 回填仅含批均值。L0 已确认本次同卡整图改善，局部归因看下轮配对 L4。

## A6 TCM 接口（本机 SDK 检索）

- **装入 TCM：未查到。** 本机 CANN 9.3.0（ascend-toolkit/latest 即 cann-9.3.0）与 PTO-ISA 83b1b2b5 中无任何 TCM 接口名、头文件或示例；A6 侧仅 `__gm__` / `__ubuf__` / `__cbuf__` 三种地址空间（TLoad 为 GM→UB / GM→CBUF）。
- **AICore scalar 从 TCM 读取：未查到。** 同上；TCMP/TCMPS 为比较指令、aclrtCmo* 为 cache maintain op，均为前缀巧合，已排除。内网平台文档本机不可达，未查。

上述结果限定于已检索的版本和资料。A6 是否提供可供 percounter 使用的 TCM，仍待平台接口资料确认。

<a id="黄区本轮命令"></a>

### 已完成的配对 L4 采集命令

以下命令留作复现。

在已加载 CANN 的环境、同一张 A6 卡上执行。沿用 L0 的 `SWA_RUN` 和 `DEVICE`。将 `T25_RUN` 设为刚才 L0 打印的 `swa-t25-*` 目录，`L4_LIB` 设为此前成功采集 A6 L4 的 percounter 运行库目录（形如 `lib/a6/onboard`，已启用 DFX、ORCH、SCHED）。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t25_l4.py \
  "${SWA_RUN:?SWA 基线目录}" "${T25_RUN:?已完成的 t25 L0 实验目录}" \
  "${L4_LIB:?已验证的 A6 L4 运行库目录}" --device "${DEVICE:?已分配的设备号}"
```

新采默认 A、B 各 3 个正式轮（共 6 个）。脚本对每个正式轮分别生成以下文件，所有时延单位均为 µs。A、B 的 kernel 区间数应分别为 570、560。

| 要回答的问题 | 采集结果 |
| --- | --- |
| 能否逐核查看两组完整泳道？ | `A6-SWA-t25-64-run1.json.gz`、`A6-SWA-t25-54-run1.json.gz` 及其余正式轮。每份为同轮 records 和 deps 转出的 Perfetto trace。保留 `A1/rank0`、`B1/rank0` 下的原始 records、deps、任务映射和 golden。 |
| t25 提前后，t28、t35 和整图是否一起提前？ | `feedback.txt` 汇总八项时间，包含 t25 跨度、以 t22 结束为零点的三个下游端点、整图 kernel 窗口，以及 t22 前和 t25 至 t35 的区间。A、B 各报中位数和最小、最大值，差值取两组中位数之差。单轮结果只代表该轮。 |
| 同一 AIV 再执行一个块，哪些调度步骤占了时间？ | 自动定位 t25、t35 每轮最后结束的 worker，提取该任务在此核上前块结束到末块开始的间隔，统计中间穿插的其他 kernel。列出与此窗口相交的 claim、resolve、prepare、完成发布、async seal。事件按窗口裁剪；各阶段可能嵌套，时长应分别读。仅执行一块时显示 `None`；未观测到某个阶段显示 `NA`。 |
| 其余 A5/A6 差距集中在哪个任务？ | `task-details.json` 保留 A、B 每个正式轮的 16 个源任务。每项包含首末时间、启动分散、活跃核数与复用分布，以及按 AIC/AIV 分开的 kernel 时长中位数和最大值。回填文本同时输出 16 行 A/B 对照，含任务跨度、启动分散以及 AIC、AIV 各自的 kernel 时长中位数。明细另留时钟、epoch 和各调度流丢失/截断字段。t18 末 kernel 到 t22 首 dispatch 在调度记录齐全时单列；这段仍包含前驱发布、会合及调度。 |

**已有成对采集时**，将 `T25_L4` 指向含 `A1/rank0` 和 `B1/rank0` 的旧输出目录，执行一次离线汇总即可。若缺少同轮 deps 或 Perfetto 转换失败，脚本仍保存可读的原始时间统计，并在反馈中标出对应轮次。补齐文件后可从同一目录重新执行。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t25_report.py "${T25_L4:?已有的 t25-l4 输出目录}"
```

### 黄区 L4 结果

设备 0，A（64 块）与 B（54 块）各预热 1 轮、正式 3 轮。两组 golden 均通过，A/B 分别有 570/560 个 kernel 区间；六轮各有 108 条调度流，上报丢失 0 条。

归档位置（内网）：`/npu/machine/z00880344/a6-swa-port/src/simpler/build/swa-t25-lk1vgyf9/t25-l4-3evzw1k0/`（含 `A6-SWA-t25-64-run1..3.json.gz`、`A6-SWA-t25-54-run1..3.json.gz`、`task-details.json`、`feedback.txt` 及 A1/B1 rank0 原始 records/deps/任务映射/golden）。

以下为脚本生成的 `feedback.txt` 全文：

```text
device 0, 3 formal rounds per plan, golden PASS A/B
metric_us: A64 median [min,max] | B54 median [min,max] | median(B) - median(A)
t25_span: 43.572 [40.828,43.895] | 29.271 [28.802,31.195] | -14.301
t22_end_to_t25_end: 51.437 [48.469,52.655] | 37.312 [36.697,38.081] | -14.125
t22_end_to_t28_start: 68.642 [64.807,71.313] | 56.729 [54.643,58.591] | -11.913
t22_end_to_t35_end: 202.449 [199.720,212.448] | 192.719 [191.276,192.748] | -9.730
graph_kernel_span: 460.947 [460.412,466.547] | 447.249 [442.692,451.857] | -13.698
first_kernel_to_t22_start: 222.599 [218.378,222.923] | 221.467 [215.083,221.502] | -1.132
t18_end_to_t22_start: 40.045 [39.496,41.915] | 38.905 [38.269,40.523] | -1.140
t25_end_to_t35_start: 118.240 [117.972,126.719] | 122.786 [119.481,122.934] | +4.546
task | A/B medians_us: task span | start spread | AIC kernel median | AIV kernel median
t8 | 12.296/12.802 | 0.676/1.084 | NA/NA | 11.254/11.226
t9 | 20.228/21.679 | 18.970/20.356 | NA/NA | 0.487/0.483
t12 | 15.159/14.674 | 5.780/5.536 | NA/NA | 8.626/8.610
t16 | 32.285/31.790 | 21.851/21.568 | 10.313/10.356 | NA/NA
t17 | 17.504/17.350 | 1.576/1.235 | NA/NA | 16.043/16.487
t18 | 35.808/37.638 | 20.830/22.400 | 20.671/20.684 | 6.654/6.636
t19 | 17.663/16.511 | 5.600/4.933 | 12.236/12.589 | NA/NA
t20 | 11.142/12.081 | 3.229/3.904 | NA/NA | 7.981/7.889
t22 | 35.721/34.890 | 13.401/15.358 | 20.595/20.322 | 22.968/22.776
t25 | 43.572/29.271 | 32.579/17.796 | NA/NA | 11.027/11.047
t28 | 44.833/46.908 | 20.157/15.792 | 20.581/20.461 | 24.928/32.434
t29 | 42.625/40.401 | 10.667/10.135 | 28.142/27.872 | NA/NA
t31 | 16.929/16.209 | 1.978/1.329 | NA/NA | 14.894/14.918
t33 | 29.839/29.701 | 0.117/0.139 | 26.570/26.849 | NA/NA
t34 | 5.643/5.804 | 1.097/1.171 | NA/NA | 5.043/4.787
t35 | 33.074/33.236 | 24.081/24.530 | NA/NA | 8.993/8.978
A1/run1: intervals=570, t25 workers=54, t25/t35 last-worker gaps_us=14.524/13.465, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=38.644
  t25 worker=80, other kernels=0, phase overlaps_us: claim=3.166 resolve=0.511 prepare_subtask=2.323 publish_completion=0.489 async_seal=0.578
  t35 worker=89, other kernels=0, phase overlaps_us: claim=3.078 resolve=0.495 prepare_subtask=2.402 publish_completion=0.536 async_seal=0.563
A1/run2: intervals=570, t25 workers=54, t25/t35 last-worker gaps_us=14.617/13.753, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=40.265
  t25 worker=79, other kernels=0, phase overlaps_us: claim=3.765 resolve=0.500 prepare_subtask=1.967 publish_completion=0.491 async_seal=0.560
  t35 worker=71, other kernels=0, phase overlaps_us: claim=3.197 resolve=0.490 prepare_subtask=2.514 publish_completion=0.442 async_seal=0.593
A1/run3: intervals=570, t25 workers=54, t25/t35 last-worker gaps_us=13.682/13.733, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=37.352
  t25 worker=56, other kernels=0, phase overlaps_us: claim=2.789 resolve=0.488 prepare_subtask=2.145 publish_completion=0.535 async_seal=0.561
  t35 worker=73, other kernels=0, phase overlaps_us: claim=2.823 resolve=0.512 prepare_subtask=2.768 publish_completion=0.446 async_seal=0.616
B1/run1: intervals=560, t25 workers=54, t25/t35 last-worker gaps_us=None/13.851, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=38.788
  t35 worker=89, other kernels=0, phase overlaps_us: claim=3.165 resolve=0.485 prepare_subtask=2.405 publish_completion=0.693 async_seal=0.586
B1/run2: intervals=560, t25 workers=54, t25/t35 last-worker gaps_us=None/14.422, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=37.689
  t35 worker=93, other kernels=0, phase overlaps_us: claim=3.379 resolve=0.521 prepare_subtask=2.798 publish_completion=0.546 async_seal=0.602
B1/run3: intervals=560, t25 workers=54, t25/t35 last-worker gaps_us=None/14.113, sched streams=108, known dropped=0, reported loss-free=True
  t18 kernel end to first t22 dispatch_us=36.900
  t35 worker=93, other kernels=0, phase overlaps_us: claim=3.374 resolve=0.512 prepare_subtask=2.473 publish_completion=0.550 async_seal=0.636
```
### t25 结果复核

| L4 端点（µs，各组三轮中位数） | A，64 块 | B，54 块 | B−A |
| --- | ---: | ---: | ---: |
| t25 首块开始 → 末块结束 | 43.572 | 29.271 | −14.301 |
| t22 结束 → t25 结束 | 51.437 | 37.312 | −14.125 |
| t22 结束 → t28 首块开始 | 68.642 | 56.729 | −11.913 |
| t22 结束 → t35 末块结束 | 202.449 | 192.719 | −9.730 |

四项均为 B 最慢一轮仍早于 A 最快一轮。t25 首块到末块开始的分散从 32.579 降到 17.796 µs，而 AIV 单次 kernel 时长中位数为 11.027 / 11.047 µs。A 的末块所在核三轮均跑过前一块，两块间隔为 13.682–14.617 µs；B 的 54 块在 54 个 AIV 上各执行一次。三轮结果支持 t25 的主要变化来自启动和收尾。单块中位数对少数处理两个 head 的 B 块不敏感。

以 t22 结束为共同起点，提前量到 t28 首块和 t35 末块仍然可见。另一个观察是 t28 AIV 单次 kernel 时长中位数从 24.928 升到 32.434 µs，t28 任务跨度从 44.833 升到 46.908 µs。当前回填无法确定该变化的原因，各区间中位数也不能直接相加归因。L4 的整图 kernel 窗口缩短 13.698 µs；关闭插桩的同卡 L0 AICore / Device 均值分别节省 4.870 / 4.979 µs。

**蓝区下一步。** 保留 64 块这条对照，优先检查同一 AIV 第二次领到同任务时，取票和参数准备中哪些工作必须按块重做，哪些任务级数据可以复用。t35 的任务描述在 A/B 间相同，六轮末块核的复用间隔为 13.465–14.422 µs，且均无其他 kernel 穿插。窗口内 claim 为 2.823–3.379 µs、prepare_subtask 为 2.402–2.798 µs、resolve 为 0.485–0.521 µs。这些事件时长是与窗口的相交部分。t35 可作为后续检验通用 runtime 改动的对照。目前已测收益归在 t25 的 SWA 分块实验下。

## 整图差距

| L0 指标（µs） | A5 基线 | A6 上一批 | A6 本次反馈 | 本次 A6 − A5 |
| --- | ---: | ---: | ---: | ---: |
| AICore wall 均值 | 185.173 | 265.768 | 267.511 | +82.338（+44.5%） |
| Device 均值 | 296.698 | 357.712 | 360.831 | +64.133（+21.6%） |

三批各预热 1 轮、正式 10 轮。本次 A6 AICore 最小 259.7、最大 275.2 µs，均值比上一批高 1.743 µs；Device 均值高 3.119 µs。本次数字按既有基线单位 µs 记录，来源为项目负责人反馈，未附提交号和校验字段。上一批 A6 已有数值校验记录。两批都指向约 80–82 µs 的 AICore 差距，当前按此定位。[硬件与测量条件](a6-a5-comparison.zh-CN.md)

## 先定位时间，再验证原因

沿两端已有 L4 从整图首个 kernel 开始，到整图末 kernel 结束，用相同任务端点切成六段。每个时刻只计入一段。

| 连续时间段（µs） | A5 | A6 | A6 − A5 |
| --- | ---: | ---: | ---: |
| 整图首 kernel 开始 → t22 首 kernel 开始 | 168.486 | 211.137 | +42.651 |
| t22 首 kernel 开始 → 末 kernel 结束 | 21.923 | 36.213 | +14.290 |
| t22 末 kernel 结束 → t25 首 kernel 开始 | 5.649 | 8.879 | +3.230 |
| t25 首 kernel 开始 → 末 kernel 结束 | 19.103 | 42.285 | +23.182 |
| t25 末 kernel 结束 → t35 首 kernel 开始 | 92.992 | 121.882 | +28.890 |
| t35 首 kernel 开始 → 整图末 kernel 结束 | 12.844 | 33.093 | +20.249 |
| **整图 kernel 窗口** | **320.997** | **453.489** | **+132.492** |

t22 前和 t25 末到 t35 首两个长区间合计多 71.541 µs，里面包含其他任务的计算。t22 前的 42.651 µs 中，t18 末 kernel 到 t22 首 dispatch 的差值是 11.173 µs。后续按可见计算前驱从 t18、t29 往前追，区分单块执行、各核启动分散和相邻任务间隔。L4 两端各一轮且预热条件不同；上表定位差距出现的位置，整图收益由同机 L0 A/B 给出。

**第一项实验选 t25。** 冻结 plan 中 func20 的参数为 72 个有效行、8 组、容量 80。设备代码选择 `run_native<80>`，共有 64 个 head 工作项，步长取 `get_block_num(args)`。A 的 64 块各领一项，B 的 54 块中有 10 块在同一次 kernel 调用中各做两项。两份 plan 的 2735 条记录逐条对比，仅 t25 的 block 数变化；逻辑 kernel 实例数由 570 变为 560。B 同时改变块间调度与块内工作分配，L0 对照给出两者合起来的净效果。[量化 kernel](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/o_quant_vf.cpp) · [A/B 脚本](../analysis/t25_ab.py)

**t35、t22 分别处理。** t35 的 func27 用常量 64 划分整块和尾块，只改 plan 会遗漏工作。蓝区先做覆盖检查，再评估按实际 block 数划分的独立候选。t22 的 func18/19 共用一份设备源码；A6 将同一逻辑块拆给两组 1C1V，每组负责一半 head，但各自 gather 全部 keys。先按每个逻辑块对齐 head、key 和同步工作量，再判断 kernel 内的慢化。运行时代码把 kernel 计时起点放在调用前，终点放在调用后的屏障之后；外层 claim、参数准备和完成发布各有自己的时间区间。[尾块 kernel](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/hc_post.cpp) · [t22 内核映射](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/sparse_gather_vf.cpp) · [percounter 计时边界](../../../../src/a5/runtime/percounter/aicore/lane_loop.h)

## 已有泳道说明了什么

| 任务 | A5 / A6 的 L4 观测 | 蓝区判断 |
| --- | --- | --- |
| t35，64 个向量 block，末块结束即整图结束 | 首块开始到末块结束为 12.844 / 33.093 µs，差 20.249；首块到末块开始为 6.721 / 24.013 µs，差 17.292 | 额外跨度约 85% 落在各块陆续启动的区间。A5 的 64 个 AIV 各跑一块；A6 的 54 个 AIV 中有 10 个各跑两块。优先看末块所在的 worker 69：前块结束到下块开始 14.201 µs，中间经过完成发布、取票、准备和派发 |
| t25，同为 64 个向量 block | 任务跨度多 23.182 µs，其中启动分散多 18.517 µs（约 80%）；A6 末块所在的 worker 84 两块间隔为 13.962 µs | 用 t25 核对是否与 t35 共有同一条调度开销路径。worker 84 的 claim 事件占 2.900 µs，整个复用间隔还包含前块发布和下块准备 |
| t22，48 个同步 block | 最晚可见计算前驱 t18 结束到首 dispatch 为 27.813 / 38.986 µs，差 11.173；首 kernel 开始到末 kernel 结束另多 14.290 µs | t21 完成与 t22 最后到达事件仍缺失，启动前的差值尚不能归因给 GM。蓝区先沿已有轮询、放行事件核对，并保留 kernel 内耗时差异 |

L4 各取一轮，A5 此轮无预热，A6 取预热后的正式轮。上表的“启动分散”是最早到最晚 kernel **开始**的时间；该区间可与已启动 block 的执行重叠。百分比只描述各任务跨度在时间轴上的位置。整图 L0 的可回收时间须由后续单项改动测量。[三任务端点对照](swa-l4-comparison.zh-CN.md) · [逐核事件记录](../results/2026-11-19-a6-percounter-l4/README.md)

### CntNotify 并发时延

96 核硬件同步起跑时，A6 原子加零读为 1.043 µs，交换写 + DSB 为 1.046 µs；A5 分别为 16.387、16.385 µs。A6 扩展组 GM 加一 + DSB 为 1.051 µs，CntNotify INC + DSB 为 1.336 µs。微基准支持当前保留 GM；生产 t22 的 48 个写者与阈值等待仍需按上表的实际事件分析。[96 / 108 核完整回填](https://github.com/HaoZhang1024/simpler/blob/2d4396a56/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#L98-L138)

## 每日进展

| 日期 | 已完成及证据 | 结果或仍缺的证据 | 下一步 |
| --- | --- | --- | --- |
| 2026-11-23 | t25 两端分段、两目标量化函数反汇编；A5 同卡完成除法对照 12 个正式轮 | 单 head 量化多 3.548 µs；A6 现场分段二进制指纹和倒数对照待收 | 黄区先完成 54 块身份分组，再进行 64 块量化对照 |
| 2026-11-20 | 蓝区按六个连续区间复算 A5/A6 泳道，生成 t25 单变量 A/B | 64 个 head 在两种分配下各覆盖一次；已验证两份 plan 只差 t25 块数 | 黄区用上方一条命令测同卡净收益 |
| 2026-11-20 | 黄区完成 002 硬件 SYNCALL 同口径六组重测 | CntNotify 微基准结项，保留 GM 基线 | A6 新一批 L0 已收到，蓝区分析 t35/t25 的尾块及 t22 的启动 |
| 2026-11-19 | A5/A6 的 L4 已对齐 t22、t25、t35；A6 正式轮采到 570 个 kernel 区间，输出校验通过。蓝区已交付整理后的 A6 源码和单卡脚本 | 已定位 t22 启动差值和 t35 尾块复用。CntNotify 作业按现场反馈已启动，分支尚无这次实测时延 | 黄区先回传 probe 原始结果；蓝区核对硬件映射和读回，统计三条路径的首、中、尾时延 |
| 2026-11-18 | 黄区现场移植版通过 A6 单卡 SWA 端到端回放和输出校验 | 取得上表 A6 L0 基线 | 与 A5 的逐任务泳道对齐 |
| 2026-11-17 | 已归档 A5 单卡 percounter 的 10 轮 L0 样本 | 取得上表 A5 L0 参考值 | 保留固定输入与原始时延，用于后续对照 |
