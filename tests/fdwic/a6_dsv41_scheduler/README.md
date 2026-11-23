# A6 percounter SWA

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

黄区在原分支执行一次集成版 t25=54 的 L0/L2，结果统一填在[每日进展顶部](https://github.com/HaoZhang1024/simpler/blob/a6-swa-port/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#当前状态与反馈位置)。脚本固定集成版代码和 PTO-ISA，并自动汇总十轮结果。

| 黄区运行信息 | 回填值 |
| --- | --- |
| 集成提交、SoC、CANN、CCEC 版本 | 待填 |
| L0 AICore 均值 / 中位数 / 最快一轮、Device 均值（µs） | 待填 |
| 固定排块的理想时间均值（µs）、有效轮数 | 待填 |
| L2 首核至末核跨度、关键链间隔总量（十轮均值 µs）、贡献最大的三个 task 及间隔 | 待填，见 `l2_kernel_span_mean_us`、`l2_chain_gap_mean_us`、`l2_top_chain_gaps` |
| t25=54 每轮 kernel 执行数、成功匹配轮数 | 待填，预期 560 次 × 10 轮 |
| `model/summary.json` 中的 `lower_bound_mean_us`、`feasible_mean_us`、`all_optimal` | 待填 |
| 中途失败时的阶段、命令和首条错误 | 按需填写 |
