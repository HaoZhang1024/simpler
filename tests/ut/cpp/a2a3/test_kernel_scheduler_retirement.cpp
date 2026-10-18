/*
 * Copyright (c) PyPTO Contributors.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 * -----------------------------------------------------------------------------------------------------------
 */

#include <gtest/gtest.h>

#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <thread>

#include "runtime.h"
#include "scheduler/scheduler_context.h"
#include "task_interface/tmr_kernel_control.h"

namespace {
constexpr int kCores = 6;
std::array<std::atomic<int>, kCores> opened{};
std::array<std::atomic<int>, kCores> retired{};
std::array<uint32_t, kCores> conditions{};
std::atomic<int> batches{0};
std::atomic<int> deadlines{0};
std::mutex init_mutex;
std::condition_variable init_cv;
bool pause_open = false;
bool open_paused = false;
bool resume_open = false;
bool silent_first_core = false;

template <typename Context>
auto initialize(Context &context, Runtime *runtime, uint64_t regs, int)
    -> decltype(context.pre_handshake_init(runtime, 3, 2, regs)) {
    return context.pre_handshake_init(runtime, 3, 2, regs);
}
template <typename Context>
auto initialize(Context &context, Runtime *runtime, uint64_t regs, long)
    -> decltype(context.pre_handshake_init(runtime, 3, regs)) {
    return context.pre_handshake_init(runtime, 3, regs);
}

template <typename Context>
auto handshake_owned(Context &context, Runtime *runtime, int owner, int)
    -> decltype(context.handshake_owned_clusters(runtime, owner, 2), bool()) {
    context.handshake_owned_clusters(runtime, owner, 2);
    context.assign_own_clusters(owner);
    context.publish_retirement_group(runtime, owner);
    return true;
}
template <typename Context>
bool handshake_owned(Context &, Runtime *, int, long) {
    return false;
}

template <typename Context>
auto handshake_owned_only(Context &context, Runtime *runtime, int owner, int)
    -> decltype(context.handshake_owned_clusters(runtime, owner, 2), bool()) {
    context.handshake_owned_clusters(runtime, owner, 2);
    return true;
}

template <typename Context>
bool handshake_owned_only(Context &, Runtime *, int, long) {
    return false;
}

template <typename Context>
auto assign_owned(Context &context, Runtime *runtime, int owner, int)
    -> decltype(context.assign_own_clusters(owner), bool()) {
    context.assign_own_clusters(owner);
    context.publish_retirement_group(runtime, owner);
    return true;
}

template <typename Context>
bool assign_owned(Context &, Runtime *, int, long) {
    return false;
}
}  // namespace

uint32_t platform_get_physical_cores_count() { return kCores; }
static uint64_t test_report_epoch = 0;
static int nonce_batches = 0;
extern "C" uint64_t get_platform_run_result_epoch() { return test_report_epoch; }
uint64_t platform_aicore_exit_deadline() { return ++deadlines; }
uint64_t read_reg(uint64_t, RegId) { return AICORE_IDLE_VALUE; }

void platform_init_aicore_regs(uint64_t address) {
    ++opened.at(address - 1);
    std::unique_lock<std::mutex> lock(init_mutex);
    if (pause_open && address == kCores) {
        open_paused = true;
        init_cv.notify_all();
        init_cv.wait(lock, [] {
            return resume_open;
        });
    }
}

int32_t
platform_retire_aicore_current_ack_group(const AicoreExitTarget *targets, size_t count, uint64_t, bool *released) {
    ++batches;
    bool timed_out = false;
    for (size_t i = 0; i < count; ++i) {
        const auto core = targets[i].reg_addr - 1;
        EXPECT_LT(core, kCores);
        if (core >= kCores) continue;
        EXPECT_EQ(opened[core].load(), 1);
        EXPECT_NE(targets[i].teardown, nullptr);
        ++retired[core];
        const bool success = !(silent_first_core && core == 0);
        if (released != nullptr) released[i] = success;
        if (success && targets[i].teardown != nullptr) {
            __atomic_store_n(&targets[i].teardown->post_close_release, AICORE_POST_CLOSE_RELEASE, __ATOMIC_RELEASE);
        }
        timed_out |= !success;
    }
    return timed_out ? -1 : 0;
}

