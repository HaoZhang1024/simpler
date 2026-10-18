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
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

#include "aicore_lifecycle.h"
#include "aicpu/aicpu_device_config.h"
#include "aicpu/device_run_result_base_aicpu.h"
#include "aicpu/platform_regs.h"
#include "aicpu/pmu_collector_aicpu.h"
#include "runtime.h"
#include "scheduler/scheduler_context.h"

// The register-layer tests exercise the real ACK, close, read-back, drain and
// release sequence. This seam verifies that both HBG owners pass the real per-core
// gate to that protocol, including their failure and overlapping-exit paths.
namespace {
struct RetireCall {
    std::vector<uint64_t> addrs;
    std::vector<AicoreTeardownControl *> gates;
    uint64_t deadline;
};

std::vector<RetireCall> retire_calls;
std::vector<uint64_t> exit_signals;
int32_t retirement_result = 0;
std::atomic<uint64_t> deadline_calls{0};
bool pmu_enabled = false;
bool mixed_release = false;
std::vector<int> pmu_stopped;
std::mutex retire_mutex;
}  // namespace

uint64_t platform_aicore_exit_deadline() { return 1000 + ++deadline_calls; }

int32_t platform_retire_aicore_group(const AicoreExitTarget *targets, size_t count, uint64_t deadline, bool *released) {
    RetireCall call;
    call.deadline = deadline;
    for (size_t i = 0; i < count; ++i) {
        call.addrs.push_back(targets[i].reg_addr);
        call.gates.push_back(targets[i].teardown);
        const bool closed = retirement_result == 0 || (mixed_release && i == 0);
        if (closed && targets[i].before_release != nullptr) {
            EXPECT_EQ(targets[i].teardown->post_close_release, 0u);
            targets[i].before_release(targets[i].release_context);
        }
        if (released != nullptr) released[i] = closed;
    }
    {
        std::lock_guard<std::mutex> lock(retire_mutex);
        retire_calls.push_back(std::move(call));
    }
    return retirement_result;
}

void platform_signal_aicore_exit(uint64_t reg_addr) { exit_signals.push_back(reg_addr); }
void platform_init_aicore_regs(uint64_t) {}
uint32_t platform_get_physical_cores_count() { return 3; }
void write_reg(uint64_t, RegId, uint64_t) {}
extern "C" bool is_dump_args_enabled() { return false; }
extern "C" bool is_pmu_enabled() { return pmu_enabled; }
void pmu_aicpu_init(const uint32_t *, int) {}
void pmu_aicpu_finalize(const int *ids, int count) { pmu_stopped.insert(pmu_stopped.end(), ids, ids + count); }
void pmu_aicpu_flush_buffers(int, const int *, int) {}

class SchedulerContextTestPeer {
public:
    static void seed(SchedulerContext &context, const std::array<uint64_t, 3> &addrs) {
        context.cores_total_num_ = 3;
        context.core_trackers_[0].init(1);
        context.core_trackers_[0].set_cluster(0, 0, 1, 2);
        for (int i = 0; i < 3; ++i) {
            context.core_exec_states_[i].reg_addr = addrs[i];
            context.retirement_state_[i] = SchedulerContext::RETIREMENT_READY;
        }
    }
    static void emergency(SchedulerContext &context, Runtime *runtime) { context.emergency_shutdown(runtime); }
};

class AicoreLifecycleTestPeer {
public:
    static void signal_in_progress(AicoreLifecycle &lifecycle, int core) {
        lifecycle.exit_state_[core].store(AicoreLifecycle::ExitState::SIGNALING);
    }
    static void mark_pmu_initialized(AicoreLifecycle &lifecycle) { lifecycle.pmu_initialized_.store(true); }
    static void set_thread_count(AicoreLifecycle &lifecycle, int count) { lifecycle.aicpu_thread_num_ = count; }
    static void seed(AicoreLifecycle &lifecycle, const std::array<uint64_t, 3> &addrs) {
        lifecycle.core_count_ = 3;
        lifecycle.aicpu_thread_num_ = 1;
        for (int i = 0; i < 3; ++i)
            lifecycle.cores_[i].reg_addr = addrs[i];
    }
};

namespace {
constexpr std::array<uint64_t, 3> kAddrs = {0x1000, 0x2000, 0x3000};

class HbgRetirementWiring : public testing::Test {
protected:
    void SetUp() override {
        retire_calls.clear();
        exit_signals.clear();
        retirement_result = 0;
        deadline_calls = 0;
        pmu_enabled = false;
        mixed_release = false;
        pmu_stopped.clear();
        set_scheduler_timeout_ms(0);
        set_platform_run_result(0, 0);
    }

