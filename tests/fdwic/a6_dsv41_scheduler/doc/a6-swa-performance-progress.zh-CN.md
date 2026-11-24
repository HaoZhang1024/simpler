# A6 percounter SWA 性能分析与每日进展

## 当前交接 · 2026-11-24

| 负责方 | 当前状态 | 下一步 |
| --- | --- | --- |
| 蓝区 | 已接入 IPC0 命令和 IPC4 回执，构建 A5/A6 目标并检查 A6 产物。IPC 位宽与偏移、启动中止、退出确认、返回放行四组 CPU 测试通过 | 从同卡 GM/IPC 的 L0 样本核对功能和整图时延 |
| 黄区 | 已有设备 0 的集成版产物 | 采集 [SWA L1](#swa-l1)。[GM/IPC 的 L0 对照](#ipc-lifecycle) 有独立的回填位置 |

本页按最近完成的任务在前排列。每节保留可从仓库根目录执行的命令和当批原始 JSON。硬件配置、CntNotify 测量、整图基线和瓶颈结论见 [A6 与 A5 性能对比](a6-a5-comparison.zh-CN.md)。

<a id="swa-l1"></a>

## A6 集成版 SWA 的 L1 核内时间

在 `percounter` 分支根目录加载原 A6 CANN 环境，分配原设备 0 后执行。脚本复用 `build/swa-integrated-758Yr8` 中的 GM runtime、runner、t25=54 计划、callable 和输入，直接采 L1。预热 1 轮、正式 10 轮，逐轮校验输出和每个任务的 AIC/AIV 调用数，每轮合计 560 次。

```bash
git pull --ff-only && DEVICE=0 bash tests/fdwic/a6_dsv41_scheduler/analysis/run_swa_l1.sh
```

**黄区回填位置**　把命令最后一行 JSON 粘到下面。完整的十轮样本在命令打印目录的 `L1/summary.json`。如执行失败，在同一处填首条错误。

```text
待回填 A6 SWA L1 的 feedback.json
```

| 十轮均值 | 如何读数 | A5 对照 |
| --- | --- | ---: |
| `critical_chain_kernel_us` | 从最后结束的调用回溯，每步取本核上一项与图上前驱中最晚结束的调用，只累加链上的 L1 窗口 | 113.697 µs |
| `first_to_last_us` | 从最早开始到最后结束的整段时间 | 166.056 µs |
| `any_kernel_active_us` / `no_kernel_active_us` | 上述时间内，至少一个核在 kernel 窗口内 / 全部核都在窗口外。跨核重叠只计一次 | 144.335 / 21.721 µs |
| `aic_core_us` / `aiv_core_us` | 各 AIC / AIV 的 kernel 时间分别累加，单位为核·µs | 1912.357 / 3336.011 核·µs |

L1 窗口从业务 kernel 调用前计到返回后的写屏障完成，包含调用内部计算、访存和等待。A5 对照取自同一集成基线的设备 4、t25=64、任务 `task_20261124_165608_158205029729`，10 轮均通过数值校验，每轮 578 次调用。两端核内时间差用同一行的 A6 值减 A5 值。

<a id="ipc-lifecycle"></a>

## 当前任务 · A6 percounter 的 IPC 启动与退出

本轮沿用 HBG 实卡确认的 IPC0/IPC4 映射和已有的 CntNotify 测量。待验证的是 percounter 切换后的连续运行、输出正确性，以及相对 GM 版的整图时延。旧 GM 版在同卡运行一组，作为本轮 L0 对照。[寄存器实测与适用范围](a6-a5-comparison.zh-CN.md#寄存器gm-与同步)

进入个人 fork 的 `percounter` 分支根目录，加载原 A6 CANN 环境，使用已分配的设备 0。脚本分别从原版 GM 提交 `be6e23f0e` 和当前 IPC 提交构建 percounter 和 dispatcher，复用原 trial 的 t25=54 计划、runner、callable 和输入。同卡、同工具链，两组各预热 1 轮、正式 10 轮，采无打点 L0。

```bash
git pull --ff-only && DEVICE=0 bash tests/fdwic/a6_dsv41_scheduler/analysis/run_ipc_lifecycle.sh
```

**黄区在这里回填。** 两组都应正常返回、通过数值校验，并且各有 10 个 AICore / Device 样本。将末行 JSON 填入下框，完整结果保存在脚本打印的目录中的 `feedback.json`。若某组失败，填组名（gm 或 ipc）、首条错误和 `run.log` 中最后完成的步骤。`ipc_minus_gm_us` 是整图差值，负数表示 IPC 版更快。

```text
待回填 A6 GM / IPC 的 feedback.json
```

<a id="t22-observe"></a>

## 前一批 · V0 首次观察到输入就绪

加载原 A6 CANN 环境，在 `percounter` 根目录使用已有的 `build/swa-integrated-758Yr8`。脚本复用原 trial 的 Python、PTO-ISA、query、runner、plan、callable 和输入，只构建诊断 runtime。在同一张已分配的卡上依次采原版、诊断版 L2，各预热 1 轮、测 10 轮。

```bash
git pull --ff-only && DEVICE=0 bash tests/fdwic/a6_dsv41_scheduler/analysis/run_t22_observation.sh
```

**黄区在此回填末行 JSON。** 两组都应通过数值校验，各覆盖 480 个 t22 block。诊断版每个 V0 都要满足 C 的 `inputs_ready ≤ fanin_observed_cycles ≤ entry_commit`。脚本检查 worker 身份和事件顺序，重新计算各轮关键链，并在新建目录输出 `feedback.json`。失败时填写运行到哪一组及首条错误。

```text
待回填 A6 control / probe 的 feedback.json
```

**蓝区 A5 实卡对照。** 设备 4，原 runner 和 SWA 输入，任务 `task_20261124_142153_214901118765`。原版与诊断版各检查 10 轮 × 24 块，均通过参考输出校验；两段单位均为 µs。

| V0 时间窗 | 原版总时间 | 诊断版：C 打点至 V0 首次读到 | 诊断版：首次读到至提交 | 诊断版总时间 |
| --- | ---: | ---: | ---: | ---: |
| 全部 block，原始间隔 | 1.312 | 0.930 | 0.397 | 1.327 |
| 各轮关键 block 的 V0，截到关键链窗口 | 1.493 | 0.999 | 0.363 | 1.362 |

A5 整图 L2 kernel 跨度由 166.952 变为 168.764 µs。原版十轮关键 lane 均为 V1；诊断版为 V0 九轮、V1 一轮。先比较 A6 两组的总时间与关键角色，再比较两端诊断版全部 block 的前后两段。前段包含 C 发布、V0 的轮询间隔及观察，后段包含候选选择、顺序检查与提交准备。只有无新增打点的 L0 对照才能验收优化收益。

<a id="t22-entry-roles"></a>

## 已完成 · t22 按 C、V0 核对提交时延

分析脚本 `f8f756c29` 复用设备 0 的集成版 trial。黄区核对了十轮共 480 个 block 的领取者、依赖就绪发布者和各 lane 的实际 worker，返回码为 0。[对比结论](a6-a5-comparison.zh-CN.md#t22-entry-roles)

```bash
git pull --ff-only &&
trial=build/swa-integrated-758Yr8 &&
"$trial/src/.venv/bin/python" tests/fdwic/a6_dsv41_scheduler/analysis/task_sensitivity.py \
  "$trial" --t22-entry-roles
```

```json
{
  "source_commit": "76c7c288b18b6e0f88ac5e9091951dc1d7049d2a",
  "rounds": 10,
  "blocks_checked": 480,
  "critical_roles": ["V0", "V0", "V0", "V0", "V0", "V0", "V0", "V0", "V0", "V0"],
  "critical_lane_us": 1.661,
  "critical_block_us": {
    "C": 0.879,
    "V0": 1.661
  },
  "all_blocks_raw_us": {
    "C": 0.916,
    "V0": 1.469
  },
  "critical_block_raw_us": {
    "C": 0.879,
    "V0": 1.661
  },
  "critical_block_v0_raw_kernel_overlap_us": 0.0
}
```

<a id="t22-release"></a>

## 已完成 · t22 按最后一次提交拆分同步等待

分析脚本 `9662196b6` 读取同一批十轮 L2。每个 block 的 `inputs_ready` 唯一，48 块 × 2 lane × 10 轮共 960 条逐 lane 记录。完整 CSV 留在 trial 内，黄区回填以下 JSON。[对比结论](a6-a5-comparison.zh-CN.md#t22-release)

```bash
git pull --ff-only &&
trial=build/swa-integrated-758Yr8 &&
"$trial/src/.venv/bin/python" tests/fdwic/a6_dsv41_scheduler/analysis/task_sensitivity.py \
  "$trial" --t22-release "$trial/t22-release-lanes.csv" > "$trial/t22-release.json" &&
cat "$trial/t22-release.json"
```

```json
{
  "source_commit": "76c7c288b18b6e0f88ac5e9091951dc1d7049d2a",
  "lane_rows": 960,
  "mean_us": {
    "before_last_commit_us": 2.001,
    "after_last_commit_us": 2.575,
    "first_ready_minus_last_commit_us": 1.725,
    "last_ready_minus_last_commit_us": 3.235
  },
  "last_lane_columns": [
    "block", "lane", "worker", "previous_task", "previous_block",
    "prev_end_to_commit_us", "inputs_ready_to_commit_us"
  ],
  "rounds": [
    {"round": 1, "last_commit_lanes": [[47, 1, 65, 18, 23, 7.07, 1.804]], "critical_block_worker": [12, 78], "before_last_commit_us": 4.288, "after_last_commit_us": 2.735, "first_ready_minus_last_commit_us": 1.682, "last_ready_minus_last_commit_us": 3.193},
    {"round": 2, "last_commit_lanes": [[39, 1, 93, 18, 11, 6.469, 2.167]], "critical_block_worker": [11, 65], "before_last_commit_us": 0.578, "after_last_commit_us": 3.526, "first_ready_minus_last_commit_us": 2.609, "last_ready_minus_last_commit_us": 4.055},
    {"round": 3, "last_commit_lanes": [[47, 0, 3, 18, 3, 7.053, 1.367]], "critical_block_worker": [13, 107], "before_last_commit_us": 1.104, "after_last_commit_us": 2.795, "first_ready_minus_last_commit_us": 1.507, "last_ready_minus_last_commit_us": 3.137},
    {"round": 4, "last_commit_lanes": [[47, 0, 47, 18, 23, 7.254, 1.383]], "critical_block_worker": [18, 56], "before_last_commit_us": 0.621, "after_last_commit_us": 1.816, "first_ready_minus_last_commit_us": 1.726, "last_ready_minus_last_commit_us": 3.121},
    {"round": 5, "last_commit_lanes": [[47, 1, 81, 18, 19, 7.239, 2.121]], "critical_block_worker": [9, 59], "before_last_commit_us": 4.046, "after_last_commit_us": 2.483, "first_ready_minus_last_commit_us": 1.638, "last_ready_minus_last_commit_us": 2.821},
    {"round": 6, "last_commit_lanes": [[47, 0, 15, 18, 11, 6.182, 1.331]], "critical_block_worker": [23, 85], "before_last_commit_us": 0.866, "after_last_commit_us": 2.211, "first_ready_minus_last_commit_us": 1.764, "last_ready_minus_last_commit_us": 3.704},
    {"round": 7, "last_commit_lanes": [[47, 1, 65, 18, 19, 6.621, 1.845]], "critical_block_worker": [11, 85], "before_last_commit_us": 2.804, "after_last_commit_us": 2.425, "first_ready_minus_last_commit_us": 0.962, "last_ready_minus_last_commit_us": 2.502},
    {"round": 8, "last_commit_lanes": [[45, 1, 99, 18, 21, 6.336, 1.94]], "critical_block_worker": [27, 97], "before_last_commit_us": 1.023, "after_last_commit_us": 2.748, "first_ready_minus_last_commit_us": 1.85, "last_ready_minus_last_commit_us": 3.466},
    {"round": 9, "last_commit_lanes": [[43, 1, 73, 18, 29, 6.235, 1.844]], "critical_block_worker": [7, 77], "before_last_commit_us": 3.53, "after_last_commit_us": 3.079, "first_ready_minus_last_commit_us": 1.97, "last_ready_minus_last_commit_us": 3.382},
    {"round": 10, "last_commit_lanes": [[39, 1, 105, 18, 27, 6.158, 1.927]], "critical_block_worker": [11, 77], "before_last_commit_us": 1.15, "after_last_commit_us": 1.928, "first_ready_minus_last_commit_us": 1.538, "last_ready_minus_last_commit_us": 2.966}
  ]
}
```

<a id="offline-l2"></a>

## 已完成 · 十轮 L2 任务收益与派发间隔

分析脚本 `691f09b21` 用 trial 自带的 Python 和 OR-Tools 在 CPU 上运行。十轮 L2 的设备、构建产物、关键链和固定分核结果与保存的模型一致。16 项任务 × 10 轮全部完成，返回码为 0，耗时约 90 秒。[任务结果与计算口径](a6-a5-comparison.zh-CN.md#task-gains)

```bash
git pull --ff-only &&
trial=build/swa-integrated-758Yr8 &&
"$trial/src/.venv/bin/python" tests/fdwic/a6_dsv41_scheduler/analysis/task_sensitivity.py "$trial"
```

```json
{
  "source_commit": "76c7c288b18b6e0f88ac5e9091951dc1d7049d2a",
  "pto_isa_commit": "45435c0624c1d0d056bf38aa60d4f56dc0ef3b6b",
  "baseline_us": 197.15,
  "actual_chain_kernel_us": {
    "8": 10.357,
    "9": 1.241,
    "12": 11.32,
    "16": 10.025,
    "17": 15.523,
    "18": 20.945,
    "19": 0,
    "20": 0,
    "22": 23.575,
    "25": 20.932,
    "28": 30.636,
    "29": 32.12,
    "31": 1.452,
    "33": 0,
    "34": 0,
    "35": 17.433
  },
  "gain_us_if_task_10pct_shorter": {
    "29": [3.2, 3.2],
    "28": [3.1, 3.1],
    "22": [2.44, 2.44],
    "18": [2.13, 2.13],
    "25": [2.13, 2.13],
    "35": [1.74, 1.74],
    "17": [1.57, 1.57],
    "8": [1.15, 1.15],
    "12": [1.14, 1.14],
    "16": [1.05, 1.05],
    "9": [0.12, 0.12],
    "19": [0.0, 0.0],
    "20": [0.0, 0.0],
    "31": [0.0, 0.0],
    "33": [0.0, 0.0],
    "34": [0.0, 0.0]
  },
  "t25_mean_of_round_p50_us": {
    "1": 10.691,
    "2": 20.924
  },
  "t25_last_blocks_by_round": [
    [6], [8], [8], [8], [6], [4], [6], [6], [2], [8]
  ],
  "t22_mean_us": {
    "before_owner_claim_us": 0.0,
    "in_owner_claim_us": 0.094,
    "after_owner_claim_us": 7.956,
    "claim_end_spread_us": 56.529,
    "first_dispatch_minus_last_claim_us": 4.863
  },
  "t22_chain_hits_by_round": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  "t22_detailed_hits_by_round": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  "t22_after_claim_breakdown_us": {
    "to_inputs_ready_us": 1.426,
    "to_entry_commit_us": 1.661,
    "to_ready_us": 4.576,
    "ready_to_dispatch_us": 0.293
  }
}
```

<a id="integrated"></a>

## 已完成 · 集成版 A6 实卡采集

首次下载集成分支

```bash
git clone --single-branch --branch percounter https://github.com/HaoZhang1024/simpler.git simpler-percounter
cd simpler-percounter
```

加载黄区 A6 CANN 和 Python 3.11 环境后，在分配到设备 0 的 checkout 根目录执行。

```bash
DEVICE=0 bash tests/fdwic/a6_dsv41_scheduler/analysis/run_integrated_comparison.sh
```

运行提交 `76c7c288b`，输出目录 `build/swa-integrated-758Yr8/`。设备为 Ascend960DT_966B7，CANN 9.3.0（1022），CCEC clang 15.0.5（2026-10-20）。L0、L2 各预热 1 轮、正式 10 轮，参考输出通过，每轮 560 次 kernel 执行，10 轮模型均求得最优解。黄区在 trial venv 内隔离了共享环境的 editable 安装，复核 `simpler`、`simpler_setup` 均从 trial 的 `src/` 导入。

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

## 构建、复现与验收

A6 工作负载冻结了 19 个 kernel 注册及源码依赖、输入和参考输出。[设备源码](../kernels/) · [冻结数据](../fixtures/)

| Component | A6 contract |
| --- | --- |
| Replay | 16 compute tasks. t22 uses 48 C+V blocks with synchronized start. t28 uses 32 C+V blocks. |
| Resources | A 64-block vector task uses up to 54 AIVs in its first wave. The 54-block t25 comparison changes only the recorded block count. |
| Lifecycle | AICPU publishes READY in shared memory. AICore checks the per-worker shutdown gate. Dependency counters use the GM path. |
| SSBUF | Runtime uses bytes 1792–2047. The AIC and AIV callable context slots start at 1920 and 1984. Rebuild the runtime and callable together. |
| Profiling | L0 records whole-run timing. Native percounter L2 records each block's kernel start, return and scheduler finish. |

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

代码基线为 `922b55003`。蓝区在 CANN 9.3.0 下构建了 A5 和 A6 的
percounter runtime、replay、runner 和 SWA callable。A6 的 64-block 与
54-block 版本分别生成 570 和 560 次执行。5 个 C++ 测试目标和 9 项 SWA 离线测试通过。
A5 栈对齐静态扫描完成 7/8 个编译单元，已扫描部分为 0 项发现。
剩余的 `kernel.cpp` 生成的设备 bitcode 在两种 LLVM 读取器中均解析失败。

早期的 t25 分段、CntNotify 测量及移植执行记录可按批次查阅。[旧分支交接记录](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md)
