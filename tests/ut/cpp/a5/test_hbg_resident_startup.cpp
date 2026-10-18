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
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <stdexcept>
#include <thread>
#include <vector>
#include "aicore/aicore.h"
#include "aicore/aicore_profiling_state.h"
#include "runtime.h"
#include "scheduler/scheduler_types.h"

void aicore_execute(Runtime *, int, CoreType);
namespace {
std::vector<uint32_t> registers(0x6000 / sizeof(uint32_t));

template <typename Predicate>
bool wait_until(Predicate predicate) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (!predicate()) {
        if (std::chrono::steady_clock::now() >= deadline) return false;
        std::this_thread::yield();
    }
    return true;
}

void check_current_report_resets_cond(CoreType type) {
    Runtime runtime;
    alignas(128) SchedulerWorkerContext context{};
    alignas(128) SchedulerRunControl control{};
    context.scheduler_state_base_address = reinterpret_cast<uint64_t>(&control);
    context.run_control_offset = 0;
    control.scheduler_timeout_cycles = 0;
    runtime.worker_count = 1;
    runtime.kernel_prelaunch.state = HBG_KERNEL_PRELAUNCH_READY;
    runtime.workers[0].aicpu_ready = SCHEDULER_RUNTIME_MODE_RESIDENT_PENDING;
    runtime.workers[0].task = reinterpret_cast<uint64_t>(&context);
    // A previous invocation ended with this retained value. A current startup
    // report must never make that old COND eligible to acknowledge a new EXIT.
    write_reg(RegId::COND, AICORE_EXITED_VALUE);
    std::atomic<bool> returned{false};
    std::thread core([&] {
        aicore_execute(&runtime, 0, type);
        returned.store(true, std::memory_order_release);
    });
    if (!wait_until([&] {
            return __atomic_load_n(&runtime.workers[0].aicore_done, __ATOMIC_ACQUIRE) != 0;
        }))
        std::_Exit(2);
    if (read_reg(RegId::COND) != AICORE_IDLE_VALUE) std::_Exit(3);
    if (returned.load(std::memory_order_acquire)) std::_Exit(4);
    // This is the actual pre-READY cooperative abort path, after the observed
    // report/IDLE boundary and before bootstrap or any payload can execute.
    __atomic_store_n(&control.scheduler_error, 1ULL, __ATOMIC_RELEASE);
    if (!wait_until([&] {
            return returned.load(std::memory_order_acquire);
        }))
        std::_Exit(5);
    core.join();
    if (read_reg(RegId::COND) != AICORE_EXITED_VALUE) std::_Exit(6);
    std::_Exit(0);
}
TEST(A5HbgResidentStartupDeathTest, AicClearsRetainedCondBeforeCurrentReport) {
    EXPECT_EXIT(check_current_report_resets_cond(CoreType::AIC), testing::ExitedWithCode(0), "");
}
TEST(A5HbgResidentStartupDeathTest, AivClearsRetainedCondBeforeCurrentReport) {
    EXPECT_EXIT(check_current_report_resets_cond(CoreType::AIV), testing::ExitedWithCode(0), "");
}
}  // namespace

[[noreturn]] void assert_impl(const char *condition, const char *, int) { throw std::logic_error(condition); }
void legacy_aicore_execute(Runtime *, int, CoreType) { std::_Exit(7); }
volatile uint8_t *sim_get_reg_base() { return reinterpret_cast<volatile uint8_t *>(registers.data()); }
uint32_t sim_get_physical_core_id() { return 0; }
uint32_t get_aicore_profiling_flag() { return 0; }
ChipSwimlaneActiveHead *get_chip_swimlane_aicore_head() { return nullptr; }
struct PmuAicoreRing;
PmuAicoreRing *get_aicore_pmu_ring() { return nullptr; }
uint64_t get_aicore_pmu_reg_base() { return 0; }

extern "C" {
void unified_log_error(const char *, const char *, ...) {}
void unified_log_warn(const char *, const char *, ...) {}
void unified_log_info(const char *, const char *, ...) {}
void unified_log_debug(const char *, const char *, ...) {}
void unified_log_timing(const char *, const char *, ...) {}
}
