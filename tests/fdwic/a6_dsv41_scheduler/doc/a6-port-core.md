# A6 percounter 移植 · 核心改动精简版（评审用）

> 完整 29 文件补丁 = 仓库 `doc/a6-diff1`（可直接 git apply，md5 1295923e）。
> 本文档保留 8 个核心运行时文件的完整 diff；其余 21 个文件（平台注册/测试适配/工具/文档）一句话说明。
> 背景：A6 = Ascend960DT_966B7（dav-920r1），54 簇 × (1 AIC + 1 AIV)，对比 A5 36 簇 × (1 AIC + 2 AIV)。

## 其余 21 个文件（一句话）

### 平台注册 / 构建接入（6 个，对应 a6-result.md §3.1）

纯枚举/表驱动追加，a6 平台进入各注册表；A5 路径不变。文件级差异：

- `python/simpler/callable_identity.py`：a6 加入合法平台集合（callable 描述符校验）
- `simpler_setup/build_runtimes.py`：a6 构建目标接入
- `simpler_setup/kernel_compiler.py`：a6 内核编译注册 + dav-920r1 双架构（vec/cube）
- `simpler_setup/platform_info.py`：a6 拓扑信息：54 簇 × 1C1V
- `simpler_setup/runtime_builder.py`：a6 runtime 构建注册
- `simpler_setup/runtime_compiler.py`：a6 runtime 编译注册（host/aicpu/aicore 三端参数）

### ST 测试适配（12 个，对应 §3.12/3.13）

槽位步长平台化（§3.12/3.13）：A5 双 AIV 槽（stride=3）→ A6 单 AIV 槽（stride=2），kernel 落位/收集/断言按平台常量计算；双 AIV case 收集级过滤（TwoVectorSync 等预期排除）。纯测试适配，无运行时语义改动。涉及：

- `tests/st/a5/host_build_graph/graph_execution/kernels/aic/kernel_spmd_mix.cpp`
- `tests/st/a5/host_build_graph/graph_execution/kernels/aiv/kernel_spmd_mix.cpp`
- `tests/st/a5/host_build_graph/graph_execution/kernels/orchestration/graph_execution_mix_spmd_orch.cpp`
- `tests/st/a5/host_build_graph/graph_execution/test_graph_execution.py`
- `tests/st/a5/host_build_graph/graph_execution/test_graph_execution_aic_aiv.py`
- `tests/st/a5/host_build_graph/graph_execution/test_graph_execution_mix_spmd.py`
- `tests/st/a5/host_build_graph/graph_predicated_dispatch/test_graph_predicated_dispatch.py`
- `tests/st/a5/host_build_graph/predicated_dispatch/test_predicated_dispatch.py`
- `tests/st/a5/host_build_graph/spmd_mixed_waves/kernels/orchestration/spmd_mixed_waves_orch.cpp`
- `tests/st/a5/host_build_graph/spmd_mixed_waves/test_spmd_mixed_waves.py`
- `tests/st/a5/host_build_graph/spmd_multiblock_aic/test_spmd_multiblock_aic.py`
- `tests/st/a5/host_build_graph/spmd_releases_spmd/test_spmd_releases_spmd.py`

### 侦察工具（2 个，对应 §3.9，非产品代码）

- `tools/cann-examples/aicore-notification-perf/device-aicpu/consumer.cpp`：黄区侦察工具（§3.9）：复现 A6 0xD0 通知路径死链的探针，与产品代码无关
- `tools/cann-examples/cmake/aicore_reg_mapping.h`：黄区侦察工具：dav-920r1 aicore 寄存器映射头（探针用）

### 交付文档（1 个）

- `tests/fdwic/a6_dsv41_scheduler/doc/a6-result.md`：结果文档自身（另发，不需要 review diff）

## 核心文件完整 diff（8 个）

### 1. `src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp`

