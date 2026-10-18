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
#include <memory>
#include <stdexcept>
#include "aicore_lifecycle.h"
#include "aicore_scheduler_state.h"
#include "aicpu/platform_regs.h"
#include "common/chip_swimlane_profiling.h"
#include "runtime.h"

namespace {
uint64_t ticks;
std::array<int, 7> exits, closes, readbacks;
std::array<bool, 7> acknowledges;
int first_poll_exits;
bool pmu_enabled, profiling_enabled;
std::array<int, 7> pmu_stops, profiling_flushes;

class A5HbgResidentRetirement : public testing::Test {
protected:
    std::unique_ptr<AicoreLifecycle> lifecycle;
    std::unique_ptr<Runtime> runtime;
    void SetUp() override {
        ticks = 0;
        exits.fill(0);
        closes.fill(0);
        readbacks.fill(0);
        acknowledges.fill(false);
        first_poll_exits = -1;
        pmu_enabled = profiling_enabled = false;
        pmu_stops.fill(0);
        profiling_flushes.fill(0);
        lifecycle = std::make_unique<AicoreLifecycle>();
        runtime = std::make_unique<Runtime>();
        reset(3, 1);
    }
    void reset(int cores, int threads) {
        runtime->worker_count = cores;
        ASSERT_EQ(lifecycle->pre_handshake_init(runtime.get(), threads, 0), 0);
        for (int i = 0; i < cores; ++i)
            lifecycle->cores_[i].reg_addr = i + 1;
    }
};

TEST_F(A5HbgResidentRetirement, FinishSilentPartitionPaysOneBudgetAndBroadcastsBeforePolling) {
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_LT(ticks, 130u);
    EXPECT_EQ(first_poll_exits, 3);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}
TEST_F(A5HbgResidentRetirement, InitAbortSilentPartitionPaysOneBudgetAndBroadcastsBeforePolling) {
    EXPECT_EQ(lifecycle->release_partition(0, false), -1);
    EXPECT_LT(ticks, 130u);
    EXPECT_EQ(first_poll_exits, 3);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}
TEST_F(A5HbgResidentRetirement, AllPartitionsAndBothEntrypointsShareOneAbsoluteDeadline) {
    reset(6, 2);
    EXPECT_EQ(lifecycle->release_partition(0, false), -1);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(1, runtime.get()), -1);
    EXPECT_LT(ticks, 140u);
    for (int i = 1; i <= 6; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}
TEST_F(A5HbgResidentRetirement, FailedTargetsAreNotRetriedByOtherCleanupEntry) {
    EXPECT_EQ(lifecycle->release_partition(0, false), -1);
    const auto after_abort = ticks;
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), 0);
    EXPECT_EQ(lifecycle->release_partition(0, false), 0);
    EXPECT_EQ(ticks, after_abort);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}
