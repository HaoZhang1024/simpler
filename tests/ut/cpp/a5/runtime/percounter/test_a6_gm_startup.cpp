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

#include <functional>
#include <gtest/gtest.h>

#include "inner_kernel.h"
#include "runtime_types.h"

namespace {
std::function<void()> advance_aicpu;
}

#undef SPIN_WAIT_HINT
#define SPIN_WAIT_HINT() advance_aicpu()

uint64_t get_aicore_report_epoch();
#include "lane_loop.h"
#include "aicpu/abort_aicore_startup.h"

namespace {
using namespace simpler::percounter;

TEST(PercounterGmStartup, RetiresBeforeReadyAndAcceptsOnlyFreshReleaseOnReuse) {
    Handshake report{};
    PercounterControl control{};
    AicoreTeardownControl gate{};
    gate.exit_request = AICORE_EXIT_NONCE_0;
    report.aicpu_ready = SCHEDULER_RUNTIME_MODE_PERCOUNTER;
    aicore_stage_native_report(&report, 0, CoreType::AIC, 1, 0);

    int polls = 0;
    advance_aicpu = [&] {
        ++polls;
        EXPECT_EQ(report.aicpu_ready, 0U);
        gate = {};
        publish_aicore_startup_abort(&report);
    };
    EXPECT_FALSE(percounter_wait_for_gm_release(&report, &control, 0));
    EXPECT_EQ(polls, 1);
    EXPECT_EQ(control.lane_error, 0U);

    gate.exit_request = AICORE_EXIT_NONCE_1;
    aicore_stage_native_report(&report, 0, CoreType::AIC, 1, 0);
    advance_aicpu = [&] {
        ++polls;
        EXPECT_EQ(report.aicpu_ready, 0U);
        gate = {};
        report.aicpu_ready = SCHEDULER_RUNTIME_MODE_PERCOUNTER;
    };
    EXPECT_TRUE(percounter_wait_for_gm_release(&report, &control, 0));
    EXPECT_EQ(polls, 2);
    LaneConfig cfg{};
    cfg.control = &control;
    cfg.teardown_gate = &gate;
    EXPECT_FALSE(percounter_should_stop(cfg));
    gate.exit_request = AICORE_EXIT_NONCE_0;
    EXPECT_TRUE(percounter_should_stop(cfg));
    advance_aicpu = {};
}

TEST(PercounterGmStartup, TimedOutLaneWaitsForCurrentPublicationWithoutRunning) {
    Handshake report{};
    PercounterControl control{};
    advance_aicpu = [&] {
        if (control.lane_error != 0) report.aicpu_ready = SCHEDULER_RUNTIME_MODE_PERCOUNTER;
    };
    EXPECT_FALSE(percounter_wait_for_gm_release(&report, &control, 1));
    EXPECT_EQ(control.lane_error, static_cast<uint64_t>(SchedulerGraphResult::TIMEOUT));
    EXPECT_EQ(report.aicpu_ready, SCHEDULER_RUNTIME_MODE_PERCOUNTER);
    advance_aicpu = {};
}

}  // namespace