    static void expect_group(const Runtime &runtime) {
        ASSERT_EQ(retire_calls.size(), 1u);
        EXPECT_EQ(retire_calls[0].addrs, std::vector<uint64_t>(kAddrs.begin(), kAddrs.end()));
        for (size_t i = 0; i < kAddrs.size(); ++i)
            EXPECT_EQ(retire_calls[0].gates[i], &runtime.dev.teardown_gates[i]);
    }
};

TEST_F(HbgRetirementWiring, SchedulerNormalShutdownClaimsEachCoreBeforeEmergency) {
    auto runtime = std::make_unique<Runtime>();
    auto scheduler = std::make_unique<SchedulerContext>();
    SchedulerContextTestPeer::seed(*scheduler, kAddrs);

    EXPECT_EQ(scheduler->shutdown(runtime.get(), 0), 0);
    SchedulerContextTestPeer::emergency(*scheduler, runtime.get());
    expect_group(*runtime);
}

TEST_F(HbgRetirementWiring, SchedulerClearsStaleGatesBeforeHandshake) {
    auto runtime = std::make_unique<Runtime>();
    runtime->set_worker_count(3);
    for (auto &gate : runtime->dev.teardown_gates)
        gate.post_close_release = AICORE_POST_CLOSE_RELEASE;
    auto scheduler = std::make_unique<SchedulerContext>();

    ASSERT_EQ(scheduler->pre_handshake_init(runtime.get(), 1, 0), 0);
    for (size_t i = 0; i < kAddrs.size(); ++i)
        EXPECT_EQ(runtime->dev.teardown_gates[i].post_close_release, 0u);
}

TEST_F(HbgRetirementWiring, SchedulerEmergencyClaimsEachCoreBeforeNormalShutdown) {
    auto runtime = std::make_unique<Runtime>();
    auto scheduler = std::make_unique<SchedulerContext>();
    SchedulerContextTestPeer::seed(*scheduler, kAddrs);

    SchedulerContextTestPeer::emergency(*scheduler, runtime.get());
    EXPECT_EQ(scheduler->shutdown(runtime.get(), 0), 0);
    expect_group(*runtime);
}

TEST_F(HbgRetirementWiring, ConcurrentNormalAndEmergencyShutdownRetireEachCoreOnce) {
    auto runtime = std::make_unique<Runtime>();
    auto scheduler = std::make_unique<SchedulerContext>();
    SchedulerContextTestPeer::seed(*scheduler, kAddrs);
    std::atomic<bool> go{false};
    auto wait_for_start = [&] {
        while (!go.load(std::memory_order_acquire))
            std::this_thread::yield();
    };
    std::thread normal([&] {
        wait_for_start();
        EXPECT_EQ(scheduler->shutdown(runtime.get(), 0), 0);
    });
    std::thread emergency([&] {
        wait_for_start();
        SchedulerContextTestPeer::emergency(*scheduler, runtime.get());
    });
    go.store(true, std::memory_order_release);
    normal.join();
    emergency.join();
    std::array<int, 3> claims{};
    size_t target_count = 0;
    for (const RetireCall &call : retire_calls) {
        for (size_t target = 0; target < call.addrs.size(); ++target) {
            ++target_count;
            for (size_t core = 0; core < kAddrs.size(); ++core) {
                if (call.addrs[target] != kAddrs[core]) continue;
                ++claims[core];
                EXPECT_EQ(call.gates[target], &runtime->dev.teardown_gates[core]);
            }
        }
    }
    EXPECT_EQ(target_count, kAddrs.size());
    EXPECT_EQ(claims, (std::array<int, 3>{1, 1, 1}));
}

TEST_F(HbgRetirementWiring, LegacyShutdownSignalsAndRetiresTheSameGatedPartition) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);

    lifecycle.signal_shutdown_partition(0);
    EXPECT_EQ(exit_signals, std::vector<uint64_t>(kAddrs.begin(), kAddrs.end()));
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), 0);
    expect_group(*runtime);
}

TEST_F(HbgRetirementWiring, LegacyClearsStaleGatesBeforeHandshake) {
    auto runtime = std::make_unique<Runtime>();
    runtime->set_worker_count(3);
    for (auto &gate : runtime->dev.teardown_gates)
        gate.post_close_release = AICORE_POST_CLOSE_RELEASE;
    AicoreLifecycle lifecycle;

    ASSERT_EQ(lifecycle.pre_handshake_init(runtime.get(), 1, 0), 0);
    for (size_t i = 0; i < kAddrs.size(); ++i)
        EXPECT_EQ(runtime->dev.teardown_gates[i].post_close_release, 0u);
}

TEST_F(HbgRetirementWiring, FailedResidentFinishDoesNotStopUnclosedPmu) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    pmu_enabled = true;
    AicoreLifecycleTestPeer::mark_pmu_initialized(lifecycle);
    retirement_result = -1;
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_TRUE(pmu_stopped.empty());
}