AICPU 生命周期（§3.3）：硬编码 3-slot（AIC+AIV0+AIV1）重建为按平台槽位数 2-slot，static_assert 同步平台化

```diff
diff --git a/src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp b/src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp
index 2988b3cea..36fed05cf 100644
--- a/src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp
+++ b/src/a5/runtime/host_build_graph/aicpu/aicore_lifecycle.cpp
@@ -271,8 +271,14 @@ int32_t AicoreLifecycle::post_handshake_init(Runtime *runtime) {
         }
         cluster_workers[cluster][lane] = worker;
     }
-    static_assert(PLATFORM_CORES_PER_BLOCKDIM == 3, "Scheduler selection assumes one AIC and two AIV lanes");
-    static_assert(PLATFORM_AIV_CORES_PER_BLOCKDIM == 2, "Scheduler selection assumes two AIV lanes per cluster");
+    // Lane count must equal the per-block sub-core count (A5: 1 AIC + 2 AIV = 3
+    // lanes; A6 1C1V: 1 AIC + 1 AIV = 2 lanes). The loops above/below are
+    // parameterized by these constants; the scheduler_cluster_coordinate_from_
+    // worker mapping honors AIV_CORES_PER_BLOCKDIM for lane assignment.
+    static_assert(
+        PLATFORM_CORES_PER_BLOCKDIM == PLATFORM_AIC_CORES_PER_BLOCKDIM + PLATFORM_AIV_CORES_PER_BLOCKDIM,
+        "Scheduler lane count must equal AIC + AIV sub-core count per block");
+    static_assert(PLATFORM_AIC_CORES_PER_BLOCKDIM == 1, "Scheduler selection assumes one AIC lane per cluster");
     for (int32_t cluster = 0; cluster < aic_count; ++cluster) {
         for (int32_t lane = 0; lane < PLATFORM_CORES_PER_BLOCKDIM; ++lane) {
             if (cluster_workers[cluster][lane] < 0) {
```

### 2. `src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h`

调度容量常量（§3.2）：36→54 簇、每簇 3→2 worker、SCHEDULER_WORKER_CAPACITY=108；A5 分支编译期常量不变

```diff
diff --git a/src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h b/src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h
index de3c3c0ec..ce14a222b 100644
--- a/src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h
+++ b/src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_types.h
@@ -45,11 +45,15 @@ inline constexpr uint64_t SCHEDULER_STATE_ALIGNMENT = 64;
 // AIC/AIV scalar atomicAdd/ld_dev probes support this separation for layout;
 // it is not a scalar ordering guarantee. See the data-layout contract.
 inline constexpr uint64_t SCHEDULER_GM_ATOMIC_SECTOR_BYTES = 128;
-inline constexpr uint64_t SCHEDULER_WORKER_CAPACITY = 108;
+// Platform-derived worker pool: A5 36 blocks x (1 AIC + 2 AIV) = 108;
+// A6 54 blocks x (1 AIC + 1 AIV) = 108. Same pool size, different shape.
+inline constexpr uint64_t SCHEDULER_WORKER_CAPACITY =
+    static_cast<uint64_t>(PLATFORM_MAX_BLOCKDIM) * (1 + PLATFORM_AIV_CORES_PER_BLOCKDIM);
 inline constexpr uint32_t SCHEDULER_PENDING_SLOT_COUNT = 2;
 enum class SchedulerExecutionEngine : uint32_t { AIC = 0, AIV = 1 };
 inline constexpr uint32_t SCHEDULER_EXECUTION_ENGINE_COUNT = 2;
-inline constexpr uint32_t SCHEDULER_CLUSTER_CAPACITY = SCHEDULER_WORKER_CAPACITY / 3;
+// One cluster per block: A5 36, A6 54.
+inline constexpr uint32_t SCHEDULER_CLUSTER_CAPACITY = static_cast<uint32_t>(PLATFORM_MAX_BLOCKDIM);
 inline constexpr uint32_t SCHEDULER_ACTIVITY_CAPACITY = 1024;
 inline constexpr uint64_t SCHEDULER_PROFILING_TASK_TIMING_LEVEL = 1;
 inline constexpr uint64_t SCHEDULER_PROFILING_SCHEDULE_TIMING_LEVEL = 2;
```

