#test here
# A6 percounter 移植任务书

更新：2026-11-18 22:10。代码基线：`a6-swa-port` 分支 pin `b921a01b`。
本文件自包含：硬件实测事实、已完成全部代码改动（意图+机制+仓库内相对路径）、验证状态、下一步任务（含验收标准）。
精确 diff 见配套归档 `a6-port-tracked.patch`（已跟踪文件）与 `src-a6-layer.tar.gz`（新增 `src/a6/` 平台层目录）。

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

## 4. 当前验证状态

测试定义文件：`tests/st/a5/percounter/acquire/test_acquire.py`（下述全部测试类均在此，构建/上板/结果回填由黄区执行，蓝区只管代码）。

**通过（上板真执行+golden）**：`TestPercounterMix` 4/4——`chain16_mask3` / `chain16_mask5` / `burst16_mask3` / `burst16_mask5`。mask5 折叠语义（AIC+MUL@AIV0）结果与 golden 一致。

**预期排除（非 bug）**：mask6/7、`ordinary_mix_interleaved`、`TestMixKernelRendezvous`（双 AIV，平台过滤）；绕过过滤直接提交会触发 3.7 的 `single-AIV platform...` 报错（SIMPLER_ERROR_INVALID_ARGS）。

**未验证**：`test_acquire.py` 其余 9 类（SpmdAic/MixedWaves/ReleasesSpmd/TwoVectorSync/Graph/GraphPure/GraphSpmd/Predicate/GraphPredicate）；AICPU 设备链 orchestrator 折叠（当前 ST 全走 host 链）。

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

### 5.1 run-entry CLI 适配

- 目标：`prepare.py` / `run.py` 接受 `--platform a6`（run.py:85-86 目前硬检查 a5 并报错）；按 3.1 的平台注册模式补全 CLI 路径。A6 无 task-submit 提交通道（ST pytest 路径绕过），CLI 只需支持已有路径。
- 验收：`--platform a6` 不再报 Unknown/unsupported；prepare→run 链跑通一个最小场景。

### 5.2 其余 9 个测试类上板验证

- 逐类跑 `TestPercounterSpmdAic` 等 9 类（见 §4 命令形态）。
- 预期问题及处理模式：
  - 双 AIV/3-slot 的 case → 按 3.8 模式做 CASES platforms 过滤（`+ (["a6"] if mask in (单AIV集合) else [])`）
  - **Graph 系类**（TestPercounterGraph/Pure/Spmd/Predicate/GraphPredicate）注意：模板 body 任务不经 3.7 折叠（见 3.11）——若其 CASES 含 bit2 mask 的 body 任务需另行处理（在 `read_graph_template`/`build_graph_template` 入口做同样的平台折叠，或测试过滤）
  - 新报错按 §4 对照表思路：先在 fail 路径加日志定位（参考 3.10 手法），再定根因
- 验收：9 类在 a6 上全绿或明确过滤（每类给出通过/过滤清单）。

### 5.3 三目标 ABI 离线检查（Q6）

- 目标：host/aicpu/aicore 三编译目标的共享结构 sizeof/alignof/offsetof 一致（重点：`SchedulerTaskMetadata`、`PercounterControl`、wire_types.h 各结构、`AicoreTeardownControl`）。
- 方法：各目标编译一个 static_assert/打印程序比对（离线，不需设备）。
- 验收：报告三目标布局一致，或列出差异并修复。

### 5.4 诊断探针清理（合并前置）

- 删除 3.10 全部 `A6-VERIFY` 探针（platform_regs.cpp d0 探针、region_plan.h 5 处审计、lane_loop.h detail 探针及其写入），保留 3.5 的 GM 信号逻辑本体（非探针）。
- 验收：`grep -rn A6-VERIFY src/` 为空；重跑 TestPercounterMix 仍 4/4。

### 5.5 SWA 端到端回放

- DSV4.1 场景（16 任务/570 实例/30 buffer）在 a6 percounter 上回放+性能采集。
- 验收：golden 通过，产出性能基线数据。

## 6. 代码约束（改动必须遵守）

1. **A5 零回归**：所有平台化改动在 A5 编译目标下常量/行为不变（3.2/3.3/3.4/3.7 均以编译期常量分支实现，保持该模式）。
2. 双 AIV kernel 任务在 A6 的最终态是**明确报错**（3.7 report_fatal），不做静默降级。
3. A5 语义里 AIC+AIV1 MIX 保留 AIV 身份（硬件通道选择），不可在 else 分支改变原行为。
