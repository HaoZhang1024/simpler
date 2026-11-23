# A6 percounter SWA

## 黄区本轮执行与回填

从 `percounter` 运行 A6 集成版 SWA，t25=54。首次切换时，在旧 checkout 的同级目录单独下载新分支；以后在新目录运行 `git pull --ff-only`。

```bash
git clone --single-branch --branch percounter https://github.com/HaoZhang1024/simpler.git simpler-percounter
cd simpler-percounter
```

加载黄区 A6 CANN 和此前使用的 Python 3.11 环境，分配到基线设备 0 后，从新 checkout 根目录执行：

```bash
DEVICE=0 bash tests/fdwic/a6_dsv41_scheduler/analysis/run_integrated_comparison.sh
```

脚本将当前提交检出到独立构建目录，按 `pto_isa.pin` 下载 PTO-ISA，运行 L0、L2 各 1 轮预热和 10 轮正式采样。检查参考输出、每轮 560 次 kernel 执行和模型求解状态。末行打印 `feedback.json` 的位置。黄区将 JSON 填入下框，同时记录 SoC、CANN 和 CCEC 版本；中途失败时填运行提交、阶段和首条错误。后续蓝区按这批结果对照 t22、t9、t35 的 dispatch 前后间隔。

**本轮 A6 集成版 t25=54 回填**

SoC / CANN / CCEC：Ascend960DT_966B7 / CANN 9.3.0（1022，`/npu/cann/1022/cann-9.3.0`）/ CCEC（bisheng ccec，clang 15.0.5，2026-10-20 构建）

设备 0，percounter 分支 `76c7c288b`（集成 #3166 MIX 前驱预取参数 + #3180 减少 GM 原子 + #3195 调度/完成路径优化 + A6 适配），独立构建目录 `build/swa-integrated-758Yr8/`，L0/L2 各 1 预热 + 10 正式轮，参考输出数值校验通过，每轮 560 次 kernel 执行，模型 10/10 轮 OPTIMAL（feasible==lower_bound）。

feedback.json：

```json
{
  "platform": "a6",
  "case": "swa",
  "device": 0,
  "runtime_sha256": {
    "dispatcher/libsimpler_aicpu_dispatcher.so": "9be46d5ef764b7e6267c402eef340039265bed4d67c967898e3e8494f61179a2",
    "onboard/percounter/libhost_runtime.so": "8b4c01158bfd7c5978bd27ae44a9d62e0beee06e89e7936386acee6ecc62d1a6",
    "onboard/percounter/libaicpu_kernel.so": "26699e7009ba4a46af12a55dbd3747116ea6ef769e582076b7365d8ce8fa5c9d",
    "onboard/percounter/aicore_kernel.o": "dded49cda5599c73f6ddcddf38ce9297a8548f6b406ac8a34f1872edb185fedc"
  },
  "t25_block_num": 54,
  "capacities": {"aic": 54, "aiv": 54},
  "capture_level": 2,
  "quantum_ns": 100,
  "time_limit_seconds_per_round": 30.0,
  "executions_per_round": 560,
  "aicore_wall_l0_mean_us": 239.8697,
  "aicore_wall_l0_min_us": 231.522,
  "aicore_wall_l0_median_us": 239.8925,
  "device_l0_mean_us": 305.49519999999995,
  "lower_bound_mean_us": 197.15,
  "fixed_order_mean_us": 198.73,
  "fixed_order_valid_rounds": 10,
  "l2_kernel_span_mean_us": 246.6253,
  "l2_chain_gap_mean_us": 51.0665,
  "l2_top_chain_gaps": [
    {"task": 22, "mean_us": 8.3914, "before_dispatch_mean_us": 8.0501, "after_dispatch_mean_us": 0.3413000000000011},
    {"task": 9, "mean_us": 7.933400000000002, "before_dispatch_mean_us": 7.516799999999999, "after_dispatch_mean_us": 0.4166000000000025},
    {"task": 35, "mean_us": 7.2052, "before_dispatch_mean_us": 6.707000000000001, "after_dispatch_mean_us": 0.49819999999999853}
  ],
  "feasible_mean_us": 197.15,
  "all_optimal": true,
  "excess_us": 42.71969999999999,
  "excess_percent_of_bound": 21.668627948262742,
  "source_commit": "76c7c288b18b6e0f88ac5e9091951dc1d7049d2a",
  "aicore_l0_samples_us": [
    248.208,
    244.50900000000001,
    242.94199999999998,
    242.684,
    240.90800000000002,
    238.877,
    238.862,
    231.522,
    236.96200000000002,
    233.223
  ],
  "critical_chain_by_source_task": {
    "22": {"rounds_present": 10, "gap_us": 8.3914, "gap_before_dispatch_us": 8.0501, "gap_after_dispatch_us": 0.34130000000000005},
    "9": {"rounds_present": 10, "gap_us": 7.933400000000002, "gap_before_dispatch_us": 7.516799999999999, "gap_after_dispatch_us": 0.41659999999999997},
    "35": {"rounds_present": 10, "gap_us": 7.2052, "gap_before_dispatch_us": 6.707000000000001, "gap_after_dispatch_us": 0.49820000000000003}
  }
}
```