int32_t
platform_retire_cond_nonce_group(const AicoreExitTarget *targets, size_t count, uint64_t deadline, bool *released) {
    ++nonce_batches;
    return platform_retire_aicore_current_ack_group(targets, count, deadline, released);
}

class SchedulerContextTestPeer {
public:
    template <typename Context>
    static auto
    bind_replay_fault(Context &context, Runtime *runtime, const simpler::tmr::TmrReplayAdmission *state, int)
        -> decltype(context.bind_handshakes(runtime->dev.workers, 7, state), bool()) {
        context.bind_handshakes(runtime->dev.workers, 7, state);
        return true;
    }
    template <typename Context>
    static bool bind_replay_fault(Context &, Runtime *, const simpler::tmr::TmrReplayAdmission *, long) {
        return false;
    }
    static LoopAction check_idle(SchedulerContext &context, SharedMemoryHeader *header, Runtime *runtime) {
        return context.check_idle_fatal_error(0, header, runtime);
    }
    static LoopAction check_exit(SchedulerContext &context, SharedMemoryHeader *header, Runtime *runtime) {
        int32_t task_count = 0;
        return context.handle_orchestrator_exit(0, header, runtime, task_count);
    }
    static void completed_with_running_core(SchedulerContext &context, SchedulerState *scheduler) {
        context.sched_ = scheduler;
        context.completed_.store(true, std::memory_order_release);
        context.core_trackers_[0].change_core_state(0);
    }
    static int32_t request_all(SchedulerContext &context, Runtime *runtime) {
        return context.retire_all_cores(runtime);
    }
    static void emergency(SchedulerContext &context, Runtime *runtime) { context.emergency_shutdown(runtime); }
    static bool handshake_failed(const SchedulerContext &context) {
        return context.handshake_failed_.load(std::memory_order_acquire);
    }
    static int32_t request(SchedulerContext &context, Runtime *runtime, const int32_t *ids, int count) {
        return context.retire_cores(runtime, ids, count);
    }
    static void clear_register_address(SchedulerContext &context, int core) {
        context.core_exec_states_[core].reg_addr = 0;
    }
    static void clear_ownership(SchedulerContext &context) {
        context.core_trackers_[0].init(0);
        context.core_trackers_[1].init(0);
    }
    static void force_assignment_failure(SchedulerContext &context) {
        // Fault-injected discovery geometry stays within the allocated tables.
        context.cores_total_num_ = PLATFORM_MAX_CORES;
        context.aicpu_thread_num_ = 2;
        for (int i = 0; i < PLATFORM_MAX_CORES; ++i)
            context.core_type_compact_[i] = static_cast<uint8_t>(CoreType::AIC);
    }
    static void assign(SchedulerContext &context) {
        context.core_trackers_[0].init(1);
        context.core_trackers_[0].set_cluster(0, 0, 2, 3);
        context.core_trackers_[1].init(1);
        context.core_trackers_[1].set_cluster(0, 1, 4, 5);
    }
};

class SchedulerRetirement : public testing::Test {
protected:
    std::unique_ptr<SchedulerContext> context = std::make_unique<SchedulerContext>();
    std::unique_ptr<Runtime> runtime = std::make_unique<Runtime>();
    std::array<uint64_t, kCores> regs{};

