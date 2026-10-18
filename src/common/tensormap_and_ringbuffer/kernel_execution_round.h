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

#include "kernel_execution.h"
#include "kernel_native_status.h"

namespace simpler::tmr {

// The two architecture executors supply the same cold-path operations. This
// coordinator owns publication/retirement, not scheduling or resource ownership.
template <typename Executor>
int32_t execute_kernel_round_impl(
    Executor &executor, const KernelExecutionRequest &request, int32_t cpu, KernelFinalStatus *out = nullptr
) noexcept {
    // These are trusted prepare-time topology values, checked before launch.
    if (request.allowed_cpus == nullptr || request.execution_threads <= 0 ||
        request.execution_threads > request.launched_threads || request.launched_threads > MAX_GATE_THREADS)
        return -1;
    for (int32_t i = 0; i < request.execution_threads; ++i) {
        if (request.allowed_cpus[i] < 0) return -1;
        for (int32_t j = 0; j < i; ++j)
            if (request.allowed_cpus[i] == request.allowed_cpus[j]) return -1;
    }
    const auto replay_failed = [&]() noexcept {
        return request.replay_admission != nullptr &&
               __atomic_load_n(&request.replay_admission->fault, __ATOMIC_ACQUIRE) != 0;
    };
    struct WaitContext {
        const KernelExecutionRequest &request;
    } wait_context{request};
    KernelWaitControl wait = request.wait_control;
    wait.context = &wait_context;
    wait.keep_waiting = [](void *opaque) noexcept {
        const auto &r = static_cast<WaitContext *>(opaque)->request;
        return (r.replay_admission == nullptr || __atomic_load_n(&r.replay_admission->fault, __ATOMIC_ACQUIRE) == 0) &&
               (r.wait_control.keep_waiting == nullptr || r.wait_control.keep_waiting(r.wait_control.context));
    };
    wait.on_abort = [](void *opaque) noexcept {
        const auto &r = static_cast<WaitContext *>(opaque)->request;
        // Classify before publishing the sticky fault for a fresh deadline.
        // Otherwise every deadline looks like an admission fault here.
        if (r.wait_control.on_abort != nullptr) r.wait_control.on_abort(r.wait_control.context);
        if (r.replay_admission != nullptr)
            __atomic_store_n(
                &const_cast<TmrReplayAdmission *>(r.replay_admission)->fault, uint32_t{1}, __ATOMIC_RELEASE
            );
    };
    auto &gate = executor.kernel_gate_;
    KernelRoundTicket ticket;
    if (!gate.join(request.launched_threads, cpu, &ticket, wait)) return -1;
    if (ticket.launch_index == 0) {
        auto handshake = request.handshake;
        if (handshake.epoch == 0) handshake.epoch = ticket.epoch;
        executor.kernel_storage_attached_ = executor.kernel_storage_.attach(handshake);
        int32_t status = request.admission_status;
        if (!executor.kernel_storage_attached_ || replay_failed()) status = -1;
        if (status == 0) {
            try {
                status = executor.prepare_kernel_round(request);
            } catch (...) {
                status = -1;
            }
        }
        if (!gate.publish_admission(ticket, request.allowed_cpus, request.execution_threads, status, wait)) return -1;
    }
    KernelRoundAdmission admission;
    if (!gate.wait_admission(ticket, &admission, wait)) return -1;
    int32_t status = replay_failed() ? -1 : admission.status;
    if (status == 0 && admission.execution_index >= 0) {
        const KernelThreadView thread{admission.execution_index, request.execution_threads};
        const auto &invocation = executor.kernel_invocation_;
        try {
            status = executor.execute(invocation.resident(), invocation.inputs(), &thread);
        } catch (...) {
            status = -1;
            executor.cancel_kernel_round();
        }
    }
    if (replay_failed()) status = -1;
    const auto arrival = gate.arrive(ticket, status);
    if (arrival == RoundArrival::Invalid) return -1;
    KernelFinalStatus result;
    if (arrival == RoundArrival::Finalizer) {
        // All execution threads have published their status before the native result.
        const int32_t sm_status = replay_failed() ? -1 : executor.kernel_status();
        const int32_t cleanup = 0;
        if (!gate.publish_final_status(
                ticket, sm_status, cleanup,
                [&](const KernelFinalStatus &final) noexcept {
                    if (executor.kernel_storage_attached_)
                        executor.kernel_storage_.publish_status(final.runtime_status, final.cleanup_status);
                }
            ) ||
            !gate.read_final_status(ticket, &result, wait))
            return -1;
    } else if (!gate.read_final_status(ticket, &result, wait)) {
        return -1;
    }
    if (out != nullptr) *out = result;
    const auto departure = gate.depart(ticket);
    if (departure == RoundDeparture::Invalid) return -1;
    if (departure == RoundDeparture::Last && result.cleanup_status == 0 && result.runtime_status == 0) {
        if (replay_failed()) return -1;
        executor.clear_kernel_round();
        if (!gate.complete_departure(ticket)) return -1;
    }
    // Any failed round retains the retiring gate and every borrowed argument;
    // a timeout is not proof that an AICore stopped reading the storage.
    return result.cleanup_status != 0 ? result.cleanup_status : result.runtime_status;
}

}  // namespace simpler::tmr
