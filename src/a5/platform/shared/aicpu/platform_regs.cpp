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
/**
 * @file platform_regs.cpp
 * @brief AICPU register interface - shared implementation
 *
 * Contains platform-agnostic functions shared across all platforms.
 * Platform-specific read_reg/write_reg are in:
 *   sim/aicpu/inner_platform_regs.cpp    -- sparse_reg_ptr mapping for simulation
 *   onboard/aicpu/inner_platform_regs.cpp -- direct MMIO offset for hardware
 */

#include <cstdint>
#include "common/memory_barrier.h"
#include "aicore_teardown.h"
#include "aicpu/device_time.h"
#include "aicpu/platform_regs.h"
#include "common/platform_config.h"
#include "common/unified_log.h"
#include "spin_hint.h"

static uint64_t g_platform_regs = 0;

void set_platform_regs(uint64_t regs) { g_platform_regs = regs; }

uint64_t get_platform_regs() { return g_platform_regs; }

void platform_init_aicore_regs(uint64_t reg_addr) {
    // Initialize task dispatch register to idle state
    write_reg(reg_addr, RegId::DATA_MAIN_BASE, AICPU_IDLE_TASK_ID);
}

uint64_t platform_aicore_exit_deadline() { return get_sys_cnt_aicpu() + inner_get_deinit_timeout_ticks(); }

void platform_close_aicore_window(uint64_t reg_addr) {
    write_reg(reg_addr, RegId::DATA_MAIN_BASE, AICPU_IDLE_TASK_ID);
    (void)read_reg(reg_addr, RegId::DATA_MAIN_BASE);
}

int32_t platform_deinit_aicore_regs(uint64_t reg_addr) {
    // Send exit signal to AICore
    write_reg(reg_addr, RegId::DATA_MAIN_BASE, AICORE_EXIT_SIGNAL);

    // Wait for AICore to acknowledge exit by writing AICORE_EXITED_VALUE to COND.
    // Timeout is variant-specific (sim wider than onboard) — see
    // inner_get_deinit_timeout_ticks declaration in platform_regs.h.
    const uint64_t deinit_timeout_ticks = inner_get_deinit_timeout_ticks();
    uint64_t t0 = get_sys_cnt_aicpu();
    while (read_reg(reg_addr, RegId::COND) != AICORE_EXITED_VALUE) {
        if (get_sys_cnt_aicpu() - t0 > deinit_timeout_ticks) {
            LOG_ERROR("Timed out waiting for AICore exit ack at reg_addr=0x%lx", static_cast<unsigned long>(reg_addr));
            return -1;
        }
        SPIN_WAIT_HINT();
    }

    // Initialize task dispatch register to idle state
    write_reg(reg_addr, RegId::DATA_MAIN_BASE, AICPU_IDLE_TASK_ID);
    return 0;
}

uint32_t platform_get_physical_cores_count() {
    return DAV_3510::PLATFORM_MAX_PHYSICAL_CORES * PLATFORM_CORES_PER_BLOCKDIM;
}

int32_t platform_deinit_aicore_regs_group(
    const uint64_t *reg_addrs, size_t count, uint64_t deadline, bool *closed, bool send_exit
) {
    if (closed != nullptr) {
        const size_t reportable = count < PLATFORM_MAX_CORES ? count : PLATFORM_MAX_CORES;
        for (size_t i = 0; i < reportable; ++i)
            closed[i] = false;
    }
    if (count > PLATFORM_MAX_CORES || (count != 0 && reg_addrs == nullptr)) return -1;
    for (size_t i = 0; i < count; ++i) {
        if (reg_addrs[i] == 0) return -1;
    }
    if (send_exit) {
        for (size_t i = 0; i < count; ++i)
            write_reg(reg_addrs[i], RegId::DATA_MAIN_BASE, AICORE_EXIT_SIGNAL);
        wmb();
    }
    bool acknowledged[PLATFORM_MAX_CORES]{};
    size_t remaining = count;
    while (remaining != 0) {
        for (size_t i = 0; i < count; ++i) {
            if (!acknowledged[i] && read_reg(reg_addrs[i], RegId::COND) == AICORE_EXITED_VALUE) {
                acknowledged[i] = true;
                --remaining;
            }
        }
        if (remaining == 0 || get_sys_cnt_aicpu() > deadline) break;
    }
    for (size_t i = 0; i < count; ++i) {
        if (acknowledged[i]) write_reg(reg_addrs[i], RegId::DATA_MAIN_BASE, AICPU_IDLE_TASK_ID);
    }
    for (size_t i = 0; i < count; ++i) {
        if (acknowledged[i]) (void)read_reg(reg_addrs[i], RegId::DATA_MAIN_BASE);
    }
    rmb();
    if (closed != nullptr) {
        for (size_t i = 0; i < count; ++i)
            closed[i] = acknowledged[i];
    }
    return remaining == 0 ? 0 : -1;
}