    void SetUp() override {
        test_report_epoch = 0;
        nonce_batches = 0;
        batches = 0;
        deadlines = 0;
        pause_open = false;
        open_paused = false;
        resume_open = false;
        silent_first_core = false;
        for (int i = 0; i < kCores; ++i) {
            opened[i] = 0;
            retired[i] = 0;
            regs[i] = i + 1;
        }
        runtime->set_worker_count(kCores);
        ASSERT_EQ(initialize(*context, runtime.get(), reinterpret_cast<uint64_t>(regs.data()), 0), 0);
        for (int i = 0; i < kCores; ++i) {
            auto &handshake = runtime->dev.workers[i];
            handshake.physical_core_id = i;
            handshake.core_type = i < 2 ? CoreType::AIC : CoreType::AIV;
            handshake.aicore_done = 1;
        }
        SchedulerContextTestPeer::assign(*context);
    }
    void handshake() {
        context->handshake_partition(runtime.get(), 0, 1);
        const bool failed = SchedulerContextTestPeer::handshake_failed(*context);
        EXPECT_EQ(context->post_handshake_init(runtime.get()), failed ? -1 : 0);
        context->publish_all_retirement_cores(runtime.get());
    }
    int32_t request_all() { return SchedulerContextTestPeer::request_all(*context, runtime.get()); }
    void emergency() { SchedulerContextTestPeer::emergency(*context, runtime.get()); }
    void expect_once() {
        for (int i = 0; i < kCores; ++i) {
            EXPECT_EQ(retired[i].load(), 1) << "core " << i;
            EXPECT_EQ(
                runtime->get_teardown_gates()[i].post_close_release,
                silent_first_core && i == 0 ? 0U : AICORE_POST_CLOSE_RELEASE
            ) << "core "
              << i;
        }
    }
};

