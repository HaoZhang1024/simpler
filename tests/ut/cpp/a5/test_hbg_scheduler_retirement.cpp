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
#include "scheduler/scheduler_context.h"

namespace {
uint64_t ticks;
std::array<int, 4> exits, closes;
std::array<bool, 4> acknowledges;
int first_poll_exits;

class A5HbgRetirement : public testing::Test {
protected:
    std::unique_ptr<SchedulerContext> scheduler;
    void SetUp() override {
        ticks = 0;
        exits.fill(0);
        closes.fill(0);
        acknowledges.fill(false);
        first_poll_exits = -1;
        scheduler = std::make_unique<SchedulerContext>();
        scheduler->cores_total_num_ = 3;
        scheduler->core_trackers_[0].init(1);
        scheduler->core_trackers_[0].set_cluster(0, 0, 1, 2);
        for (int i = 0; i < 3; ++i)
            scheduler->core_exec_states_[i].reg_addr = i + 1;
    }
};

TEST_F(A5HbgRetirement, NormalShutdownSilentGroupPaysOneBudgetAndBroadcastsBeforePolling) {
    EXPECT_EQ(scheduler->shutdown(0), -1);
    EXPECT_LT(ticks, 130u);
    EXPECT_EQ(first_poll_exits, 3);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}

TEST_F(A5HbgRetirement, EmergencySilentGroupPaysOneBudgetAndNormalShutdownCannotRetryIt) {
    scheduler->emergency_shutdown(nullptr);
    const auto after_emergency = ticks;
    EXPECT_LT(after_emergency, 130u);
    EXPECT_EQ(scheduler->shutdown(0), 0);
    EXPECT_EQ(ticks, after_emergency);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 0);
    }
}

TEST_F(A5HbgRetirement, PartialAckClosesOnlyAcknowledgedWindowAndNeverRetriesSilentWindows) {
    acknowledges[2] = true;
    EXPECT_EQ(scheduler->shutdown(0), -1);
    EXPECT_LT(ticks, 130u);
    EXPECT_EQ(closes[1], 0);
    EXPECT_EQ(closes[2], 1);
    EXPECT_EQ(closes[3], 0);
    scheduler->emergency_shutdown(nullptr);
    for (int i = 1; i <= 3; ++i)
        EXPECT_EQ(exits[i], 1);
}

TEST_F(A5HbgRetirement, HealthyGroupClosesOnceAndEmptyOwnerDoesNotAllocateBudget) {
    acknowledges.fill(true);
    EXPECT_EQ(scheduler->shutdown(0), 0);
    const auto finished = ticks;
    EXPECT_EQ(scheduler->shutdown(1), 0);
    EXPECT_EQ(ticks, finished);
    scheduler->emergency_shutdown(nullptr);
    for (int i = 1; i <= 3; ++i) {
        EXPECT_EQ(exits[i], 1);
        EXPECT_EQ(closes[i], 1);
    }
}
}  // namespace

[[noreturn]] void assert_impl(const char *condition, const char *, int) { throw std::logic_error(condition); }

uint64_t get_sys_cnt_aicpu() { return ++ticks; }
uint64_t inner_get_deinit_timeout_ticks() { return 100; }
uint64_t read_reg(uint64_t base, RegId reg) {
    if (reg == RegId::COND) {
        if (first_poll_exits == -1) first_poll_exits = exits[1] + exits[2] + exits[3];
        return acknowledges.at(base) ? AICORE_EXITED_VALUE : AICORE_IDLE_VALUE;
    }
    return 0;
}
void write_reg(uint64_t base, RegId reg, uint64_t value) {
    if (reg != RegId::DATA_MAIN_BASE) return;
    if (value == AICORE_EXIT_SIGNAL) ++exits.at(base);
    if (value == AICPU_IDLE_TASK_ID) ++closes.at(base);
}
namespace aicpu_cache_maintenance {
void invalidate_range_impl(const void *, size_t) {}
void flush_range_impl(const void *, size_t) {}
}  // namespace aicpu_cache_maintenance
extern "C" {
void unified_log_error(const char *, const char *, ...) {}
void unified_log_warn(const char *, const char *, ...) {}
void unified_log_info(const char *, const char *, ...) {}
void unified_log_debug(const char *, const char *, ...) {}
void unified_log_timing(const char *, const char *, ...) {}
}