TEST_F(A5HbgResidentRetirement, PartialAckClosesAndReadsBackOnlyAcknowledgedTarget) {
    acknowledges[2] = true;
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_LT(ticks, 130u);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(closes[i], i == 2 ? 1 : 0);
        EXPECT_EQ(readbacks[i], i == 2 ? 1 : 0);
    }
}
TEST_F(A5HbgResidentRetirement, HealthyTargetCannotBeClosedAgainAndNewInitResetsClaims) {
    acknowledges.fill(true);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), 0);
    const auto finished = ticks;
    EXPECT_EQ(lifecycle->release_partition(0, false), 0);
    EXPECT_EQ(ticks, finished);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 1);
        EXPECT_EQ(readbacks[i], 1);
    }
    reset(3, 1);
    acknowledges.fill(false);
    const auto restarted = ticks;
    EXPECT_EQ(lifecycle->release_partition(0, false), -1);
    EXPECT_GE(ticks - restarted, 100u);
    EXPECT_LT(ticks - restarted, 130u);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 2);
        EXPECT_EQ(closes[i], 1);
    }
}
TEST_F(A5HbgResidentRetirement, SignalAllPartitionsPrecedesAnyJoinAndDoesNotRebroadcast) {
    reset(6, 2);
    lifecycle->signal_shutdown_partition(0);
    lifecycle->signal_shutdown_partition(1);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(1, runtime.get()), -1);
    EXPECT_EQ(first_poll_exits, 6);
    EXPECT_LT(ticks, 140u);
    for (int i = 1; i <= 6; ++i)
        EXPECT_EQ(exits[i], 1);
}
TEST_F(A5HbgResidentRetirement, SilentTargetsNeverStopPmuOrFlushProfilingEvenWhenInitialized) {
    pmu_enabled = profiling_enabled = true;
    lifecycle->pmu_initialized_.store(true);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), -1);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(pmu_stops[i], 0);
        EXPECT_EQ(profiling_flushes[i], 0);
    }
}
TEST_F(A5HbgResidentRetirement, MixedAckFinalizesOnlyClosedTargetOnceAfterReadback) {
    pmu_enabled = profiling_enabled = true;
    lifecycle->pmu_initialized_.store(true);
    acknowledges[2] = true;
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), -1);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), 0);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(pmu_stops[i], i == 2 ? 1 : 0);
        EXPECT_EQ(profiling_flushes[i], i == 2 ? 1 : 0);
    }
}
TEST_F(A5HbgResidentRetirement, AbortBeforePmuInitDoesNotRestoreUninitializedPmuState) {
    pmu_enabled = true;
    acknowledges.fill(true);
    EXPECT_EQ(lifecycle->release_partition(0, false), 0);
    EXPECT_EQ(lifecycle->finish_shutdown_partition(0, runtime.get()), 0);
    for (int i = 1; i <= 3; ++i)
        EXPECT_EQ(pmu_stops[i], 0);
}
TEST_F(A5HbgResidentRetirement, PartialHandshakeRetainsValidatedTargetsForInitAbort) {
    reset(3, 1);
    for (auto &c : lifecycle->cores_)
        c.reg_addr = 0;
    uint64_t regs[3]{1, 2, 3};
    lifecycle->regs_base_ = reinterpret_cast<uint64_t>(regs);
    for (int i = 0; i < 2; ++i) {
        runtime->workers[i].aicore_done = 1;
        runtime->workers[i].physical_core_id = i;
        runtime->workers[i].core_type = CoreType::AIV;
    }
    lifecycle->handshake_partition(runtime.get(), 0, 1);
    EXPECT_TRUE(lifecycle->handshake_failed_.load());
    const auto abort_start = ticks;
    EXPECT_EQ(lifecycle->release_partition(0, false), -1);
    EXPECT_LT(ticks - abort_start, 130u);
    EXPECT_EQ(exits[1], 1);
    EXPECT_EQ(exits[2], 1);
    EXPECT_EQ(exits[3], 0);
    EXPECT_EQ(lifecycle->cores_[2].reg_addr, 0u);
}
TEST_F(A5HbgResidentRetirement, PublicResidentMarkerSelectsLifecycleAndLegacyMarkersDoNot) {
    for (int i = 0; i < 3; ++i)
        runtime->workers[i].aicpu_ready = SCHEDULER_RUNTIME_MODE_RESIDENT_PENDING;
    EXPECT_TRUE(aicore_scheduler_runtime_enabled(runtime.get()));
    runtime->workers[0].aicpu_ready = SCHEDULER_RUNTIME_MODE_RESIDENT_READY;
    EXPECT_TRUE(aicore_scheduler_runtime_enabled(runtime.get()));
    runtime->workers[0].aicpu_ready = SCHEDULER_RUNTIME_MODE_LEGACY_GRAPH;
    EXPECT_FALSE(aicore_scheduler_runtime_enabled(runtime.get()));
    runtime->workers[0].aicpu_ready = SCHEDULER_RUNTIME_MODE_LEGACY_UNSUPPORTED_SHAPE;
    EXPECT_FALSE(aicore_scheduler_runtime_enabled(runtime.get()));
}
}  // namespace

[[noreturn]] void assert_impl(const char *condition, const char *, int) { throw std::logic_error(condition); }
uint64_t get_sys_cnt_aicpu() { return ++ticks; }
uint64_t inner_get_deinit_timeout_ticks() { return 100; }
uint64_t read_reg(uint64_t base, RegId reg) {
    if (reg == RegId::COND) {
        if (first_poll_exits == -1) {
            first_poll_exits = 0;
            for (int i = 1; i <= 6; ++i)
                first_poll_exits += exits[i];
        }
        return acknowledges.at(base) ? AICORE_EXITED_VALUE : AICORE_IDLE_VALUE;
    }
    if (reg == RegId::DATA_MAIN_BASE) ++readbacks.at(base);
    return 0;
}
void write_reg(uint64_t base, RegId reg, uint64_t value) {
    if (reg != RegId::DATA_MAIN_BASE) return;
    if (value == AICORE_EXIT_SIGNAL) ++exits.at(base);
    if (value == AICPU_IDLE_TASK_ID) ++closes.at(base);
}
ChipSwimlaneLevel get_chip_swimlane_level() { return static_cast<ChipSwimlaneLevel>(0); }
void chip_swimlane_aicpu_init(int) {}
void chip_swimlane_aicpu_flush(int, const int *ids, int count) {
    for (int i = 0; i < count; ++i) {
        EXPECT_GT(readbacks.at(ids[i] + 1), 0);
        ++profiling_flushes.at(ids[i] + 1);
    }
}
void pmu_aicpu_finalize(const int *ids, int count) {
    for (int i = 0; i < count; ++i) {
        EXPECT_GT(readbacks.at(ids[i] + 1), 0);
        ++pmu_stops.at(ids[i] + 1);
    }
}
namespace aicpu_cache_maintenance {
void invalidate_range_impl(const void *, size_t) {}
void flush_range_impl(const void *, size_t) {}
}  // namespace aicpu_cache_maintenance
extern "C" {
bool is_pmu_enabled() { return pmu_enabled; }
bool is_dump_args_enabled() { return false; }
bool is_chip_swimlane_enabled() { return profiling_enabled; }
int get_scheduler_timeout_ms() { return 1; }
void unified_log_error(const char *, const char *, ...) {}
void unified_log_warn(const char *, const char *, ...) {}
void unified_log_info(const char *, const char *, ...) {}
void unified_log_debug(const char *, const char *, ...) {}
void unified_log_timing(const char *, const char *, ...) {}
}