TEST_F(SchedulerRetirement, RequestBeforeHandshakeIsServicedByPublisher) {
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 0);
    handshake();
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(deadlines.load(), 1);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, RequestAfterHandshakeUsesOneBatchAndDeadline) {
    handshake();
    EXPECT_EQ(batches.load(), 0);
    EXPECT_EQ(request_all(), 0);
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(deadlines.load(), 1);
}
TEST_F(SchedulerRetirement, RequestAfterHandshakeWaitsForInitialization) {
    SchedulerContextTestPeer::clear_ownership(*context);
    context->handshake_partition(runtime.get(), 0, 1);
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 0);
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(opened[i].load(), 1);
        EXPECT_EQ(retired[i].load(), 0);
        EXPECT_EQ(runtime->get_teardown_gates()[i].post_close_release, 0U);
    }
    EXPECT_EQ(context->post_handshake_init(runtime.get()), 0);
    context->publish_all_retirement_cores(runtime.get());
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, OwnedHandshakeWaitsForAssignment) {
    SchedulerContextTestPeer::clear_ownership(*context);
    if (!handshake_owned_only(*context, runtime.get(), 0, 0)) {
        GTEST_SKIP() << "HBG has only the partition handshake";
    }
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 0);
    ASSERT_TRUE(assign_owned(*context, runtime.get(), 0, 0));
    const std::array<int, 3> owned = {0, 2, 3};
    for (int core : owned)
        EXPECT_EQ(retired[core].load(), 1);
    EXPECT_EQ(retired[1].load(), 0);
    EXPECT_EQ(retired[4].load(), 0);
    EXPECT_EQ(retired[5].load(), 0);
    EXPECT_EQ(batches.load(), 1);
    ASSERT_TRUE(handshake_owned(*context, runtime.get(), 1, 0));
    expect_once();
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, AssignmentFailurePublishesOpenedWindows) {
    SchedulerContextTestPeer::clear_ownership(*context);
    context->handshake_partition(runtime.get(), 0, 1);
    SchedulerContextTestPeer::force_assignment_failure(*context);
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 0);
    EXPECT_EQ(context->post_handshake_init(runtime.get()), -1);
    context->publish_all_retirement_cores(runtime.get());
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, RequestWhileWindowsOpenBeforeStatePublicationIsRetained) {
    pause_open = true;
    std::thread publisher([&] {
        handshake();
    });
    bool reached;
    {
        std::unique_lock<std::mutex> lock(init_mutex);
        reached = init_cv.wait_for(lock, std::chrono::seconds(5), [] {
            return open_paused;
        });
    }
    EXPECT_TRUE(reached);
    if (reached) {
        EXPECT_EQ(request_all(), 0);
        EXPECT_EQ(batches.load(), 0);
    }
    {
        std::lock_guard<std::mutex> lock(init_mutex);
        resume_open = true;
    }
    init_cv.notify_all();
    publisher.join();
    expect_once();
}
TEST_F(SchedulerRetirement, OwnedClusterPublishersServiceEarlyRequest) {
    EXPECT_EQ(request_all(), 0);
    if (!handshake_owned(*context, runtime.get(), 0, 0)) {
        GTEST_SKIP() << "HBG has only the partition handshake";
    }
    ASSERT_TRUE(handshake_owned(*context, runtime.get(), 1, 0));
    expect_once();
    EXPECT_EQ(batches.load(), 2);
    EXPECT_EQ(deadlines.load(), 2);
}
TEST_F(SchedulerRetirement, OverlappingSetsAndDuplicateIdsRetireOnlyOnce) {
    handshake();
    const int32_t subset[] = {-1, 0, 3, 0, kCores};
    EXPECT_EQ(SchedulerContextTestPeer::request(*context, runtime.get(), subset, 5), 0);
    EXPECT_EQ(request_all(), 0);
    expect_once();
    EXPECT_EQ(batches.load(), 2);
}
TEST_F(SchedulerRetirement, NormalAndEmergencyRetireReadyCoresOnce) {
    handshake();
    std::thread normal([&] {
        context->shutdown(0, runtime.get());
    });
    std::thread fatal([&] {
        emergency();
    });
    context->shutdown(1, runtime.get());
    normal.join();
    fatal.join();
    expect_once();
}
TEST_F(SchedulerRetirement, PartialTimeoutDoesNotReleaseSilentCoreOrRetryClaim) {
    handshake();
    silent_first_core = true;
    EXPECT_EQ(request_all(), -1);
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(deadlines.load(), 1);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, EarlyRequestPreservesPartialTimeout) {
    silent_first_core = true;
    EXPECT_EQ(request_all(), 0);
    handshake();
    expect_once();
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, PublishedZeroAddressDoesNotRetireOrReleaseTarget) {
    handshake();
    // Fault injection after READY exercises the retirement boundary guard.
    SchedulerContextTestPeer::clear_register_address(*context, 3);
    silent_first_core = true;
    EXPECT_EQ(request_all(), -1);
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(retired[i].load(), i == 3 ? 0 : 1);
        EXPECT_EQ(
            runtime->get_teardown_gates()[i].post_close_release, i == 0 || i == 3 ? 0U : AICORE_POST_CLOSE_RELEASE
        );
    }
    EXPECT_EQ(batches.load(), 1);
    EXPECT_EQ(deadlines.load(), 1);
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 1);
}
TEST_F(SchedulerRetirement, EmptyValidatedBatchDoesNotAllocateDeadline) {
    handshake();
    for (int i = 0; i < kCores; ++i)
        SchedulerContextTestPeer::clear_register_address(*context, i);
    EXPECT_EQ(request_all(), 0);
    EXPECT_EQ(batches.load(), 0);
    EXPECT_EQ(deadlines.load(), 0);
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(retired[i].load(), 0);
        EXPECT_EQ(runtime->get_teardown_gates()[i].post_close_release, 0U);
    }
}
TEST_F(SchedulerRetirement, NewGenerationClearsPendingRequestsAndReturnGates) {
    EXPECT_EQ(request_all(), 0);
    for (int i = 0; i < kCores; ++i)
        runtime->get_teardown_gates()[i].post_close_release = AICORE_POST_CLOSE_RELEASE;
    ASSERT_EQ(initialize(*context, runtime.get(), reinterpret_cast<uint64_t>(regs.data()), 0), 0);
    handshake();
    EXPECT_EQ(batches.load(), 0);
    for (int i = 0; i < kCores; ++i)
        EXPECT_EQ(runtime->get_teardown_gates()[i].post_close_release, 0U);
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, InitializationPreservesTheCoreOwnedAck) {
    for (int i = 0; i < kCores; ++i) {
        auto &control = runtime->dev.teardown_gates[i];
        control.post_close_release = AICORE_POST_CLOSE_RELEASE;
        control.exit_request = 9;
        control.exit_ack = 17;
    }
    ASSERT_EQ(initialize(*context, runtime.get(), reinterpret_cast<uint64_t>(regs.data()), 0), 0);
    for (int i = 0; i < kCores; ++i) {
        const auto &control = runtime->dev.teardown_gates[i];
        EXPECT_EQ(control.post_close_release, 0u);
        EXPECT_EQ(control.exit_request, 0u);
        EXPECT_EQ(control.exit_ack, 17u);
    }
}

