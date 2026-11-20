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

constexpr uint32_t kPairs = 48;
constexpr uint32_t kLanes = kPairs * 2;
constexpr uint32_t kRounds = 193;  // First round warms up the launched kernel.

enum class Operation : uint32_t { Load, AddZero, Store, Exchange };

struct alignas(64) Observation {
    uint64_t begin;
    uint64_t end;
    uint32_t slot;
    uint32_t vector_lane;
    uint32_t core;
    uint32_t round;
    uint32_t value;
    uint32_t target_after_barrier;
};
static_assert(sizeof(Observation) == 64);

extern "C" void launch_measurement(Operation, uint32_t *, Observation *, void *);
