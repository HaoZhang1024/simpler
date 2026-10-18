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

#include "kernel_binder_test_support.h"
#include <algorithm>

namespace kernel_binder_test {
namespace {
int cancel_unpaired(void *context, void *) noexcept {
    auto &fake = *static_cast<Fake *>(context);
    ++fake.cancellations;
    // Cancellation is queued while the owner still holds submission admission.
    EXPECT_FALSE(fake.poisoned);
    return fake.cancellation_error;
}

template <typename Ops>
auto install_cancellation(Ops &ops, int) -> decltype(ops.cancel_unpaired_aicore = cancel_unpaired, void()) {
    ops.cancel_unpaired_aicore = cancel_unpaired;
}
template <typename Ops>
void install_cancellation(Ops &, long) {}
}  // namespace

TEST(KernelBinder, DefiniteUnpairedCoreReceivesCancellationWithoutClaimingCompletion) {
    Fixture f;
    f.initialize();
    f.fake.fail_at = 7;  // AICore submitted; AICPU launch has not been called.
    auto ops = f.fake.ops();
    install_cancellation(ops, 0);
    const auto result = launch_bound_kernel(f.binding, ptr(100), f.fake.gate(), ops);
    EXPECT_EQ(result.status, -1707);
    EXPECT_EQ(f.fake.cancellations, 1);
    EXPECT_TRUE(f.fake.poisoned);
    EXPECT_FALSE(result.tail_recorded);
}

TEST(KernelBinder, CancellationErrorPreservesTheOriginalEnqueueErrorAndPoison) {
    Fixture f;
    f.initialize();
    f.fake.fail_at = 7;
    f.fake.cancellation_error = -88;
    auto ops = f.fake.ops();
    install_cancellation(ops, 0);
    const auto result = launch_bound_kernel(f.binding, ptr(100), f.fake.gate(), ops);
    EXPECT_EQ(result.status, -1707);
    EXPECT_EQ(result.cleanup_status, -88);
    EXPECT_EQ(f.fake.cancellations, 1);
    EXPECT_TRUE(f.fake.poisoned);
}

TEST(KernelBinder, UncertainCpuLaunchFailureCannotUsePreWindowCancellation) {
    Fixture f;
    f.initialize();
    f.fake.fail_at = 8;  // AICPU API has been attempted: acceptance is unconfirmed.
    auto ops = f.fake.ops();
    install_cancellation(ops, 0);
    const auto result = launch_bound_kernel(f.binding, ptr(100), f.fake.gate(), ops);
    EXPECT_EQ(result.status, -1708);
    EXPECT_EQ(f.fake.cancellations, 0);
    EXPECT_TRUE(f.fake.poisoned);
}

TEST(KernelBinder, ThreeStreamSuccessAndSteadyStateHaveExactTrace) {
    Fixture f;
    ASSERT_NO_FATAL_FAILURE(f.initialize());
    ASSERT_EQ(f.launch().status, 0);
    EXPECT_EQ(f.fake.trace, success);
    for (int i = 0; i < 10; ++i) {
        f.fake.clear_trace();
        const auto result = f.launch();
        EXPECT_EQ(result.status, 0);
        EXPECT_TRUE(result.tail_recorded);
        EXPECT_EQ(f.fake.trace, success);
    }
    EXPECT_EQ(f.fake.queries, 0);
    EXPECT_EQ(f.fake.acquisitions, 11);
    EXPECT_EQ(f.fake.finishes, 11);
}

TEST(KernelBinder, StreamSwitchQueriesButNeverWaitsOldTail) {
    Fixture f;
    ASSERT_NO_FATAL_FAILURE(f.initialize());
    ASSERT_EQ(f.launch().status, 0);
    f.fake.clear_trace();
    f.fake.complete = false;
    EXPECT_NE(f.launch(ptr(101)).status, 0);
    EXPECT_TRUE(f.fake.trace.empty());
    EXPECT_FALSE(f.fake.poisoned);
    f.fake.complete = true;
    f.fake.query_error = -22;
    EXPECT_EQ(f.launch(ptr(101)).status, -22);
    EXPECT_TRUE(f.fake.trace.empty());
    f.fake.query_error = 0;
    EXPECT_EQ(f.launch(ptr(101)).status, 0);
    EXPECT_EQ(f.fake.queries, 3);
    EXPECT_EQ(f.fake.trace, success);
    f.fake.clear_trace();
    EXPECT_EQ(f.launch(ptr(101)).status, 0);
    EXPECT_EQ(f.fake.queries, 3);
}

TEST(KernelBinder, ReadOnlyRejectionsReleaseOwnerAndPreservePrepareDependency) {
    for (int fault = 0; fault < 10; ++fault) {
        SCOPED_TRACE(fault);
        Fixture f;
        f.initialize();
        auto gate = f.fake.gate();
        auto ops = f.fake.ops();
        auto binding = f.binding;
        void *caller = ptr(100);
        switch (fault) {
        case 0:
            f.fake.validation_error = -1234;
            break;
        case 1:
            f.fake.ready = false;
            break;
        case 2:
            f.fake.frozen = false;
            break;
        case 3:
            f.fake.handles.aicpu_done = nullptr;
            break;
        case 4:
            f.fake.handles.aicpu_done = ptr(5);
            break;
        case 5:
            caller = ptr(1);
            break;
        case 6:
            binding.packet_bytes = 0;
            break;
        case 7:
            gate.acquire = nullptr;
            break;
        case 8:
            gate.finish = nullptr;
            break;
        case 9:
            ops.launch_aicore = nullptr;
            break;
        }
        EXPECT_NE(launch_bound_kernel(binding, caller, gate, ops).status, 0);
        EXPECT_TRUE(f.fake.trace.empty());
        EXPECT_FALSE(f.fake.poisoned);
        EXPECT_EQ(f.fake.acquisitions, f.fake.finishes);
        EXPECT_EQ(f.fake.previous_caller, 0u);
        f.fake.validation_error = 0;
        f.fake.ready = f.fake.frozen = true;
        f.fake.handles.aicpu_done = ptr(6);
        EXPECT_EQ(f.launch().status, 0);
        EXPECT_EQ(f.fake.trace, success);
    }
}

TEST(KernelBinder, EveryEnqueueFailurePoisonsWithExactSubmissionTrace) {
    for (int fail = 1; fail <= static_cast<int>(success.size()); ++fail) {
        SCOPED_TRACE(fail);
        Fixture f;
        ASSERT_NO_FATAL_FAILURE(f.initialize());
        f.fake.fail_at = fail;
        const auto result = f.launch();
        EXPECT_EQ(result.status, -1700 - fail);
        EXPECT_EQ(result.failed_step, success[fail - 1]);
        auto expected = std::vector<Step>(success.begin(), success.begin() + fail);
        EXPECT_EQ(f.fake.trace, expected);
        EXPECT_TRUE(f.fake.poisoned);
        EXPECT_EQ(f.fake.runtime_error, result.status);
        f.fake.clear_trace();
        EXPECT_NE(f.launch().status, 0);
        EXPECT_TRUE(f.fake.trace.empty());
        EXPECT_EQ(f.fake.acquisitions, f.fake.finishes);
    }
}

TEST(KernelBinder, PartialLaunchFailureStopsWithoutClaimingQuiescence) {
    for (int primary : {7, 8}) {
        Fixture f;
        ASSERT_NO_FATAL_FAILURE(f.initialize());
        f.fake.fail_at = primary;
        const auto result = f.launch();
        EXPECT_EQ(result.status, -1700 - primary);
        EXPECT_EQ(result.cleanup_status, 0);
        EXPECT_FALSE(result.tail_recorded);
        EXPECT_EQ(f.fake.calls, primary);
        EXPECT_TRUE(f.fake.poisoned);
    }
}

TEST(KernelBinder, ConcurrentHostLaunchIsRejectedWithoutTouchingArgs) {
    Fixture f;
    ASSERT_NO_FATAL_FAILURE(f.initialize());
    std::promise<void> entered, release;
    f.fake.entered = &entered;
    f.fake.release = release.get_future().share();
    auto first = std::async(std::launch::async, [&] {
        return f.launch();
    });
    entered.get_future().wait();
    auto second = f.launch();
    EXPECT_NE(second.status, 0);
    EXPECT_FALSE(second.enqueue_started);
    release.set_value();
    EXPECT_EQ(first.get().status, 0);
    EXPECT_EQ(f.fake.acquisitions, 1);
    EXPECT_EQ(f.fake.finishes, 1);
}
}  // namespace kernel_binder_test

TEST(KernelLaunchBinderReplay, EpilogueIsOrderedAfterBothNativeGroupsAndBeforeCallerCompletion) {
    kernel_binder_test::Fixture f;
    f.initialize();
    auto ops = f.fake.ops();
    ops.finish_replay = [](void *context, void *) noexcept {
        return static_cast<kernel_binder_test::Fake *>(context)->append(
            simpler::kernel_launch::KernelLaunchStep::FinishReplay
        );
    };
    auto result =
        simpler::kernel_launch::launch_bound_kernel(f.binding, kernel_binder_test::ptr(100), f.fake.gate(), ops);
    ASSERT_EQ(result.status, 0);
    const auto &trace = f.fake.trace;
    auto join = std::find(trace.begin(), trace.end(), simpler::kernel_launch::KernelLaunchStep::JoinAicore);
    auto finish = std::find(trace.begin(), trace.end(), simpler::kernel_launch::KernelLaunchStep::FinishReplay);
    auto caller = std::find(trace.begin(), trace.end(), simpler::kernel_launch::KernelLaunchStep::AicpuDone);
    EXPECT_LT(join, finish);
    EXPECT_LT(finish, caller);
}