TEST_F(SchedulerRetirement, PhaseOneAbortNeverPublishesAnUnopenedWindow) {
    emergency();
    context->handshake_partition(runtime.get(), 0, 1);
    context->publish_all_retirement_cores(runtime.get());
    EXPECT_EQ(batches.load(), 0);
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(opened[i].load(), 0);
        EXPECT_EQ(retired[i].load(), 0);
    }
}

TEST_F(SchedulerRetirement, DeviceAbortCancelsUnopenedWorkersWithoutChangingTheirAck) {
    for (int i = 0; i < kCores; ++i)
        runtime->get_teardown_gates()[i].exit_ack = 77;
    emergency();
    emergency();
    context->handshake_partition(runtime.get(), 0, 1);
    context->publish_all_retirement_cores(runtime.get());
    EXPECT_EQ(batches.load(), 0);
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(opened[i].load(), 0);
        EXPECT_EQ(retired[i].load(), 0);
        EXPECT_EQ(runtime->get_teardown_gates()[i].post_close_release, AICORE_PRE_WINDOW_HOST_CANCEL);
        EXPECT_EQ(runtime->get_teardown_gates()[i].exit_ack, 77U);
    }
}

TEST_F(SchedulerRetirement, DeviceAbortSeparatesUnopenedWorkersFromAConcurrentLateOpen) {
    pause_open = true;
    std::thread publisher([&] {
        context->handshake_owned_clusters(runtime.get(), 1, 2);
        context->publish_retirement_group(runtime.get(), 1);
    });
    {
        std::unique_lock<std::mutex> lock(init_mutex);
        ASSERT_TRUE(init_cv.wait_for(lock, std::chrono::seconds(5), [] {
            return open_paused;
        }));
    }
    emergency();
    for (int core : {0, 2, 3}) {
        EXPECT_EQ(opened[core].load(), 0);
        EXPECT_EQ(runtime->get_teardown_gates()[core].post_close_release, AICORE_PRE_WINDOW_HOST_CANCEL);
    }
    for (int core : {1, 4, 5})
        EXPECT_EQ(runtime->get_teardown_gates()[core].post_close_release, 0U);
    {
        std::lock_guard<std::mutex> lock(init_mutex);
        resume_open = true;
    }
    init_cv.notify_all();
    publisher.join();
    EXPECT_EQ(batches.load(), 1);
    for (int core : {1, 4, 5}) {
        EXPECT_EQ(retired[core].load(), 1);
        EXPECT_EQ(runtime->get_teardown_gates()[core].post_close_release, AICORE_POST_CLOSE_RELEASE);
    }
    context->handshake_owned_clusters(runtime.get(), 0, 2);
    for (int core : {0, 2, 3}) {
        EXPECT_EQ(opened[core].load(), 0);
        EXPECT_EQ(retired[core].load(), 0);
    }
}

