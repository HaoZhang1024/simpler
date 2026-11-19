# A6 percounter 移植任务书

更新：2026-11-18 22:10。代码基线：`a6-swa-port` 分支 pin `b921a01b`。
本文件自包含：硬件实测事实、已完成全部代码改动（意图+机制+仓库内相对路径）、验证状态、下一步任务（含验收标准）。
精确 diff 见配套归档 `a6-port-tracked.patch`（已跟踪文件）与 `src-a6-layer.tar.gz`（新增 `src/a6/` 平台层目录）。

蓝区接续说明：已收到[已有文件的补丁](a6-diff)，16 个文件通过 git apply --check。新增 src/a6 平台目录仍需与通过 MIX 的工作树一起交付。[下一轮测试命令](usage.zh-CN.md#黄区接续测试)

## 1. 任务背景

把 simpler 的 percounter 调度运行时移植到 A6（Ascend960DT_966B7，dav-920r1）。A6 平台层（`src/a6/`）已落地，构建链已通，**单-MIX 冒烟已全绿**（`TestPercounterMix` 4 个 case 上板真执行 + golden 校验通过）。剩余：run-entry CLI 适配、其余 9 个测试类验证、SWA 端到端回放、诊断探针清理。

## 2. 硬件实测事实（A6，设备实测，决策依据）

### 2.1 拓扑与参数

| 项           | A5                              | A6                                                           |
| ------------ | ------------------------------- | ------------------------------------------------------------ |
| 每 block 核  | 1 AIC + 2 AIV（3 slot）         | **1 AIC + 1 AIV（2 slot）**                                  |
| MAX_BLOCKDIM | 36                              | **54**（每 die 27 有效，缺陷跳号）                           |
| worker 池    | 108                             | 108（形状不同）                                              |
| cluster 容量 | 36                              | **54**                                                       |
| SSBUF/簇     | 3 KiB                           | **2 KiB**（偏移 ≥2048 写即 errcode 271）                     |
| AICore 映射  | 每 AIC 3 MiB 窗（AIV 子窗在内） | **每 res_id 独立 2 MiB 窗**（70 窗，每 die 35，die 交错；AIV 推断在 +0x100000，同 A5 首偏移） |
| coreid       | —                               | die0: AIC 0..34/AIV 35..69；die1: AIC 70..104/AIV 105..139   |
| MIX 编译     | —                               | `dav-920r1`（cube+vec 双子核，`__DAV_CUBE__`/`__DAV_VEC__`），ELF `e_flags=0xa60000`，`ld -m aicorelinux`；一次 launch 同拉 AIC+AIV |

平台常量同名定义于 `src/a5` / `src/a6` 的 `platform/include/common/platform_config.h`（`PLATFORM_CORES_PER_BLOCKDIM`、`PLATFORM_AIV_CORES_PER_BLOCKDIM`、`PLATFORM_SSBUF_SIZE`、`PLATFORM_MAX_BLOCKDIM` 等），按编译目标 -I 切换。**任何 A5 语义的 3-slot/2-AIV 假设在 A6 都要用这些常量参数化。**

### 2.2 寄存器实测

| 寄存器                                                       | 结论                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `DATA_MAIN_BASE`（0xD0，AIC SPR；MMIO 落点 dmb_offset=0xD0） | **MMIO→SPR 链死**：AICPU 写 + MMIO 回读全窗口一致（IDLE=0x7ffffffd），但 AIC `read_reg(RegId::DATA_MAIN_BASE)` 永远观察不到 → percounter lane 信号已改 GM（见 3.5） |
| COND（0x5108）                                               | 实测关闭（AIC `set_cond` ↔ AICPU MMIO 不通）。探测工具用 `cond_offset=0xFFFFFFFF` GM-only 哨兵跳过 |
| IPC（0x5500/0x5520）                                         | HBG 通路使用，percounter 未用，未验证                        |
| `PROCESS_CP2` / `RES_L2BUFF` / `RES_C2C`                     | halResMap 拒绝（rc=65534/17）；`RES_DBG_ADDR` 4KiB、`RES_HSCB_AICORE` 0x4096B 可映射 |

### 2.3 slot/mask 语义（本次核心根因）

`active_mask` 位编码：bit0=AIC、bit1=AIV0、bit2=AIV1（A5 3-slot 语义）。任务发布（orchestrator submit）把各 lane 的 kernel 写入 slot 的 `kernel_id[lane]`；host 侧 `state.h` 统计时 `is_mix` 用**原始 3-bit mask** 判定，而 `input.active_mask` 从 `descriptor.kernel_id[lane]` 按 `PLATFORM_CORES_PER_BLOCKDIM`（A6=2）个 lane **重建**。两份来源在 A6 上不一致 → build_tables 审计炸。**A6 无 AIV1 槽：双 AIV kernel 任务（mask6/7）物理不可运行**（一个任务同时占两个 AIV lane 的调度语义在 1C1V 下无解；lane 分时多 subtask 属调度器语义级改动，未做）。

## 3. 已完成改动（仓库内相对路径，全部已构建+上板验证，除非注明）

### 3.1 平台注册（python 构建链）

| 文件                                  | 改动                                                         |
| ------------------------------------- | ------------------------------------------------------------ |
| `simpler_setup/platform_info.py`      | `PLATFORM_MAP` 加 `"a6": ("a6", "onboard")`；`ARCHS` 加 `"a6"` |
| `simpler_setup/build_runtimes.py`     | `detect_buildable_platforms` 可建平台列表加 `"a6"`（有交叉编译器+CCEC 时） |
| `simpler_setup/runtime_builder.py`    | `platform_embeds_pto_isa` 集合加 `"a6"`；docstring 更新      |
| `simpler_setup/runtime_compiler.py`   | platform_dir 加 a6→`src/a6/platform/onboard`；新增 `_init_a6()`（镜像 `_init_a5`：CCEC aicore + aarch64 aicpu + host_gxx host，含 pto_isa pinned checkout）；deploy 段 ccu_event_trigger/aicpu_cpu_topo_fallback 拷贝条件扩为 `platform in ("a5","a6")`；错误消息列出 a6 |
| `simpler_setup/kernel_compiler.py`    | 7 处 a6 分支：platform_dir→`src/a6/platform`；toolchain 分组（a6 与 a5 同组 CCEC+aarch64+host_gxx，CCU 仍 a5-only）；两处 arch 映射 a6→`src/a6/runtime`（符号链接到 a5 源）；`get_incore_include_dirs` 追加 `src/a6/runtime`；incore toolchain map `"a6": ToolchainType.CCEC` |
| `python/simpler/callable_identity.py` | `_platform_arch` 加 `if platform == "a6": return "a6"`       |

### 3.2 `src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h`

容量硬编码改平台推导（A5 值不变）：

```cpp
inline constexpr uint64_t SCHEDULER_WORKER_CAPACITY =
    static_cast<uint64_t>(PLATFORM_MAX_BLOCKDIM) * (1 + PLATFORM_AIV_CORES_PER_BLOCKDIM);  // A5 108; A6 108
inline constexpr uint32_t SCHEDULER_CLUSTER_CAPACITY = static_cast<uint32_t>(PLATFORM_MAX_BLOCKDIM);  // A5 36; A6 54
```

修 `A5 percounter: incomplete cluster topology AIC=54 AIV=54`（supervisor.h:88 的 `aic_count > SCHEDULER_CLUSTER_CAPACITY` 拒绝）。

### 3.3 `src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp:271+`

static_assert 去硬编码：

```cpp
// 原: static_assert(PLATFORM_CORES_PER_BLOCKDIM == 3, ...); static_assert(PLATFORM_AIV_CORES_PER_BLOCKDIM == 2, ...);
static_assert(PLATFORM_CORES_PER_BLOCKDIM == PLATFORM_AIC_CORES_PER_BLOCKDIM + PLATFORM_AIV_CORES_PER_BLOCKDIM, ...);
static_assert(PLATFORM_AIC_CORES_PER_BLOCKDIM == 1, ...);
```

### 3.4 `src/a5/runtime/percounter/runtime/scheduler/ssbuf.h`

SSBUF 调度 region 平台化：

```cpp
constexpr uint32_t PERCOUNTER_SSBUF_REGION_OFFSET =
    (PLATFORM_SSBUF_SIZE == 3 * 1024) ? 2 * 1024 : 1792;   // A6: KFC 占 [0,~1748)，136B region 放 [1792,2048)
constexpr uint32_t PERCOUNTER_SSBUF_REGION_SIZE = PLATFORM_SSBUF_SIZE - PERCOUNTER_SSBUF_REGION_OFFSET;
static_assert(PERCOUNTER_SSBUF_REGION_SIZE >= 136, ...);    // PENDING_CAPACITY=1 下限
```

### 3.5 `src/a5/runtime/percounter/aicore/lane_loop.h`（0xD0→GM 信号，A6 可运行的关键）

实测 0xD0 MMIO→SPR 死链后，lane 全部信号改 GM：

1. `LaneConfig` 加 `__gm__ AicoreTeardownControl *teardown_gate{nullptr};`
2. `run_percounter_lane` 加第 4 参数 `teardown_gate`，写进 cfg；调用点（`percounter_aicore_execute`）传 `&runtime->dev.teardown_gates[block_idx]`
3. `percounter_should_stop`：EXIT 判定 `read_reg(DATA_MAIN_BASE)==AICORE_EXIT_SIGNAL` → `cfg.teardown_gate != nullptr && ld_dev(&cfg.teardown_gate->exit_request, 0) != 0`（GM nonce；AICPU 所有 shutdown 路径先于旧 0xD0 EXIT 发布它）
4. release-wait：`while (signal != AICPU_IDLE_TASK_ID && ...)` → `while (handshake->aicpu_ready != SCHEDULER_RUNTIME_MODE_PERCOUNTER && ...)`，循环内加 `percounter_observe_cache_line(handshake)`；`released = (handshake->aicpu_ready == SCHEDULER_RUNTIME_MODE_PERCOUNTER)`。安全性依据：AICPU `publish_partition`（GM，aicpu_executor.cpp:459）先于 `release_partition`（0xD0，:485）；lane 任务路径自带 `metadata_ready` gate（lane_loop.h:728）。旧 0xD0 EXIT 读保留作早期退出（A6 恒 0 无害，A5 语义不变）
5. 删尾部 `wait_for_aicpu_exit_signal()`：`acknowledge_aicore_cond_nonce_and_wait` 已等同一 GM nonce
6. 两处 watchdog 超时加 detail 探针（`A6-VERIFY probe detail=1` ready-wait / `detail=2` release-wait，写 `control->lane_error_claim/task/detail`——已有字段）

A5 兼容性：A5 上 0xD0 链通，GM 判定同样成立（publish 顺序不变），行为等价。

### 3.6 `src/a6/platform/onboard/host/ccu_event_trigger.cmake`

`dav-920r1-vec` → `dav-920r1`（CCU 触发器 MIX 整体编译，e_flags 0xa60000）。

### 3.7 orchestrator aiv1→aiv0 平台感知折叠（mask5 根因修复，**两份同改**）

文件：`src/common/host_build_graph/host/orchestrator.cpp`（**host 链，scene_test ST 实际生效**——日志特征 `record_host_orch_callable ... host_dlopen_count=1`，编进 libhost_runtime.so）与 `src/a5/runtime/tensormap_and_ringbuffer/runtime/orchestrator.cpp`（AICPU 设备链，编译验证、未上板）。

两处 normalize 段同改动（各自加 `#include "common/platform_config.h"`）：

```cpp
if (PLATFORM_AIV_CORES_PER_BLOCKDIM < 2) {      // A6 1C1V，编译期常量分支（A5 走 else）
    if (has_aiv1 && has_aiv0) {                 // 双 AIV kernel：物理不可能，明确报错
        report_fatal(SIMPLER_ERROR_INVALID_ARGS, __FUNCTION__,
            "single-AIV platform: a task cannot enable two AIV kernels at once (aiv0+av1)");
        return TaskOutputTensors{};
    }
    if (has_aiv1 && !has_aiv0) {                // AIV1-only（含 AIC+AIV1 MIX 形态）折到 AIV0
        normalized.aiv0_kernel_id = normalized.aiv1_kernel_id;
        normalized.aiv1_kernel_id = INVALID_KERNEL_ID;
        active_mask = normalized.to_lanes();    // mask 与 slot 同步
    }
} else if (!has_aic && has_aiv1 && !has_aiv0) { // A5 原逻辑原样（A5 有 AIV0↔AIC/AIV1↔AIC 两条通道，MIX 保留 AIV 身份）
    ...原折叠...
}
```

折叠后链路自洽：slot `kernel_id=[MATMUL, MUL, INVALID]` → state.h 重建 `active_mask=3`（MIX）→ `functions[1]`=MUL 地址 → AIC 跑 sub_block_id=0、AIV0 跑 sub_block_id=1 → golden 一致（已验证）。

**警示：scene_test 走 host orchestration（common 版）；只 patch a5 tensormap 版不生效。两份都要改。**

### 3.8 `tests/st/a5/host_build_graph/single_block_mix/test_single_block_mix.py`

```python
"platforms": ["a5sim", "a5"] + (["a6"] if mask in (3, 5) else []),
```

mask6/7（双 AIV）与 `ordinary_mix_interleaved`（偶任务 mask7）、`TestMixKernelRendezvous`（burst256_mask6/7）从 a6 排除；mask3/5 保留。

### 3.9 探测工具（tools/cann-examples，实测基础设施）

- `cmake/aicore_reg_mapping.h`：新增 `InitA6()`（70×2MiB 窗映射、`cond_offset_=0xFFFFFFFF` GM-only 哨兵、`dmb_offset_=0xD0`，注释含完整实测记录）
- `aicore-notification-perf/device-aicpu/consumer.cpp`：`cond_addr==nullptr`（GM-only）时跳过所有 COND MMIO 读写与 COND 采样

### 3.10 诊断探针（`A6-VERIFY` 标记，**合并前必须清除**，见 5.4）

- `src/a6/platform/shared/aicpu/platform_regs.cpp`：`platform_init_aicore_regs` 内 d0 写+回读探针（+unified_log include）
- `src/a5/runtime/percounter/host/region_plan.h`：5 处审计上下文日志（:591 boundary/sync/mix 总审计、:656 sync_index、:662 entries、:688 cursor、:743 segment/ticket）+ unified_log include
- `lane_loop.h` 两处 detail 探针（3.5.6）

### 3.11 未改动但关键的数据流（排查参考）

- `state.h:210-227`（select_percounter_state）：`is_mix`/`subtask_count` 取原始 mask；`input.active_mask` 从 `descriptor.kernel_id[lane]` 重建——**修复选在发布侧折叠（3.7）而非改 state.h**
- `state.h:315-321`：`functions[lane]` 取 `task_metadata.kernel_ids[lane]`；`SchedulerTaskMetadata.kernel_ids[3]` 硬编码 3 槽（scheduler_types.h:202）
- `graph_template.h:104-166`：**Graph 模板 body 任务不走 orchestrator normalize**——从 SubTaskDefinition 解码 `active_mask` 直接分桶（MIX→eligible[1]）。若 Graph 系测试用 mask5/6/7 的模板 body 任务，3.7 的折叠不覆盖该路径（见 5.2）
- AICPU 发布顺序（aicpu_executor.cpp）：`publish_partition`(GM :459) 先于 `release_partition`(0xD0 :485)
### 3.12 Graph/SPMD 系测试平台适配（8 文件）

- `spmd_mixed_waves/kernels/orchestration/spmd_mixed_waves_orch.cpp`：`aiv1_kernel_id` 赋值加 `PLATFORM_AIV_CORES_PER_BLOCKDIM >= 2` 编译期 guard（A6 保持 AIC+AIV0 的 Mix 形态，`MixedKernels` 未赋值字段默认 `INVALID_KERNEL_ID`；与 3.7 折叠互补——发布侧不再制造 aiv1 任务）
- 7 个测试文件 CASES `platforms` 加 `"a6"`：`graph_execution/test_graph_execution.py`、`graph_execution_aic_aiv.py`、`graph_predicated_dispatch.py`、`predicated_dispatch.py`、`spmd_mixed_waves.py`、`spmd_multiblock_aic.py`、`spmd_releases_spmd.py`（后两者的 scale/manual case 同步把 `manual` 列表加 a6）
- `spmd_sync_start_mix_aiv`（TwoVectorSync 的来源）**不加 a6**：其语义需要同一 block 两条 AIV lane 同时驻留（sync_start 协同），A6 1C1V 物理不可用；提交接口按 3.7 报 INVALID_ARGS。该类在 pytest 收集阶段即被平台过滤剔除（框架按 CASES 平台交集 deselect），预期排除。

### 3.13 GraphSpmd 深度适配（4 文件，2026-11-18）

`graph_execution` 的 mix_spmd 场景除 platforms 外还有三处 A5 假设：

- `kernels/aic/kernel_spmd_mix.cpp` 与 `kernels/aiv/kernel_spmd_mix.cpp`：槽位步长硬编码 `SLOTS_PER_BLOCK = 3` 改为 `PLATFORM_CORES_PER_BLOCKDIM`（A5=3 不变，A6=2）。AIC 写 `base+b*S+0`；AIV 写 `base+b*S+1+sub_block_id`（A6 上 AIV0 的 sub_block_id=0，见 lane_loop.h 的 placement 语义）。两平台输出布局分别为 36 簇×3 槽 / 54 簇×2 槽，覆盖同样 108 条 cache line（tensor 尺寸不变）。
- `kernels/orchestration/graph_execution_mix_spmd_orch.cpp`：同 3.12 的 aiv1 guard（AIV0/AIV1 本就共用同一内核源码，折叠不改变语义）
- `test_graph_execution_mix_spmd.py`：`compare_outputs` 不再假设 3 槽/36 簇——槽位数从写入足迹推导（最高写入行 +1 除以簇数）。注意 block 0 的槽位值为 0，`nonzero` 计数会把"写了 0"误当"未写"，不可用作足迹（首版推导即踩此坑）。L4 校验的 `active_mask == 7` 与 lane 枚举同步参数化为 `(1 << slots) - 1`。

### 3.14 run-entry CLI 适配（蓝区提交 `e8fad256d`，已合入基线）

- `tests/fdwic/a6_dsv41_scheduler/prepare.py`：`--platform {a5,a6}`；a6 构建内联执行 plan 转换（t22→48×1C1V、t28→32×1C1V，16 任务/570 执行），转换后 plan 写入 `bundle/plan-rank0.bin`，`build.json` 记录 `plan_sha256`
- `tests/fdwic/a6_dsv41_scheduler/run.py`：`--platform a6 --device <N> --a6-query <query 可执行文件>`；a6 强制 percounter + query 型号校验（`soc_name: Ascend960DT_966B7`）；设 `TASK_DEVICE` 直连设备（production/run.sh 已有路径，绕过 task-submit）；校验 build.json 与 plan 哈希
- `tests/fdwic/dsv41_scheduler/production/CMakeLists.txt`：`DSV41_ARCH` 参数化平台头文件包含路径
## 4. 当前验证状态

测试定义文件：`tests/st/a5/percounter/acquire/test_acquire.py`（下述全部测试类均在此，构建/上板/结果回填由黄区执行，蓝区只管代码）。以下结果均为 2026-11-18 A6 设备 0 上板真执行（pytest passed + 设备日志增量佐证）。

**percounter ST 类（上板真执行+golden）**：

| 测试类                       | 结果     | 说明                                                       |
| ---------------------------- | -------- | ---------------------------------------------------------- |
| TestPercounterMix            | PASS     | 4/4：chain16/burst16 × mask3/mask5（mask5 折叠语义验证）   |
| TestPercounterSpmdAic        | PASS     | 2 自动 case（`aic_block_num_8` / `aiv_block_num_16`）      |
| TestPercounterMixedWaves     | PASS     | 2 自动 case（`waves_4x8` / `waves_4x8_shifted`）           |
| TestPercounterReleasesSpmd   | PASS     |                                                            |
| TestPercounterPredicate      | PASS     |                                                            |
| TestPercounterGraph          | PASS     | `record_then_replay_1d` / `record_then_replay_2d`          |
| TestPercounterGraphPure      | PASS     |                                                            |
| TestPercounterGraphPredicate | PASS     |                                                            |
| TestPercounterGraphSpmd      | PASS     | 全量 54 簇×2 槽 + `partial_sync_2`（适配见 3.13）          |
| TestPercounterTwoVectorSync  | 预期排除 | 收集级平台过滤剔除（双 AIV 同 block，硬件不支持，见 3.12） |

Graph 系 4 类实测未触发 3.11 预警的 graph_template mask6/7 body 任务问题（其 body 任务为 A6 可运行的形态）。

**SWA 端到端回放（DSV4.1，16 任务/570 执行）**：prepare（19 内核编译、plan 转换、宿主解码校验）→ run 链路全通：

- 功能验证（1 warmup + 1 round）：output check PASS，AICore L0 wall 0.271518 ms
- 正式计量（1 warmup + 10 rounds，全 PASS）：**AICore L0 wall 均值 0.265768 ms，Device 均值 0.357712 ms**（对照 A5 基线 percounter AICore 0.185173 ms，A6 约为 1.44×）

**预期排除（非 bug）**：mask6/7、`ordinary_mix_interleaved`、`TestMixKernelRendezvous`、TwoVectorSync（双 AIV，平台过滤）；绕过过滤直接提交会触发 3.7 的 `single-AIV platform...` 报错（SIMPLER_ERROR_INVALID_ARGS）。

**运维备注**：设备偶发 `rtSetDevice` 507033（E39007 设备子进程启动超时，内部超时约 3 分钟），无规律，重试即恢复（本轮上板过程中遇到 2 次，均在重试后通过）；与本仓代码无关。

**未验证**：AICPU 设备链 orchestrator 折叠（当前 ST 全走 host 链）。

**历史报错→根因对照**（已全修复，排查线索）：

| 报错                                                         | 根因                                 | 修复       |
| ------------------------------------------------------------ | ------------------------------------ | ---------- |
| `Unknown platform: a6`（kernel_compiler/runtime_compiler）   | 平台未注册                           | 3.1        |
| `Unknown platform for callable descriptor: a6`               | callable_identity                    | 3.1        |
| `incomplete cluster topology AIC=54 AIV=54`                  | 容量硬编码 36                        | 3.2        |
| static_assert `== 3 / == 2` 编译失败                         | aicore_lifecycle 硬编码              | 3.3        |
| SSBUF 偏移 ≥2048 errcode 271                                 | region 按 A5 3KiB 布局               | 3.4        |
| `lane reported error 10; 0 of 16 blocks resolved`（rc=-100 超时；detail=2 release-wait） | 0xD0 MMIO→SPR 死链                   | 3.5        |
| `order count disagrees (task id=-1, fanin=-1)` + 审计 `segment_cursor=2 vs boundary+lists=18, ticket_interval=1>0` | A5 3-slot 发布 vs A6 2-slot 重建矛盾 | 3.7+3.8    |
| 507015/507018（errcode 65151）                               | 上述问题下游症状                     | 随根因消失 |

## 5. 下一步任务（按优先级）

### 5.1 run-entry CLI 适配——已完成（2026-11-18，蓝区 `e8fad256d`，见 3.14）

- 验收达成：`--platform a6` 全链接受；prepare→run 跑通 SWA 最小场景（1 warmup + 1 round，output check PASS，见 §4）。

### 5.2 其余 9 个测试类上板验证——已完成（2026-11-18，见 §4 结果表）

- 8 类全绿 + TwoVectorSync 预期排除（收集级过滤）。双 AIV case 按 3.8/3.12 模式过滤；GraphSpmd 需要槽位步长平台化（3.13）；Graph 系实测未触发 3.11 预警的模板 body 问题。

### 5.3 三目标 ABI 离线检查（Q6）——待做

- 目标：host/aicpu/aicore 三编译目标的共享结构 sizeof/alignof/offsetof 一致（重点：`SchedulerTaskMetadata`、`PercounterControl`、wire_types.h 各结构、`AicoreTeardownControl`）。
- 方法：各目标编译一个 static_assert/打印程序比对（离线，不需设备）。
- 验收：报告三目标布局一致，或列出差异并修复。

### 5.4 诊断探针清理（合并前置）——待做

- 删除 3.10 全部 `A6-VERIFY` 探针（platform_regs.cpp d0 探针、region_plan.h 5 处审计、lane_loop.h detail 探针及其写入），保留 3.5 的 GM 信号逻辑本体（非探针）。
- 验收：`grep -rn A6-VERIFY src/` 为空；重跑 TestPercounterMix 仍 4/4。

### 5.5 SWA 端到端回放——已完成（2026-11-18，见 §4）

- 验收达成：golden（output check）通过；性能基线产出：AICore L0 wall 均值 0.265768 ms / Device 均值 0.357712 ms（1 warmup + 10 rounds 全 PASS）。

## 6. 代码约束（改动必须遵守）

1. **A5 零回归**：所有平台化改动在 A5 编译目标下常量/行为不变（3.2/3.3/3.4/3.7 均以编译期常量分支实现，保持该模式）。
2. 双 AIV kernel 任务在 A6 的最终态是**明确报错**（3.7 report_fatal），不做静默降级。
3. A5 语义里 AIC+AIV1 MIX 保留 AIV 身份（硬件通道选择），不可在 else 分支改变原行为。

## 7. 2026-11-19 增量（泳道采集 / 蓝区同步 / manifest / 干净目录验收 / 环境清理）

### 7.1 芯片泳道首次采集（A6，L3+L4，填补 a5-results 只采 L0 的空白）

- L3：`production/run.sh … 3 1 1 --runtime=percounter`（run0/run1 均 0 截断）。570 次执行，窗口 434.89µs（dispatch→finish），平均 Exec 14.18µs，Exec/Latency 91%；最重 func_23_x（30.6µs×32）、func_25_z（27.1µs×4）。
- L4：窗口 453.94µs（观察者开销 ~4%），平均 Exec 14.10µs，Exec/Latency 90%；新增 host 阶段记录（submit_task/alloc_tensors/graph_commit/image_stage，`host_phase_records.jsonl`）；dispatch→kernel start 合计 899.41µs、单次最大 6.64µs。
- 归档：原始 records 已 gzip（L3 2.0M / L4 3.2M）+ deps.json 留存 `/npu/z00880344/swa-a6-swimlane{,-l4}`；Chrome trace 副本在黄区本地 `swimlane/`（perfetto 可视化；服务器端大 trace 已删，可由 records 经 `simpler_setup.tools.swimlane_converter` 重生成）。

### 7.2 蓝区推送同步（e8fad256d → 432a637ad，7 commits，纯文档）

- 蓝区入库：`doc/a6-diff1`（=我们 28 文件补丁）、`doc/a6va5-diff`（=4 拆分合集，542 行/20 文件）；改写 `doc/a6-adaptation-tasks.zh-CN.md` 为下一轮计划（§1 源码对齐 / §2 正确性 5.3+5.4 / §3 同版 A5/A6 样本 / §4 差值解释）；README 状态行更新。
- 同步方式：备份 → checkout a6-result.md → ff-merge → 还原本地 a6-result.md（md5 8393211d 保持）。工作树：29 个已跟踪改动 + 未跟踪 `src/a6/`、`doc/src-a6-manifest.md`、`doc/src-a6.sha256`。

### 7.3 src/a6 manifest 交付（蓝区计划 §1 的黄区物料）

- `/npu/z00880344/src-a6-manifest.md` + `src-a6.sha256`（sha256sum -c 格式）：44 文件（36 SAME / 8 MOD / 0 NEW）+ 1 symlink（a6/runtime→../a5/runtime）+ 12 省略清单，与 a6va5-diff 完全对齐；生成工具黄区本地 `tools/gen_src_a6_manifest.py`。NFS 源树复核 0 FAILED。

### 7.4 干净目录验收（蓝区计划 §1）——达成

- 流程：本地克隆 432a637ad → `git apply doc/a6-diff1`（排除 a6-result.md）→ cp src/a6（sha256 -c 0 FAILED）→ `build_runtimes.py --platforms a6 --runtime percounter` → `prepare.py build --platform a6`（pto-isa 83b1b2b5…，与 r001 一致）→ `run.py` SWA 1 warmup + 10 rounds。
- 结果：output check PASS；AICore 0.267034 ms / Device 0.362065 ms，vs r001 基线 0.265768/0.357712 ms（+0.5%/+1.2%，轮间噪声内）。
- 指纹（r001 build.json vs cleanroom summary.json，43 vs 47 个 sha256）：41 项一致——fixture、19/19 kernel 源与 .bin、plan、runner、pto_isa；不一致仅 callable.bin、libreplay.so 及 runtime 4 件（host 侧二进制嵌入构建路径，跨目录重建字节级不同属预期；设备侧产物字节级复现）。a6local 当前 runtime == r001 运行时（4/4），基线未漂移。
- 证据：`/npu/z00880344/cleanroom/`（3 个构建/运行 log + verify.log + runtime-libs.sha256 + swa-out-perf10r/summary.json 等，共 312K）+ 黄区本地 `cleanroom-evidence/`；664M 构建树取证后已删。结果待写入 a6-result.md（随 5.3/5.4 一并更新）。

### 7.5 /npu 环境清理（2026-11-19）

- 删除：cleanroom 构建树 644M、1118 旧备份 ~324K、/tmp 黄区散件（a6build*/a6probe/a6test/a6port-*/iterate.sh/gen_manifest.py 等 ~5.2M）、泳道服务器端大 trace 35M（本地有副本）、NFS 仓库 CTest `Testing/`。
- 保留：a6local 625M（5.4 迭代构建树，收尾后可再删）、venv 502M、swa-a6-build-r001 20M（基线 + native-runner + query）、泳道 records 5.6M、补丁/manifest/1119 备份 ~2.1M、cleanroom 证据 312K。合计 ~1.16G（清理前 ~1.83G）。

### 7.6 NFS v4.2 COPY 挂死与绕行（2026-11-19，运维要点）

- 现象：`build_runtimes.py`（及一切走 `shutil.copy2` → `copy_file_range` 的 staging）在 NFS 仓库 `build/cache → build/lib` 拷贝阶段挂死：线程 `wchan=nfs42_proc_copy`，tmp 文件 0 字节不增长；NFS 导出（100.102.180.181，91% 用量）读写本身正常（dd 实测 47.8 MB/s），仅 v4.2 服务端 COPY 卸载通道挂起。
- 绕行：cache 三端产物已编好时，用 `dd if=… of=…`（read/write 路径）+ `mv` 原子替换手工补拷 6 件产物（percounter 5 件 + dispatcher 1 件，md5 与 cache 一一核对），之后 `RuntimeBuilder.get_binaries(build=False)`（ST/pytest 的默认路径）只读 `build/lib` 不再拷贝，pytest 正常。
- 长任务一律 `setsid nohup … &` 脱离会话执行（ssh_run 超时断连会孤儿化前台脚本：13:33 首次构建即如此，进程纯 sleeping 无子进程，需 kill -9 后重跑）。
- ST 调用备忘：`python -m pytest tests/st/a5/percounter/acquire/test_acquire.py::TestPercounterMix --platform a6 --device 0 --runtime percounter`（venv + `$ASCEND_HOME_PATH/set_env.sh` + `TORCH_DEVICE_BACKEND_AUTOLOAD=0`；类级单节点 `test_run` 内跑全部命中 case，`chip.run.validate` 计数 = case 数）。

### 7.7 L3 调度记录分析（2026-11-19，§4 差值解释）

数据：`swa-a6-swimlane/percounter/rank0/run1/chip_swimlane_records.json.gz`（L3 权威 records，570 exec，1GHz 时钟；本地 `swimlane/` + 分析脚本 `analyze_l3_records2.py`）。记录语义：`[worker(0..53=AIC/54..107=AIV), pc任务号, 序号, start, end, …]`；pc 任务号与 `source-task-map.txt` 对齐（src t9/t22/t25/t28/t35 = pc1/pc14/pc17/pc20/pc27）。

**窗口结构**（仪器化窗口 434.31µs；对照生产 AICore wall 均值 265.77µs，泳道开销系数 ≈1.63×）：

- 16 个 pc 任务组按依赖排成 ~10 个串行阶段：**阶段跨度合计 335.9µs + 阶段间空隙 98.4µs（占窗口 22.7%）**。最大空隙在 pc14 前 38.7µs，其余 pc10 前 14.8µs、pc20 前 15.2µs、pc17 前 9.4µs。
- 关键组（span/busy/单块均值）：pc14(src22, 48blk MIX 96 exec) 34.6µs/2168.9µs/22.6µs；pc20(src28, 32blk MIX) 44.4µs/1494.7µs/23.4µs；pc21(32blk AIC GEMM) 41.8µs/980.4µs/30.6µs；pc17(src25, 64blk AIV) 42.5µs/703.8µs/11.0µs；pc27(src35, 64blk AIV) 32.8µs/578.5µs/9.0µs；pc10(32blk MIX) 38.1µs/939.9µs/14.7µs；pc1(src9, 80blk AIV 微元) 80×0.59µs；pc25(4blk AIC 大 GEMM) 4×27.1µs 窗口首段。
- **利用率极低**：AIC 均值 16.1%、AIV 均值 18.4%（最忙单 worker 24%/28%）——瓶颈是依赖链而非核数；每阶段并行度由该任务 block_num 决定（多数 ≤64），108 worker 大部分时间空闲。

蓝区复核：A5 的 t22 是 24 个同步 1C2V block，实测 72 段落在 72 个不同核上。下列“双波收益”和局部 L0 折算已撤回，保留下文作为现场分析历史。当前依据与提取任务见[A5/A6 L4 对照](swa-l4-comparison.zh-CN.md)。

**现场初步估算（待同口径复核）**（生产 wall 0.1852→0.2658ms，+80µs）：

1. **向量波次退化（量化，约 +32µs 生产折算）**：>54 块的 AIV 任务在 A6 54 AIV 上翻倍波次——pc17/pc27 各 64 块（A6 1.19 波→2 波，span 42.5/32.8µs；A5 72 AIV 0.89 波→1 波，预计 ~11-13µs/块单波）各 +~20µs 仪器化；pc1 80 块（1.48 波 vs 1.11 波）单块 0.59µs 影响可忽略。合计仪器化 +~53µs × 0.61 ≈ **+32µs 生产折算**。此即计划中 "t9/t25/t35 80/64/64 vector blocks" 项。
2. **MIX 阶段反向受益（约 −12µs 折算）**：A6 54 簇 ≥ 各 MIX 任务块数（pc14 48 块 A6 单波 vs A5 36 簇 1.33 波双波，省 ~20µs 仪器化）；pc10/pc20 同理小幅受益。MIX 单块 AIC+AIV 子任务在两平台等量（kernel_ids 第 3 槽 -1，A5 也不用 AIV1）。
3. **AIC GEMM 中性**：pc21 32 块在 36/54 AIC 上均单波；单块 30.6µs（fp32 M80×K8192×N5120，32 块合计 ~109 TFLOPS）。
4. **残差 ~+60µs 生产折算未闭合**（1+2 净 +20µs 不足以解释 +80µs）：候选为 (a) dav-920r1 vs dav-3510 单块向量/立方效率差（无同版 A5 records 无法对比）；(b) 阶段间空隙 98.4µs 仪器化 / ~60µs 折算中 GM claim/observe 轮询开销的平台差；(c) A6 SSBUF 区域缩至 256B（3.4）的换入换出增多。**建议**：蓝区在同版 bundle 下补采 A5 L3 records 即可精确闭合（A5 设备在同事环境，黄区无权限）。

**给蓝区的优化线索**（非本 port 范围）：窗口为链式非核式——最大杠杆是压缩阶段间空隙（98.4µs 仪器化，pc14 前单点 38.7µs：fanin 计数 + claim 轮询粒度/退避可调）；次为向量任务 block_num 对 54 AIV 取整（pc17/pc27 恰 64>54 触发双波）。

### 7.8 交付文档 + 交付归档刷新（2026-11-19 收尾）

- **a6-result.md**（蓝区交付文档）：5.3/5.4 改已完成态（含方法与结果数字）；§4 增 5.4 回归注记 + 干净目录验收注记；新增 §7（7.1 干净目录验收 / 7.2 ABI+探针清理 / 7.3 泳道 L3 分析 / 7.4 遗留与建议——AICPU 设备链折叠、PMU 占位、A5 L3 采样建议）。已回写 NFS 仓库。
- **全部交付归档再生成**（脚本 `/npu/z00880344/regen_archives.sh` + `split_a6va5.py`，工具 `tools/gen_src_a6_manifest.py` 同步到服务器）：
  - `a6-port-tracked.patch`：29 文件（28 port + a6-result.md），md5 `1295923ec72bf38bd271f5f7b3b6ba7b`；本地已拉回 `D:\A6-PORT\`。
  - `a6-new-files.patch`：45（44 文件 + runtime symlink），md5 `6aacdb561e420ca4f0e0aa279db49aab`；`a6-full-changeset.patch` = 两者拼接。
  - `a6-vs-a5-platform.patch`：20 段（= `git diff --no-index a5/platform a6/platform`），md5 `79a87cfa419ae6ff486d9d1c0b0daa03`；分片 `a6-a5-1-config`(2)/`-2-regs`(4)/`-3-build`(2)/`-4-sim-drop`(12 桩版)+`.full`(12 全量) 再生成。
  - `src-a6-layer.tar.gz`：59 条目，md5 `5017bd03375fcee581b7ac7f2bf58e27`；`src-a6-manifest.md`+`src-a6.sha256`：44 文件（36 SAME/8 MOD/0 NEW）+1 symlink+12 省略，`sha256sum -c` 44/44 OK。
  - doc 副本同步：`doc/a6-diff1`（=tracked patch）、`doc/a6va5-diff`（配对全量+sim 桩）、`doc/src-a6-manifest.md`、`doc/src-a6.sha256`。
- 最终工作树：31 个已跟踪改动（28 port + a6-result.md + a6-diff1 + a6va5-diff）+ 未跟踪 `src/a6/`、doc manifest/sha256——待下次蓝区同步提交。`a6local/`（625M 构建树）保留未删（如需回收可删）。

### 7.9 黄区本地目录精简（2026-11-19）

- D:\A6-PORT 清理：删除根目录 10 个过期归档（a6-a5-1..4/full-changeset/new-files/vs-a5/tar/manifest/sha256，均为 09:2x 过期版本，服务器有 14:5x 现行版）、doc_* 副本与 run.py、gitrepo（117M 旧克隆）、downloads（154M 早期传输包）、src-a6-layer（过期解包）、a6port/cann-examples/scripts/probe（早期工作副本）；remote\ 仅留 a5-results 两份并入 colleague\。
- 本地保留：A6-PORT-LOG.md、a6-port-tracked.patch（现行 md5 1295923e…）、RUNBOOK/PITFALLS/ENV_INFO/interface-answers/PROGRESS 参考、tools\（ssh_run + 生成工具源）、swimlane\（L3/L4 数据+分析）、cleanroom-evidence\、abi-check\（5.3/5.4 工具+证据）、colleague\。
- 蓝区同步不依赖本地任何文件：仓库工作树即全部交付（见 §7.8）
### 7.10 A5 L4 对照分析（2026-11-19，§4 差值解释收口）

- 数据来源：蓝区入库 5 commits（432a637ad → 564902a2b，fetch 未合并），A5 L4 归档 `tests/fdwic/a6_dsv41_scheduler/results/2026-11-19-a5-percounter-l4/`（records 1.7MB + kernel-intervals.csv 578 行 + README + source-task-map）；服务器导出 `/npu/z00880344/a5-l4/`，CSV 拉回本地 `swimlane\`。A6 侧为同级公平对比补采 L4 records（`swa-a6-swimlane-l4`，本地 `swimlane\chip_swimlane_records-L4.json.gz`）。分析脚本 `swimlane/compare_a5_a6.py` + `compare_a5_a6_detail.py`。
- A5 采集条件（归档 README）：同事环境 A5 dev card 1，runtime 26b0511f3，SWA a9046d203，PTO-ISA 83b1b2b5（**与 A6 同版**），DFX+ORCH+SCHED，L4，0 warmup + 1 round，output check PASS。CSV 语义：`core_id, source_task_id, start_us, end_us`（原始 SWA 任务号，零点 = 首 kernel 起始）。
- **A5 拓扑修正**：本次 A5 运行实际 **96 核 = 32 AIC + 64 AIV（32 簇 × 1C2V）**，非旧记录的 36 簇/108 核。证据：core 推断（AIC 任务 t16/t19/t29/t33 恰落 32 个不同核，与 64 个 AIV 核零重叠）+ 归档 README "96 个实际执行 kernel 的 core ID" + 用户确认（"是32+64"）。§7.7 第 1 条的波次前提随之修正（A5 AIV 为 64 非 72），结论方向不变。

**窗口对比（L4 同级，仪器化）**：A5 321.00µs vs A6 453.49µs → **+132.5µs**。仪器化/生产比 A5 1.734 / A6 1.707，折算系数 ~0.577；+132.5 × 0.577 ≈ +76.5µs ≈ 生产差 +80µs（AICore 0.1852→0.2658ms）→ **仪器化窗口解释生产差的 ~96%，归因闭合**。阶段结构两边完全一致（16 任务同序）。

**分项**：

1. **单 kernel 慢化（主因，仪器化 ~+75-85µs）**：中等多块任务单次执行普遍 1.2-1.7× 慢——AIV：t22 1.77、t18 1.73、t25 1.67、t17 1.68、t20 1.40、t35 1.26、t8/t31 1.20；AIC：t22 1.65、t18 1.53、t16 1.49、t28 1.44、t33 1.42、t19 1.15。**大 GEMM t29 0.96×、微元 t9 0.96×、t12 1.03× 不变**。模式 = kernel 越大越不受影响 → 指向 A6 每块/每 kernel 固定成本（GM claim/observe 信号路径轮询、SSBUF 256B 区域换入换出 3.4），大 kernel 摊薄固定开销。
2. **波次退化（+~20µs）**：仅 t25/t35 翻转（64 块：A5 64 AIV=1 波 → A6 54 AIV=2 波，波内单块时长两边相同：t25 10.98/11.02µs、t35 9.06µs）；t9 80 块两边均 2 波。A6 双波批间空隙中位 ~13.7-13.9µs（A5 t9 为 11.2µs）。
3. **阶段间空隙（+17.5µs）**：A5 85.8µs（26.7%）vs A6 103.3µs（22.8%）；最大增量在 t22 前（+11.1µs）。
4. **散布/拖尾（~+15µs）**：t29 单块不变但 span 34.7→44.1µs（max 33.96→38.41、尾 4.3→14.7µs）；t9 span +6.3µs 同类。

**MIX 分型时长**（均值 µs，AIC/AIV 分列）：t18 AIC 13.45→20.58、AIV 5.00→8.66；t22 AIC 13.46→22.27（块 24→48：1C2V→1C1V 折叠致 AIC 数翻倍）、AIV 13.00→23.02；t28 AIC 14.20→20.48、AIV 20.04→26.06（AIV 数 64→32，单 AIV 负担 2×）。busy 总量：A5 6.12ms/96 核 vs A6 8.04ms/108 核（+31%）。

**给蓝区的优化方向（按杠杆排序）**：① 单 kernel 固定开销（GM 信号 claim/observe 轮询粒度/退避、SSBUF 256B 换入换出）——覆盖全部中等任务，最大杠杆；② t25/t35 的 block_num 对 54 AIV 取整（消除双波各 +~20µs 仪器化）；③ t22 前空隙（fanin 计数 + 轮询粒度）。t29 GEMM 计算本身无退化，拖尾属调度散布