int32_t platform_retire_aicore_current_ack_group(
    const AicoreExitTarget *targets, size_t count, uint64_t deadline, bool *released
) {
    // `released` is filled before anything can return, rejection included, so a
    // caller may read it without initializing the buffer. An over-large `count`
    // says nothing about how big that buffer is, so the fill stops at the one
    // size the contract guarantees.
    if (released != nullptr) {
        const size_t reportable = count < PLATFORM_MAX_CORES ? count : PLATFORM_MAX_CORES;
        for (size_t i = 0; i < reportable; ++i)
            released[i] = false;
    }
    if (count > PLATFORM_MAX_CORES || (count != 0 && targets == nullptr)) return -1;
    for (size_t i = 0; i < count; ++i) {
        if (targets[i].reg_addr == 0 || targets[i].teardown == nullptr) return -1;
    }

    // Pick a nonzero request different from the ACK currently in memory. A
    // retained EXITED and retained ACK cannot acknowledge this request. Only the
    // exclusively-claimed caller writes the request; AICore owns the ACK line.
    uint32_t exit_requests[PLATFORM_MAX_CORES];
    {
        for (size_t i = 0; i < count; ++i) {
            auto *control = targets[i].teardown;
            cache_invalidate_range(&control->exit_ack, sizeof(control->exit_ack));
            const uint32_t previous_ack = __atomic_load_n(&control->exit_ack, __ATOMIC_ACQUIRE);
            const uint32_t request = previous_ack == UINT32_MAX ? 1U : previous_ack + 1U;
            exit_requests[i] = request;
            __atomic_store_n(&control->exit_request, request, __ATOMIC_RELAXED);
        }
        // The request is Normal memory and EXIT is posted Device memory. Publish
        // every request before any core can observe the EXIT that asks for it.
        wmb();
    }
    // Broadcast to the whole group before waiting on any member, so the cores
    // drain concurrently and a dead core's wait does not serialize behind the
    // cores ahead of it.
    for (size_t i = 0; i < count; ++i) {
        write_reg(targets[i].reg_addr, RegId::DATA_MAIN_BASE, AICORE_EXIT_SIGNAL);
    }
    wmb();

    // Round-robin rather than blocking on one core at a time. Blocking spends
    // the shared deadline on whichever core happens to come first, and every
    // core behind it is then judged on a peer's timeout instead of its own.
    // Sweeping non-blockingly gives each core the whole budget: a core is only
    // abandoned once the deadline passes with it still silent.
    // The sweep below reads an entry before it writes it, so the first `count`
    // must start false. Entries past `count` are never read.
    bool acknowledged[PLATFORM_MAX_CORES];
    for (size_t i = 0; i < count; ++i)
        acknowledged[i] = false;
    size_t remaining = count;
    while (remaining != 0) {
        for (size_t i = 0; i < count; ++i) {
            if (acknowledged[i]) continue;
            const uint32_t cond = static_cast<uint32_t>(read_reg(targets[i].reg_addr, RegId::COND));
            if (cond != AICORE_EXITED_VALUE) continue;
            {
                auto *control = targets[i].teardown;
                // This line has no AICPU writer. Invalidation cannot write back a
                // competing value, and its drain precedes the fresh ACK load.
                cache_invalidate_range(&control->exit_ack, sizeof(control->exit_ack));
                if (__atomic_load_n(&control->exit_ack, __ATOMIC_ACQUIRE) == exit_requests[i]) {
                    acknowledged[i] = true;
                    --remaining;
                }
            }
        }
        if (remaining == 0 || get_sys_cnt_aicpu() > deadline) break;
    }

    // No window closes until every ACK above is in, so a core is never quiesced
    // while a peer is still being waited on. COND is not re-read here: the
    // passes above already established it.
    int32_t rc = 0;
    for (size_t i = 0; i < count; ++i) {
        if (acknowledged[i]) {
            write_reg(targets[i].reg_addr, RegId::DATA_MAIN_BASE, AICPU_IDLE_TASK_ID);
        } else {
            rc = -1;
        }
    }
    // Issue the whole group's posted CLOSE writes before reading back any
    // window. Each acknowledged window still needs its own completion read.
    for (size_t i = 0; i < count; ++i) {
        if (acknowledged[i]) (void)read_reg(targets[i].reg_addr, RegId::DATA_MAIN_BASE);
    }
    // One drain covers every readback the close pass issued, and it is what
    // orders every store below after the CLOSE it belongs to: a dsb blocks
    // every later instruction until it completes, so the relaxed stores cannot
    // move ahead of it.
    rmb();
    // An open return gate is only ever paired with a closed window: releasing a
    // core whose window is still open is the ordering violation this protocol
    // exists to prevent. Unreleased cores are reported through `released` so
    // the caller can name them; the host recovery path owns them from here.
    for (size_t i = 0; i < count; ++i) {
        if (acknowledged[i]) {
            __atomic_store_n(&targets[i].teardown->post_close_release, AICORE_POST_CLOSE_RELEASE, __ATOMIC_RELAXED);
        }
        if (released != nullptr) released[i] = acknowledged[i];
    }
    return rc;
}