TEST_F(SchedulerRetirement, CancelAfterLastAbortCheckRetiresLateOpenedMetadata) {
    pause_open = true;
    std::thread publisher([&] {
        handshake();
    });
    {
        std::unique_lock<std::mutex> lock(init_mutex);
        ASSERT_TRUE(init_cv.wait_for(lock, std::chrono::seconds(5), [] {
            return open_paused;
        }));
    }
    emergency();
    EXPECT_EQ(batches.load(), 0);
    {
        std::lock_guard<std::mutex> lock(init_mutex);
        resume_open = true;
    }
    init_cv.notify_all();
    publisher.join();
    expect_once();
    EXPECT_EQ(request_all(), 0);
    expect_once();
}
TEST_F(SchedulerRetirement, InvalidReportBeforeOpenDoesNotFakeReady) {
    runtime->dev.workers[0].physical_core_id = kCores;
    EXPECT_EQ(request_all(), 0);
    handshake();
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(opened[i].load(), 0);
        EXPECT_EQ(retired[i].load(), 0);
    }
}

uint64_t get_platform_pmu_reg_addrs() { return 0; }
int platform_aicpu_affinity_thread_idx() { return 0; }

TEST_F(SchedulerRetirement, StaleStartupIdentityIsRejectedBeforeTaskOrOpen) {
    context->bind_handshakes(runtime->dev.workers, 7);
    for (int i = 0; i < kCores; ++i)
        runtime->dev.workers[i].report_epoch = 5;
    context->handshake_partition(runtime.get(), 0, 1);
    EXPECT_TRUE(SchedulerContextTestPeer::handshake_failed(*context));
    for (int i = 0; i < kCores; ++i) {
        EXPECT_EQ(opened[i].load(), 0);
        EXPECT_EQ(runtime->dev.workers[i].task, 0u);
    }
}

TEST_F(SchedulerRetirement, ReplayFaultStopsAnInitializedSchedulerAndPublishesError) {
    handshake();
    simpler::tmr::TmrReplayAdmission replay{7, 7, 1};
    if (!SchedulerContextTestPeer::bind_replay_fault(*context, runtime.get(), &replay, 0))
        GTEST_SKIP() << "Program HBG has no replay admission";
    SharedMemoryHeader header{};
    EXPECT_EQ(SchedulerContextTestPeer::check_exit(*context, &header, runtime.get()), LoopAction::BREAK_LOOP);
    EXPECT_EQ(header.sched_error_code.load(), SIMPLER_ERROR_INVALID_ARGS);
    EXPECT_EQ(header.orch_error_code.load(), SIMPLER_ERROR_INVALID_ARGS);
    EXPECT_EQ(header.sched_error_thread.load(), 0);
    EXPECT_EQ(header.sched_error_bitmap.load(), 1U);
    EXPECT_TRUE(context->initialization_aborted());
    expect_once();
}

TEST_F(SchedulerRetirement, ReplayFaultStopsIdleSchedulerAndPreservesFirstError) {
    handshake();
    simpler::tmr::TmrReplayAdmission replay{7, 7, 1};
    if (!SchedulerContextTestPeer::bind_replay_fault(*context, runtime.get(), &replay, 0))
        GTEST_SKIP() << "Program HBG has no replay admission";
    SharedMemoryHeader header{};
    header.sched_error_code.store(SIMPLER_ERROR_ASYNC_WAIT_OVERFLOW);
    header.sched_error_thread.store(1);
    header.orch_error_code.store(SIMPLER_ERROR_EXPLICIT_ORCH_FATAL);
    EXPECT_EQ(SchedulerContextTestPeer::check_idle(*context, &header, runtime.get()), LoopAction::BREAK_LOOP);
    EXPECT_EQ(header.sched_error_code.load(), SIMPLER_ERROR_ASYNC_WAIT_OVERFLOW);
    EXPECT_EQ(header.orch_error_code.load(), SIMPLER_ERROR_EXPLICIT_ORCH_FATAL);
    EXPECT_EQ(header.sched_error_thread.load(), 1);
    EXPECT_EQ(header.sched_error_bitmap.load(), 1U);
    expect_once();
    EXPECT_EQ(SchedulerContextTestPeer::check_idle(*context, &header, runtime.get()), LoopAction::BREAK_LOOP);
    expect_once();
}