判读（与实验分支 a1ee04044 基线同卡同输入对照，供蓝区按判断顺序参考）：

- **整图实测大幅下降**：AICore L0 均值 262.692 → **239.870 µs（−22.82，−8.7%）**，中位 262.763 → 239.893，逐轮区间 254.1–269.8 → 231.5–248.2（最快轮 −22.5）；Device L0 均值 356.976 → **305.495 µs（−51.48，−14.4%）**。
- **交接优先对照项 t22 收窄最显著**：关键链 gap 12.145 → **8.391 µs（−3.75）**，其中 before_dispatch 11.933 → 8.050（−3.88），after_dispatch 0.212 → 0.341；t9 9.447 → 7.933（before −1.54）；t35 7.793 → 7.205（before −0.62）。三项合计 29.385 → 23.530 µs，before_dispatch 合计 28.310 → 22.275 µs——集成版收益集中在派发前等待，与 #3166/#3180/#3195 的作用面一致。
- **模型侧同向改善**：自由排块下界 202.210 → 197.150 µs（10/10 OPTIMAL，feasible==lower），固定排块 204.390 → 198.730 µs；超界 60.482（29.91%）→ **42.720 µs（21.67%）**；L2 span 265.417 → 246.625、链间隔 65.936 → 51.067 µs。下界本身降 5.06 µs 说明 kernel 执行时长也有变化（集成版重建与 runtime ABI 匹配的 callable），收益不完全来自调度。
- **剩余空间**：gap 仍 92–96% 在 dispatch 之前（t22 8.05/8.39、t9 7.52/7.93、t35 6.71/7.21），下一步热点依旧是派发前等待（依赖可见/取票/参数准备），t22 余量最大；三项 rounds_present 均 10/10。
- 环境说明：trial venv 以 `--system-site-packages` 继承基础环境中的 pypto editable 安装，被脚本自带的 normal/isolated 双模式导入校验拦截（`Expected … found /npu/w00949861/pypto/...`）；黄区在 venv 创建后向其 site-packages 注入 sitecustomize（摘除 skbuild editable finder、清 pypto/a6local 路径，仅作用于该 trial venv），重跑通过，未改动共享环境。实际导入路径：trial 内 `simpler_setup`/`simpler` 均解析到 `swa-integrated-758Yr8/src/`

The SWA replay runs the production percounter scheduler on 54 AIC + 54 AIV.
Each cluster has one AIC and one AIV. The case freezes the 19 kernel registrations and their source dependencies from
the measured SWA replay in `kernels/` and the frozen input and reference tensors in `fixtures/`.

| Component | A6 contract |
| --- | --- |
| Replay | 16 compute tasks. t22 uses 48 C+V blocks with synchronized start. t28 uses 32 C+V blocks. |
| Resources | A 64-block vector task uses up to 54 AIVs in its first wave. The 54-block t25 comparison changes only the recorded block count. |
| Lifecycle | AICPU publishes READY in shared memory. AICore checks the per-worker shutdown gate. Dependency counters use the GM path. |
| SSBUF | Runtime uses bytes 1792–2047. The AIC and AIV callable context slots start at 1920 and 1984. Rebuild the runtime and callable together. |
| Profiling | L0 records whole-run timing. Native percounter L2 records each block's kernel start, return and scheduler finish. |