### 3. `src/a5/runtime/percounter/aicore/lane_loop.h`

核心改动（§3.5）：A6 上 0xD0 SPR/MMIO 死链 → GM 原子握手信号（lane ready / 任务 release / teardown，percounter_gm_* 系列）；watchdog 超时语义保留 A5 原版；MIX 场景 golden 全绿即此路径
diff --git a/src/a5/runtime/percounter/aicore/lane_loop.h b/src/a5/runtime/percounter/aicore/lane_loop.h
index 5d37d1e4b..f581e80f9 100644
--- a/src/a5/runtime/percounter/aicore/lane_loop.h
+++ b/src/a5/runtime/percounter/aicore/lane_loop.h
@@ -119,6 +119,10 @@ struct LaneConfig {
     PERCOUNTER_SSBUF PercounterSsbufRegion *ssbuf;
     uint32_t segment_begin[PERCOUNTER_LIST_COUNT];
     uint32_t segment_count[PERCOUNTER_LIST_COUNT];
+    // A6: the EXIT signal rides this gate's GM nonce because the AICore SPR
+    // read of DATA_MAIN_BASE does not observe AICPU MMIO writes on A6. Null
+    // only in unit-test builds that never check for stop.
+    __gm__ AicoreTeardownControl *teardown_gate{nullptr};
 };
 
 inline __aicore__ void percounter_publish_stream_records(ChipSwimlaneAicoreLocalState *profile) {
@@ -342,10 +346,18 @@ inline __aicore__ void percounter_publish_completion(
     if (task.sink) percounter_gm_fetch_add_issue(cfg.counters[task.shell].value, count);
 }
 
-/** True when the lane should stop: EXIT is signalled or some lane has failed. */
+/**
+ * True when the lane should stop: EXIT is signalled or some lane has failed.
+ *
+ * On A6 the AICore SPR read of DATA_MAIN_BASE never observes the AICPU's MMIO
+ * write, so the EXIT check rides the teardown gate's GM nonce instead. The
+ * AICPU publishes that nonce on every shutdown path before the legacy 0xD0
+ * EXIT, so observing it is equivalent.
+ */
 inline __aicore__ bool percounter_should_stop(const LaneConfig &cfg) {
-    return static_cast<uint32_t>(read_reg(RegId::DATA_MAIN_BASE)) == AICORE_EXIT_SIGNAL ||
-           percounter_gm_read(cfg.control->lane_error) != 0;
+    const bool exit_signalled =
+        cfg.teardown_gate != nullptr && ld_dev(&cfg.teardown_gate->exit_request, 0) != 0;
+    return exit_signalled || percounter_gm_read(cfg.control->lane_error) != 0;
 }
 
 inline __aicore__ void percounter_initialize_completion_partition(const LaneConfig &cfg, uint32_t clusters) {
@@ -1571,7 +1583,10 @@ inline __aicore__ void percounter_lane_loop(LaneConfig &cfg, uint64_t timeout_cy
 }
 
 inline __aicore__ AicoreWorkWindow
-run_percounter_lane(__gm__ PercounterControl *control, int block_idx, CoreType core_type) {
+run_percounter_lane(
+    __gm__ PercounterControl *control, int block_idx, CoreType core_type,
+    __gm__ AicoreTeardownControl *teardown_gate
+) {
     const bool is_aic = core_type == CoreType::AIC;
     const uint32_t type_index = is_aic ? 0U : 1U;
     SchedulerClusterCoordinate coordinate{-1, -1};
@@ -1588,6 +1603,7 @@ run_percounter_lane(__gm__ PercounterControl *control, int block_idx, CoreType c
     }
 
     LaneConfig cfg{};
+    cfg.teardown_gate = teardown_gate;
     PercounterScalarTrace scalar{};
     PercounterScalarBinding scalar_binding;
     uint32_t task_count = 0;
@@ -1745,10 +1761,16 @@ inline __aicore__ void percounter_aicore_execute(__gm__ Runtime *runtime, int bl
         SPIN_WAIT_HINT();
     }
     if (signal != AICORE_EXIT_SIGNAL) {
-        // The AICPU published the topology before READY; re-observe the block.
+        // A6: the release gate rides GM (aicpu_ready, written by
+        // publish_partition) because the AICore SPR read of DATA_MAIN_BASE
+        // does not observe the AICPU's MMIO IDLE write on A6. The lane's task
+        // path has its own metadata_ready gate, so releasing on the publication
+        // alone is safe. The legacy 0xD0 EXIT read stays as an early-exit
+        // check: it reads 0 on A6 (never EXIT) and keeps A5 semantics.
         percounter_observe_data_cache(reinterpret_cast<__gm__ void *>(control));
         const uint64_t release_wait_start = get_sys_cnt_aicore();
-        while (signal != AICPU_IDLE_TASK_ID && signal != AICORE_EXIT_SIGNAL) {
+        while (handshake->aicpu_ready != SCHEDULER_RUNTIME_MODE_PERCOUNTER && signal != AICORE_EXIT_SIGNAL) {
+            percounter_observe_cache_line(handshake);
             if (scheduler_watchdog_expired(release_wait_start, get_sys_cnt_aicore(), timeout_cycles)) {
                 percounter_gm_compare_exchange(
                     control->lane_error, uint64_t{0}, static_cast<uint64_t>(SchedulerGraphResult::TIMEOUT)
@@ -1758,11 +1780,12 @@ inline __aicore__ void percounter_aicore_execute(__gm__ Runtime *runtime, int bl
             signal = static_cast<uint32_t>(read_reg(RegId::DATA_MAIN_BASE));
             SPIN_WAIT_HINT();
         }
-        released = signal == AICPU_IDLE_TASK_ID;
+        released = handshake->aicpu_ready == SCHEDULER_RUNTIME_MODE_PERCOUNTER;
     }
     if (released) {
         write_reg(RegId::COND, AICORE_IDLE_VALUE);
-        const auto work_window = run_percounter_lane(control, block_idx, core_type);
+        const auto work_window =
+            run_percounter_lane(control, block_idx, core_type, &runtime->dev.teardown_gates[block_idx]);
         handshake->work_start_cycle = work_window.start_cycle;
         handshake->work_end_cycle = work_window.end_cycle;
         dcci(handshake, SINGLE_CACHE_LINE, CACHELINE_OUT);
@@ -1771,10 +1794,11 @@ inline __aicore__ void percounter_aicore_execute(__gm__ Runtime *runtime, int bl
     // A lane arrives here when its share of the run is done, which can be long
     // before the run ends, or after a local watchdog ended a wait above. The
     // AICPU sends EXIT on every outcome once its supervisor returns, and the
-    // supervisor has its own progress watchdog, so this wait needs none. EXIT
-    // is published only after the return gate is reset, so wait for it before
-    // acknowledging, and complete the preceding GM writes first.
-    wait_for_aicpu_exit_signal();
+    // supervisor has its own progress watchdog, so this wait needs none.
+    // A6: the legacy 0xD0 EXIT wait is dropped; the nonce wait below observes
+    // the GM exit_request the AICPU publishes on every shutdown path before
+    // that EXIT, so it subsumes this gate. Complete the preceding GM writes
+    // first.
     OUT_OF_ORDER_STORE_BARRIER();
     acknowledge_aicore_cond_nonce_and_wait(&runtime->dev.teardown_gates[block_idx]);
 }