TEST_F(SchedulerRetirement, HealthyReplayAndProgramKeepScheduling) {
    handshake();
    simpler::tmr::TmrReplayAdmission replay{7, 7, 0};
    if (!SchedulerContextTestPeer::bind_replay_fault(*context, runtime.get(), &replay, 0))
        GTEST_SKIP() << "Program HBG has no replay admission";
    SharedMemoryHeader header{};
    EXPECT_EQ(SchedulerContextTestPeer::check_idle(*context, &header, runtime.get()), LoopAction::NONE);
    EXPECT_EQ(SchedulerContextTestPeer::check_exit(*context, &header, runtime.get()), LoopAction::NONE);
    EXPECT_EQ(header.sched_error_code.load(), SIMPLER_ERROR_NONE);
    EXPECT_EQ(batches.load(), 0);
    ASSERT_TRUE(SchedulerContextTestPeer::bind_replay_fault(*context, runtime.get(), nullptr, 0));
    EXPECT_EQ(SchedulerContextTestPeer::check_idle(*context, &header, runtime.get()), LoopAction::NONE);
    EXPECT_EQ(SchedulerContextTestPeer::check_exit(*context, &header, runtime.get()), LoopAction::NONE);
    EXPECT_EQ(header.sched_error_code.load(), SIMPLER_ERROR_NONE);
    EXPECT_EQ(batches.load(), 0);
}

TEST_F(SchedulerRetirement, MainLoopConsumesReplayFaultEvenAfterCompletionWasPublished) {
    handshake();
    simpler::tmr::TmrReplayAdmission replay{7, 7, 1};
    if (!SchedulerContextTestPeer::bind_replay_fault(*context, runtime.get(), &replay, 0))
        GTEST_SKIP() << "Program HBG has no replay admission";
    SharedMemoryHeader header{};
    auto scheduler = std::make_unique<SchedulerState>();
    scheduler->sm_header = &header;
    // completed_ may publish before workers have returned. An admission failure
    // still has to reach producer waits and retirement on the loop's first pass.
    SchedulerContextTestPeer::completed_with_running_core(*context, scheduler.get());
    EXPECT_EQ(context->resolve_and_dispatch(runtime.get(), 0), 0);
    EXPECT_EQ(header.sched_error_code.load(), SIMPLER_ERROR_INVALID_ARGS);
    EXPECT_EQ(header.orch_error_code.load(), SIMPLER_ERROR_INVALID_ARGS);
    EXPECT_TRUE(context->initialization_aborted());
    expect_once();
}

TEST_F(SchedulerRetirement, OwnedStartupIdentityIsRejectedBeforeTaskOrOpen) {
    context->bind_handshakes(runtime->dev.workers, 7);
    for (int i = 0; i < kCores; ++i)
        runtime->dev.workers[i].report_epoch = 5;
    ASSERT_TRUE(handshake_owned_only(*context, runtime.get(), 0, 0));
    EXPECT_TRUE(SchedulerContextTestPeer::handshake_failed(*context));
    for (int i = 0; i < kCores; ++i)
        EXPECT_EQ(opened[i].load(), 0);
}

TEST_F(SchedulerRetirement, CurrentStartupIdentityOpensNormally) {
    context->bind_handshakes(runtime->dev.workers, 7);
    for (int i = 0; i < kCores; ++i)
        runtime->dev.workers[i].report_epoch = 7;
    handshake();
    for (int i = 0; i < kCores; ++i)
        EXPECT_EQ(opened[i].load(), 1);
}
