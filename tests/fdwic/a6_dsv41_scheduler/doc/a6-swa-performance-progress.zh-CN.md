# A6 percounter SWA 性能分析与每日进展

## 当前状态与反馈位置

**本轮三项任务，共两条命令。** t25 用已分配的卡测一次；t35 和 t22 共用旧 A64 泳道，一次离线提取即可。两个命令可独立执行。[上轮数据](#两端首块与同核接块)

| 顺序 | 要回答的问题 | 执行与回填 |
| --- | --- | --- |
| 1 · t25 | A6 首块多出的约 4.5 µs 分布在哪些 kernel 阶段？ | [上板命令，回填四行](#黄区任务-t25-单块分段计时) |
| 2 · t35 | 末块核上看到的取票、准备参数开销，在其余复用核上有多普遍？ | [离线命令，回填三行 t35](#黄区任务-t35-接块与-t22-启动) |
| 3 · t22 | 从 t18 结束到 48 个 AIC 和 48 个 AIV 分别开始派发，首个和最后一批相差多少？ | [同一离线命令，回填三行 t22](#黄区任务-t35-接块与-t22-启动) |

| 项目 | 状态 | 回填位置 |
| --- | --- | --- |
| t25 L0 | 已收，四批 golden 通过 | 见下方四批均值 |
| A6 TCM 接口 | 本机 SDK 与 PTO-ISA 检索已收 | 见下方检索范围 |
| t25 L4 与全图对照 | 已收，A/B 各 3 个正式轮 | [蓝区复核](#t25-结果复核) · [黄区摘要与归档位置](#黄区-l4-结果) |

### 黄区任务 t25 单块分段计时

在已加载 A6 CANN 的项目 venv 中，从本分支仓库根目录执行。沿用上轮的 `SWA_RUN`（包含原始 64 块的 `case/build.json` 与 `query/query`）、`L4_LIB`（上次 L4 的 `a6/onboard` 目录）和已分配的 `DEVICE`。PTO-ISA 位于 `build/pto-isa`；其他位置用 `--pto-isa` 指定。

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

每轮预计 54 个首块、10 个后续块。四段在设备上等对应流水线通知标量核再读钟，这会改变原有重叠。蓝区对照原 A6 首块 11.017–11.037 µs 评估扰动，用同方法的 A5 分段对照定位跨平台差值。外层与内层之差包含多项开销，末次 runtime 写屏障仍需独立证据。

**本轮反馈位置（负责人回填）**

成功时将脚本打印的 `feedback.txt` 四行原样填入下框，带上内网输出目录。失败时填失败阶段、首条具体错误和内网日志位置，黄区即可结束本轮。原始时间戳和 L4 留在内网。

```text
内网输出目录：
执行结果：待回填
```

### 黄区任务 t35 接块与 t22 启动

沿用上轮 `T25_L4`，指向含 `A1/rank0` 的 `t25-l4-3evzw1k0`。在仓库根目录执行一次。输入为原始 records 与同轮任务映射。

```bash
python tests/fdwic/a6_dsv41_scheduler/analysis/t35_t22_l4.py "${T25_L4:?上轮 t25-l4 归档目录}"
```

- **t35** 每轮读取 10 个接第二块的 worker，按前块结束到后块开始裁剪事件。同名区间合并，分别报告 claim、resolve、prepare_subtask、publish_completion、async_seal。每项为“看见事件且采集完整的核数、这些核的中位耗时（µs）”。不同阶段可嵌套。`full_streams` 表示完整流数量，`with_other_kernel` 表示间隔内穿插其他 kernel 的核数，`tail_worker` 标出最后完成的核。逐核结果保留在内网 `t35-workers.json`。
- **t22** 用同轮 t18 最后一个 kernel 结束作零点。按 AIC/AIV 分别列出 t22 的 dispatch 时间和每次 dispatch 到该核 kernel 开始的耗时，四个值依次为最小、中位、P90、最大（µs），两组各期望 48 条。`t21_last_kernel_from_t18=null` 表示 t21 缺少 kernel 结束事件。第 48 次同步加一和首次读到阈值均需带同步索引的设备事件才能直接计时。

**t35 / t22 反馈位置（负责人回填）**

将 `t35-t22-feedback.txt` 六行原样填入下框；若输入不全，填失败轮次、首条错误与内网归档目录。即使 t25 上板遇到阻塞，本项仍可先回填。

```text
t35 / t22 六行结果：待回填
```

## 下一步要补齐的证据

以 t25=54 的 A6 实验方案与历史 A5 基线比较，L0 AICore 仍多 77.032 µs，Device 多 58.830 µs。下面优先用原来的 **64 块**做原因对照，让两端的 func20 每块各处理一个 head。A5 有一轮无预热的 L4，A6 有三轮预热后的 L4；分平台、分轮列数。

| 优先级与问题 | 已有证据 | 还缺什么、怎么判读 |
| --- | --- | --- |
| 1 · t25 单块慢在哪里 | A6 三轮首块中位数为 11.017–11.037 µs，A5 为 6.511 µs。A6 后续块为 10.992–11.012 µs。取票和准备参数在 kernel 计时窗口外。 | 本轮脚本固定 72 个有效行、8 组、容量 80，记录输入搬运、旋转、量化和写回。蓝区拿同方法的 A5 数据逐段对比，结合原 L4 首块时长判断插桩扰动。runtime 末次写屏障包含在外层窗口。 |
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
| 2026-11-20 | 蓝区按六个连续区间复算 A5/A6 泳道，生成 t25 单变量 A/B | 64 个 head 在两种分配下各覆盖一次；已验证两份 plan 只差 t25 块数 | 黄区用上方一条命令测同卡净收益 |
| 2026-11-20 | 黄区完成 002 硬件 SYNCALL 同口径六组重测 | CntNotify 微基准结项，保留 GM 基线 | A6 新一批 L0 已收到，蓝区分析 t35/t25 的尾块及 t22 的启动 |
| 2026-11-19 | A5/A6 的 L4 已对齐 t22、t25、t35；A6 正式轮采到 570 个 kernel 区间，输出校验通过。蓝区已交付整理后的 A6 源码和单卡脚本 | 已定位 t22 启动差值和 t35 尾块复用。CntNotify 作业按现场反馈已启动，分支尚无这次实测时延 | 黄区先回传 probe 原始结果；蓝区核对硬件映射和读回，统计三条路径的首、中、尾时延 |
| 2026-11-18 | 黄区现场移植版通过 A6 单卡 SWA 端到端回放和输出校验 | 取得上表 A6 L0 基线 | 与 A5 的逐任务泳道对齐 |
| 2026-11-17 | 已归档 A5 单卡 percounter 的 10 轮 L0 样本 | 取得上表 A5 L0 参考值 | 保留固定输入与原始时延，用于后续对照 |
