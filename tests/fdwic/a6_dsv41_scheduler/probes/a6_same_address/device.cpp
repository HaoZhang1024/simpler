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
#include "measurement.h"

#include <pto/pto-inst.hpp>

template <Operation op>
AICORE inline void sample_rounds(__gm__ uint32_t *target, __gm__ Observation *records) {
#ifdef __DAV_VEC__
    constexpr uint32_t vector_lane = 1;
    const uint32_t slot = kPairs + get_block_idx() * get_subblockdim() + get_subblockid();
#else
    constexpr uint32_t vector_lane = 0;
    const uint32_t slot = get_block_idx();
#endif
    const uint32_t core = get_coreid();
    constexpr bool reading = op == Operation::Load || op == Operation::AddZero;
    for (uint32_t round = 0; round < kRounds; ++round) {
        if (slot == 0) {
            __builtin_cce_st_dev(uint32_t(reading), target, 0);
            dsb(DSB_DDR);
        }
        pto::SYNCALL<pto::SyncCoreType::Mix>();
        uint64_t begin, end;
        uint32_t value = 1;
        asm volatile("MOV %0, SYS_CNT" : "=l"(begin) : : "memory");
        if constexpr (op == Operation::Load) value = __builtin_cce_ld_dev(target, 0);
        if constexpr (op == Operation::AddZero) value = atomicAdd(target, uint32_t{0});
        if constexpr (op == Operation::Store) __builtin_cce_st_dev(value, target, 0);
        if constexpr (op == Operation::Exchange) value = atomicExch(target, uint32_t{1});
        if constexpr (!reading) dsb(DSB_DDR);
        // Consume the returned word before taking the end timestamp.
        asm volatile("MOV %0, %0\n\tMOV %1, SYS_CNT" : "+l"(value), "=&l"(end) : : "memory");
        pto::SYNCALL<pto::SyncCoreType::Mix>();
        auto *record = records + round * kLanes + slot;
        record->begin = begin;
        record->end = end;
        record->core = core;
        record->slot = slot;
        record->round = round;
        record->vector_lane = vector_lane;
        record->value = value;
        record->target_after_barrier = slot == 0 ? __builtin_cce_ld_dev(target, 0) : 0;
        dcci(record, SINGLE_CACHE_LINE, CACHELINE_OUT);
        dsb(DSB_DDR);
    }
}

extern "C" __global__ AICORE void measure_same_address(
    Operation op, __gm__ uint32_t *target, __gm__ Observation *records
) {
    switch (op) {
        case Operation::Load: sample_rounds<Operation::Load>(target, records); break;
        case Operation::AddZero: sample_rounds<Operation::AddZero>(target, records); break;
        case Operation::Store: sample_rounds<Operation::Store>(target, records); break;
        case Operation::Exchange: sample_rounds<Operation::Exchange>(target, records); break;
    }
}

extern "C" void launch_measurement(Operation op, uint32_t *target, Observation *records, void *stream) {
    measure_same_address<<<kPairs, nullptr, stream>>>(op, target, records);
}
