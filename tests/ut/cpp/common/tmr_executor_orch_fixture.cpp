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

#include "orchestration_api.h"
#include <chrono>

namespace {
OrchestrationConfig configure(const ChipTaskArgs &args, uint64_t id) {
    auto *output = reinterpret_cast<uint64_t *>(args.tensor(0).ref().buffer.addr);
    output[0] = id;
    output[1] = args.scalar(0);
    output[2] = reinterpret_cast<uint64_t>(&args.tensor(0).ref());
    return OrchestrationConfig{2};
}

void execute(const ChipTaskArgs &args, uint64_t id) {
    auto *output = reinterpret_cast<uint64_t *>(args.tensor(0).ref().buffer.addr);
    output[3] = id;
    output[4] = args.scalar(0);
    output[5] = reinterpret_cast<uint64_t>(&args.tensor(0).ref());
    CoreTaskArgs empty;
    rt_submit_dummy_task(empty);
}
}  // namespace

extern "C" OrchestrationConfig config_a(const ChipTaskArgs &args) { return configure(args, 3); }
extern "C" OrchestrationConfig config_b(const ChipTaskArgs &args) { return configure(args, 4); }
extern "C" OrchestrationConfig config_mismatch(const ChipTaskArgs &args) {
    configure(args, 5);
    return OrchestrationConfig{3};
}
extern "C" void orchestration_a(const ChipTaskArgs &args) { execute(args, 3); }
extern "C" void orchestration_b(const ChipTaskArgs &args) { execute(args, 4); }
extern "C" void orchestration_error(const ChipTaskArgs &args) {
    execute(args, 3);
    RuntimeContext *rt = current_runtime();
    rt->ops->report_fatal(rt, SIMPLER_ERROR_INVALID_ARGS, __FUNCTION__, "intentional executor failure");
}

extern "C" void orchestration_finite(const ChipTaskArgs &args) {
    execute(args, 3);
    auto *output = reinterpret_cast<uint64_t *>(args.tensor(0).ref().buffer.addr);
    // Prove that the finite producer passed its only submission and returned;
    // no core report or long-running orchestration keeps this round alive.
    __atomic_store_n(&output[3], uint64_t{99}, __ATOMIC_RELEASE);
}

extern "C" void orchestration_cooperative(const ChipTaskArgs &args) {
    auto *output = reinterpret_cast<uint64_t *>(args.tensor(0).ref().buffer.addr);
    __atomic_store_n(&output[3], uint64_t{1}, __ATOMIC_RELEASE);
    const auto until = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    CoreTaskArgs empty;
    while (!rt_is_fatal() && std::chrono::steady_clock::now() < until) {
        // Legal bounded scopes avoid scope-capacity failure before startup
        // expires; eventually the absent scheduler blocks slot allocation.
        rt_scope_begin();
        rt_submit_dummy_task(empty);
        rt_scope_end();
    }
    output[4] = rt_is_fatal() ? 1 : 0;
    // A further public API call must promptly retain the observed failure.
    rt_submit_dummy_task(empty);
    output[5] = rt_is_fatal() ? 1 : 0;
    __atomic_store_n(&output[3], uint64_t{99}, __ATOMIC_RELEASE);
}