TEST_F(HbgRetirementWiring, FailedResidentFinishCannotBeRetriedByTheSameOwner) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    retirement_result = -1;
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), -1);
    const auto count = retire_calls.size();
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), 0);
    EXPECT_EQ(retire_calls.size(), count);
}

TEST_F(HbgRetirementWiring, ResidentAbortAndFinishUseTheSameAbsoluteDeadline) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    retirement_result = -1;
    EXPECT_EQ(lifecycle.release_partition(runtime.get(), 0, false), -1);
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), 0);
    ASSERT_EQ(retire_calls.size(), 1u);
    EXPECT_EQ(deadline_calls.load(), 1u);
}

TEST_F(HbgRetirementWiring, ResidentRestoresPmuOnlyForAcknowledgedCoresBeforeReturn) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    AicoreLifecycleTestPeer::mark_pmu_initialized(lifecycle);
    pmu_enabled = true;
    mixed_release = true;
    retirement_result = -1;
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_EQ(pmu_stopped, (std::vector<int>{0}));
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), 0);
    EXPECT_EQ(pmu_stopped, (std::vector<int>{0}));
}

TEST_F(HbgRetirementWiring, ResidentDoesNotRestorePmuWhenInitializationNeverStartedIt) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    pmu_enabled = true;
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), 0);
    EXPECT_TRUE(pmu_stopped.empty());
}

TEST_F(HbgRetirementWiring, LateResidentPartitionUsesTheOriginalAbsoluteDeadline) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    AicoreLifecycleTestPeer::set_thread_count(lifecycle, 3);
    retirement_result = -1;
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_EQ(lifecycle.finish_shutdown_partition(1, runtime.get()), -1);
    EXPECT_EQ(lifecycle.release_partition(runtime.get(), 2, false), -1);
    ASSERT_EQ(retire_calls.size(), 3u);
    EXPECT_EQ(deadline_calls.load(), 1u);
    EXPECT_EQ(retire_calls[0].deadline, retire_calls[1].deadline);
    EXPECT_EQ(retire_calls[0].deadline, retire_calls[2].deadline);
}

TEST_F(HbgRetirementWiring, FailedLegacyStartupStillRetiresThroughPerCoreGates) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    retirement_result = -1;

    EXPECT_EQ(lifecycle.release_partition(runtime.get(), 0, false), -1);
    expect_group(*runtime);
}

TEST_F(HbgRetirementWiring, PartialResidentDiscoveryRetainsCurrentReportsForFailedInitRetirement) {
    auto runtime = std::make_unique<Runtime>();
    runtime->set_worker_count(3);
    AicoreLifecycle lifecycle;
    std::array<uint64_t, 3> registers = kAddrs;
    ASSERT_EQ(lifecycle.pre_handshake_init(runtime.get(), 1, reinterpret_cast<uint64_t>(registers.data())), 0);
    set_platform_run_result(0, 719);
    set_scheduler_timeout_ms(1);
    for (int i = 0; i < 3; ++i) {
        runtime->dev.workers[i].aicore_done = i + 1;
        runtime->dev.workers[i].physical_core_id = i;
        runtime->dev.workers[i].core_type = i == 0 ? CoreType::AIC : CoreType::AIV;
        runtime->dev.workers[i].report_epoch = i == 2 ? 718 : 719;
    }
    lifecycle.handshake_partition(runtime.get(), 0, 1);
    EXPECT_EQ(lifecycle.post_handshake_init(runtime.get()), -1);
    EXPECT_EQ(lifecycle.release_partition(runtime.get(), 0, false), 0);
    ASSERT_EQ(retire_calls.size(), 1u);
    EXPECT_EQ(retire_calls[0].addrs, (std::vector<uint64_t>{kAddrs[0], kAddrs[1]}));
    EXPECT_EQ(retire_calls[0].gates[0], &runtime->dev.teardown_gates[0]);
    EXPECT_EQ(retire_calls[0].gates[1], &runtime->dev.teardown_gates[1]);
    EXPECT_TRUE(pmu_stopped.empty());
}

TEST_F(HbgRetirementWiring, OverlappingResidentJoinDoesNotWaitForASignalOwner) {
    auto runtime = std::make_unique<Runtime>();
    AicoreLifecycle lifecycle;
    AicoreLifecycleTestPeer::seed(lifecycle, kAddrs);
    AicoreLifecycleTestPeer::signal_in_progress(lifecycle, 0);
    EXPECT_EQ(lifecycle.finish_shutdown_partition(0, runtime.get()), -1);
    ASSERT_EQ(retire_calls.size(), 1u);
    EXPECT_EQ(retire_calls[0].addrs, (std::vector<uint64_t>{kAddrs[1], kAddrs[2]}));
}
}  // namespace
