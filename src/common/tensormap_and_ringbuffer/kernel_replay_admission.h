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
#pragma once

#include <cstdint>
#include "task_interface/tmr_kernel_control.h"

namespace simpler::tmr {

inline void poison_replay(TmrReplayAdmission &state) noexcept {
    __atomic_store_n(&state.fault, uint32_t{1}, __ATOMIC_RELEASE);
}

inline uint64_t current_replay(const TmrReplayAdmission &state) noexcept {
    if (__atomic_load_n(&state.fault, __ATOMIC_ACQUIRE) != 0) return 0;
    const uint64_t epoch = __atomic_load_n(&state.ready_epoch, __ATOMIC_ACQUIRE);
    if ((epoch & 1) == 0 || __atomic_load_n(&state.sequence, __ATOMIC_ACQUIRE) != epoch ||
        __atomic_load_n(&state.fault, __ATOMIC_ACQUIRE) != 0)
        return 0;
    return epoch;
}

// clear is called only by the CAS winner. No DMA reset is allowed in front of
// this operation. A rejected prelude permanently poisons all successors, so a
// rejected graph cannot borrow the active graph's shared ready_epoch. This is
// deliberately fail-closed: a rejected overlap also retires the active context.
template <typename Clear>
uint64_t begin_replay(TmrReplayAdmission &state, Clear clear) noexcept {
    if (__atomic_load_n(&state.fault, __ATOMIC_ACQUIRE) != 0) return 0;
    uint64_t previous = __atomic_load_n(&state.sequence, __ATOMIC_ACQUIRE);
    if ((previous & 1) != 0 || previous >= UINT64_MAX - 1 ||
        !__atomic_compare_exchange_n(
            &state.sequence, &previous, previous + 1, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE
        )) {
        poison_replay(state);
        return 0;
    }
    const uint64_t epoch = previous + 1;
    if (__atomic_load_n(&state.fault, __ATOMIC_ACQUIRE) != 0 || !clear()) {
        poison_replay(state);
        return 0;
    }
    __atomic_store_n(&state.ready_epoch, epoch, __ATOMIC_RELEASE);
    return current_replay(state);
}

// The caller must be a graph epilogue ordered after BOTH native completions.
// A gate becoming idle, a queued cancellation, or a timeout is insufficient.
inline bool end_replay(TmrReplayAdmission &state, uint64_t epoch) noexcept {
    if (epoch == 0 || current_replay(state) != epoch) {
        poison_replay(state);
        return false;
    }
    uint64_t expected = epoch;
    if (!__atomic_compare_exchange_n(
            &state.sequence, &expected, epoch + 1, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE
        )) {
        poison_replay(state);
        return false;
    }
    return __atomic_load_n(&state.fault, __ATOMIC_ACQUIRE) == 0;
}

}  // namespace simpler::tmr