## 当前目标：A6 上 SWA 动态调度能跑到多少微秒

固定 54 组 1C1V、同一份输入、kernel 和任务图，主测 t25=54。用三组时间回答三个问题。
A5 与 t25=64 的数据留作历史对照。

| 时间 | 怎么得到 | 用它判断什么 |
| --- | --- | --- |
| 当前实测 | A6 原版 percounter，L0 预热 1 轮、正式 10 轮。主指标是 AICore wall 均值，另报中位数、最快一轮和 Device 均值 | 当前方案已经达到的整图性能 |
| 固定每块落核与核上顺序的理想时间 | 每轮 L2 保留 560 条 kernel 的时长、实际 worker 与执行顺序、DAG 前驱、MIX 同块起跑和 `sync_start`。把取任务、通知和派发的耗时设为零，重排开始时间 | 沿用本轮排块决策，执行窗口理论上能压到多短。实际错峰与模型的严格同步规则形成环时，该轮标记为空并统计有效轮数 |
| 自由排块的理想时间 | 同一轮时长和依赖，允许求解器重新安排 block，限制 AIC/AIV 各 54 个。报求解下界、可行解和最优状态 | 固定排块与自由排块之间还有多少空间。求解区间收敛以后再给单一最优值 |

两种模型均按 0.1 µs 向下量化单个 kernel 时长。自由排块模型按核类型计容量，MIX 配对的物理 cluster、访存争用随排布改变的影响均未单独建模。以上极限适用于这张 SWA 图和这批时长。L0 包含整图头尾，L2 模型覆盖 kernel 执行窗口，两者来自独立的十轮采样。

**瓶颈和优化怎么选。** `model/summary.json` 逐轮从最后一个 kernel 沿实际 worker 顺序和图依赖回溯，经空控制节点继续找最近的计算前驱。对每个关键 block，记录最后一个可见前驱或同核上一块返回到本块开始的间隔，并按本块 dispatch 时间拆成前后两段。每轮这条链上的 kernel 时间与间隔之和等于 L2 首核开始至末核返回的跨度。`l2_top_chain_gaps` 按 task 汇总十轮平均贡献，包含同步等待、调度、采样影响以及未记录的工作。蓝区从贡献最大的重复间隔入手，对照 L2 的 claim、dispatch、kernel_start 和 finish，区分同核换块、等前驱和 MIX 集合起跑。若主要空间出在排块，优先查末波落核。按证据选一个 runtime 改动，在同卡同输入下用基线和候选版本交替跑 L0，检查输出、全部样本和对应 L2 间隔是否缩短。

## Build and run

Use Linux, the A6 CANN environment, CCEC, a host C++ compiler, CMake, Ninja and a Python environment with the Simpler build dependencies. From the repository root, prepare PTO-ISA at the revision selected by this checkout.

```bash
git clone https://github.com/hw-native-sys/pto-isa.git build/pto-isa
git -C build/pto-isa checkout --detach "$(cat pto_isa.pin)"
```

With the allocated A6 card in `DEVICE`, run the integrated check. This builds
the runtime, query tool, runner and SWA kernels from this checkout into a new
output directory.

```bash
bash tests/fdwic/a6_dsv41_scheduler/test_a6_swa.sh "$DEVICE"
```

Check the device query, reference output validation and all ten measured rounds.
The default replay uses 64 t25 blocks and 570 executions. For the 54-block
comparison and the scheduling bound, run the following entry point. It builds a
matching callable, captures L0 and L2 and checks all 560 executions per L2 round.

```bash
DEVICE="$DEVICE" bash tests/fdwic/a6_dsv41_scheduler/analysis/run_swa_sync_bound.sh
```

