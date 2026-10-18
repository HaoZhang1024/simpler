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
#include <atomic>
#include <thread>
#include <vector>
#include "tensormap_and_ringbuffer/kernel_replay_admission.h"

namespace {
using namespace simpler::tmr;

TEST(KernelReplayAdmission, SameCapturedStateMintsDistinctExecutionIdentities) {
    TmrReplayAdmission state{};
    uint64_t last = 0;
    for (int replay = 0; replay < 1000; ++replay) {
        const auto epoch = begin_replay(state, [] {
            return true;
        });
        ASSERT_GT(epoch, last);
        ASSERT_EQ(current_replay(state), epoch);
        ASSERT_TRUE(end_replay(state, epoch));
        EXPECT_EQ(current_replay(state), 0u);
        last = epoch;
    }
}

TEST(KernelReplayAdmission, BusyRejectDoesNotClearAndCannotBorrowActiveIdentity) {
    TmrReplayAdmission state{};
    uint64_t sentinel = 0x1710;
    const auto epoch = begin_replay(state, [] {
        return true;
    });
    ASSERT_NE(epoch, 0u);
    EXPECT_EQ(
        begin_replay(
            state,
            [&] {
                sentinel = 0;
                return true;
            }
        ),
        0u
    );
    EXPECT_EQ(sentinel, 0x1710u);
    EXPECT_EQ(current_replay(state), 0u);
    EXPECT_FALSE(end_replay(state, epoch));
    EXPECT_EQ(
        begin_replay(
            state,
            [&] {
                sentinel = 0;
                return true;
            }
        ),
        0u
    );
    EXPECT_EQ(sentinel, 0x1710u);
}

TEST(KernelReplayAdmission, FailedR1BlocksQueuedR2R3EvenIfTransportExecutesTheirNodes) {
    TmrReplayAdmission state{};
    const auto r1 = begin_replay(state, [] {
        return true;
    });
    ASSERT_NE(r1, 0u);
    poison_replay(state);
    uint64_t clear = 0, open = 0, payload = 0;
    for (int round : {2, 3}) {
        (void)round;
        EXPECT_EQ(
            begin_replay(
                state,
                [&] {
                    ++clear;
                    return true;
                }
            ),
            0u
        );
        if (current_replay(state)) {
            ++open;
            ++payload;
        }
    }
    EXPECT_EQ(clear, 0u);
    EXPECT_EQ(open, 0u);
    EXPECT_EQ(payload, 0u);
    EXPECT_EQ(state.sequence, r1);
}

TEST(KernelReplayAdmission, ClearFailureRetainsLeaseAndNeverPublishesIdentity) {
    TmrReplayAdmission state{};
    EXPECT_EQ(
        begin_replay(
            state,
            [] {
                return false;
            }
        ),
        0u
    );
    EXPECT_EQ(state.sequence, 1u);
    EXPECT_EQ(state.ready_epoch, 0u);
    EXPECT_NE(state.fault, 0u);
}

TEST(KernelReplayAdmission, DelayedOldEpilogueCannotReleaseNewReplay) {
    TmrReplayAdmission state{};
    const auto old = begin_replay(state, [] {
        return true;
    });
    ASSERT_TRUE(end_replay(state, old));
    const auto next = begin_replay(state, [] {
        return true;
    });
    ASSERT_NE(next, old);
    EXPECT_FALSE(end_replay(state, old));
    EXPECT_EQ(state.sequence, next);
    EXPECT_EQ(current_replay(state), 0u);
}

TEST(KernelReplayAdmission, IdentityExhaustionNeverWrapsOrClears) {
    TmrReplayAdmission state{};
    state.sequence = UINT64_MAX - 1;
    bool cleared = false;
    EXPECT_EQ(
        begin_replay(
            state,
            [&] {
                cleared = true;
                return true;
            }
        ),
        0u
    );
    EXPECT_FALSE(cleared);
    EXPECT_EQ(state.sequence, UINT64_MAX - 1);
    EXPECT_NE(state.fault, 0u);
}

TEST(KernelReplayAdmission, ConcurrentPreludesHaveAtMostOneClearAndPoisonAllSuccessors) {
    for (int trial = 0; trial < 200; ++trial) {
        TmrReplayAdmission state{};
        std::atomic<int> ready{0}, clears{0};
        std::atomic<bool> start{false};
        std::vector<std::thread> callers;
        for (int i = 0; i < 4; ++i)
            callers.emplace_back([&] {
                ++ready;
                while (!start.load(std::memory_order_acquire))
                    std::this_thread::yield();
                begin_replay(state, [&] {
                    ++clears;
                    return true;
                });
            });
        while (ready.load() != 4)
            std::this_thread::yield();
        start.store(true, std::memory_order_release);
        for (auto &thread : callers)
            thread.join();
        EXPECT_LE(clears.load(), 1);
        EXPECT_EQ(current_replay(state), 0u);
        EXPECT_NE(state.fault, 0u);
    }
}
}  // namespace