Record the commit, device, CANN and compiler versions, output validation and
AICore/device timing from `test.log`. For the bound include `model/summary.json`
and `model/l0.csv` from the output directory printed at startup. Compare the same
block count, input and profiling level across revisions.

## 蓝区验证与黄区回填

代码基线为 `922b55003`。蓝区在 CANN 9.3.0 下构建了 A5 和 A6 的
percounter runtime、replay、runner 和 SWA callable。A6 的 64-block 与
54-block 版本分别生成 570 和 560 次执行。5 个 C++ 测试目标和 9 项 SWA 离线测试通过。
A5 栈对齐静态扫描完成 7/8 个编译单元，已扫描部分为 0 项发现。
剩余的 `kernel.cpp` 生成的设备 bitcode 在两种 LLVM 读取器中均解析失败。

| 平台与配置 | 预热 / 正式 | 参考输出 | AICore L0 均值 | Device L0 均值 |
| --- | --- | --- | --- | --- |
| 蓝区 A5 Ascend950DT_9582，32C+64V，t25=64 | 1 / 10 | PASS | 164.483 µs | 227.184 µs |
| 黄区 A6，54C+54V，t25=64 | 1 / 10 | 待填 | 待填 | 待填 |
| 黄区 A6，54C+54V，t25=54 | 1 / 10 | 待填 | 待填 | 待填 |

### A5 集成版 SWA 调度下限

在上述 A5 设备 4 上，用同一套 runtime、runner、callable 和 plan 单独采集原生 percounter L2。预热 1 轮，正式 10 轮，参考输出校验通过。每轮匹配 578 次 kernel 执行，t25 发 64 块，t22 发 24 个同步 C+V0+V1 块。

| A5 调度模型 | 十轮均值 | 逐轮范围 |
| --- | ---: | ---: |
| 固定实测 worker 和核上执行顺序 | 120.710 µs | 116.1–126.0 µs |
| 允许重新分核，10/10 轮求得最优解 | 120.260 µs | 116.0–125.7 µs |

两条下限使用每轮实测 kernel 时长，保留依赖和同步启动约束，按 0.1 µs 向下量化。重新分核平均可再缩短 0.450 µs。L0 AICore 实测均值比固定分核模型高 43.773 µs，其中也包含 L0 整图头尾与模型执行窗口的差异。[A5 十轮明细与采集配置](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-a5-comparison.zh-CN.md#集成版-a5-swa-对照基线)

### 已回传的 A6 调度基线与下一步

实验分支 `a6-swa-port` 的代码提交为 `a1ee04044`，结果回填提交为
[`520732d11`](https://github.com/HaoZhang1024/simpler/blob/520732d11/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#a6-sync-bound-feedback)。
设备 0，t25=54，预热 1 轮、正式 10 轮，L0 与 L2 独立采集。黄区修正了共享 venv 的 editable 安装指向旧 checkout 的问题，重新构建 runtime 并用这批产物完成采样。跨版本对照时，记录实际导入的 `simpler`、`simpler_setup` 路径及运行库摘要。

| 已核实的指标 | 实验分支结果 |
| --- | --- |
| L0 AICore 均值 / 中位数 / 最小–最大 | 262.692 / 262.763 / 254.056–269.833 µs |
| 自由排块最优值 | 均值 202.210 µs，逐轮 194.8–212.6 µs。10/10 轮下界与可行解重合 |
| L0 与模型之差 | 60.482 µs，占 L0 的 23.02%，或相对模型高 29.91%。它包含时间窗口、采样和放置约束的差异 |
| 固定实际 worker 和顺序后的理想值 | 204.390 µs，10/10 轮有效；较自由排块平均多 2.180 µs |

实验版 Device L0 为 356.976 µs，L2 首核至末核跨度为 265.417 µs，关键链间隔为 65.936 µs。
t22、t9 和 t35 每轮在关键链上 dispatch 前的间隔贡献分别为 11.933、9.053 和 7.323 µs。
优先核对 t22 的 48-block MIX 同步放行，其次观察同核接块。不同插桩版本之间的整图改善以 L0 对照。

本轮集成版的执行命令和结果填写位置见[黄区本轮执行与回填](#黄区本轮执行与回填)。
