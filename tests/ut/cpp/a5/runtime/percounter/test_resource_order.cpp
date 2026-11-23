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

#include "resource_order.h"

#include <gtest/gtest.h>
#include <array>

namespace {
using namespace simpler::percounter;

TEST(PercounterResourceOrder, NarrowReadySyncUsesCapacityWhileWiderSyncWaits) {
    std::vector<ResourceOrderTask> tasks(3);
    for (auto &node : tasks)
        node.active_mask = 2;
    tasks[0].blocks = 2;
    tasks[1].blocks = 3;
    tasks[1].sync = true;
    tasks[2].blocks = 2;
    tasks[2].sync = true;
    const auto plan = make_resource_order(tasks, 2, 2);
    ASSERT_TRUE(plan.has_value());
    const std::vector<uint32_t> order{0, 2, 1};
    EXPECT_EQ(plan->tasks, order);
    EXPECT_EQ(plan->first_start[2], 0U);
    EXPECT_EQ(plan->first_start[1], 1U);
    EXPECT_EQ(plan->duration, 2U);
}

TEST(PercounterResourceOrder, MixUsesOnlyItsActualParticipants) {
    for (uint8_t mix : {uint8_t{5}, uint8_t{6}}) {
        std::vector<ResourceOrderTask> tasks(2);
        tasks[0].active_mask = mix == 5 ? 2 : 1;
        tasks[1].active_mask = mix;
        const auto plan = make_resource_order(tasks, 1, 2);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->first_start[0], 0U);
        EXPECT_EQ(plan->first_start[1], 0U);
        EXPECT_EQ(plan->duration, 1U);
    }
}

TEST(PercounterResourceOrder, GraphEnvelopeReservesUsedTypesAndReleasesSuccessors) {
    std::vector<ResourceOrderTask> tasks(3);
    tasks[0].active_mask = 1;
    tasks[1].active_mask = 2;
    tasks[1].reserve_types = true;
    tasks[1].duration = tasks[1].depth = 3;
    tasks[2].active_mask = 1;
    tasks[2].predecessors = {1};
    const auto vector_body = make_resource_order(tasks, 2, 2);
    ASSERT_TRUE(vector_body.has_value());
    EXPECT_EQ(vector_body->first_start[0], 0U);
    EXPECT_EQ(vector_body->first_start[1], 0U);
    EXPECT_EQ(vector_body->first_start[2], 3U);
    EXPECT_EQ(vector_body->duration, 4U);
    tasks[1].active_mask = 3;
    const auto mixed_body = make_resource_order(tasks, 2, 2);
    ASSERT_TRUE(mixed_body.has_value());
    EXPECT_EQ(mixed_body->first_start[0], 3U);
    EXPECT_EQ(mixed_body->first_start[1], 0U);
    EXPECT_EQ(mixed_body->first_start[2], 3U);
    EXPECT_EQ(mixed_body->duration, 4U);
}

TEST(PercounterResourceOrder, DeclaredTopologyControlsVirtualCapacity) {
    std::vector<ResourceOrderTask> tasks(2);
    tasks[0].active_mask = tasks[1].active_mask = 1;
    tasks[0].blocks = 2;
    for (uint32_t clusters = 1; clusters <= 3; ++clusters) {
        const auto plan = make_resource_order(tasks, clusters, 2);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->first_start[1], 3U - clusters);
    }
}

TEST(PercounterResourceOrder, RejectsInvalidTopologyEdgesAndTimeOverflow) {
    std::vector<ResourceOrderTask> tasks(2);
    tasks[0].active_mask = tasks[1].active_mask = 1;
    EXPECT_FALSE(make_resource_order(tasks, 0, 2).has_value());
    tasks[0].predecessors = {1};
    EXPECT_FALSE(make_resource_order(tasks, 2, 2).has_value());
    tasks[0].predecessors.clear();
    tasks[0].sync = true;
    tasks[0].blocks = 3;
    EXPECT_FALSE(make_resource_order(tasks, 2, 2).has_value());
    tasks[0].sync = false;
    tasks[0].blocks = 1;
    tasks[0].reserve_types = true;
    tasks[0].duration = UINT64_MAX;
    tasks[1].predecessors = {0};
    EXPECT_FALSE(make_resource_order(tasks, 2, 2).has_value());
}

TEST(PercounterResourceOrder, EverySmallDagKeepsEdgesAndWholeSyncStarts) {
    const std::array<uint8_t, 6> masks{{1, 2, 3, 5, 6, 7}};
    for (uint32_t clusters : {1U, 2U}) {
        for (uint32_t graph = 0; graph < 64; ++graph) {
            for (uint32_t shape = 0; shape < masks.size(); ++shape) {
                std::vector<ResourceOrderTask> tasks(4);
                uint32_t edge = 0;
                for (uint32_t id = 0; id < tasks.size(); ++id) {
                    tasks[id].active_mask = masks[(shape + id) % masks.size()];
                    tasks[id].blocks = id % 2 + 1;
                    tasks[id].sync = clusters == 2 && id % 2 != 0;
                    for (uint32_t producer = 0; producer < id; ++producer, ++edge)
                        if (graph & (1U << edge)) tasks[id].predecessors.push_back(producer);
                }
                const auto plan = make_resource_order(tasks, clusters, 2);
                ASSERT_TRUE(plan.has_value());
                ASSERT_EQ(plan->tasks.size(), tasks.size());
                std::array<uint32_t, 4> rank{};
                uint32_t seen = 0;
                for (uint32_t position = 0; position < plan->tasks.size(); ++position) {
                    ASSERT_LT(plan->tasks[position], rank.size());
                    ASSERT_EQ(seen & (1U << plan->tasks[position]), 0U);
                    seen |= 1U << plan->tasks[position];
                    rank[plan->tasks[position]] = position;
                }
                EXPECT_EQ(seen, 15U);
                for (uint32_t id = 0; id < tasks.size(); ++id) {
                    EXPECT_GT(plan->finish[id], plan->first_start[id]);
                    if (tasks[id].sync) EXPECT_EQ(plan->finish[id], plan->first_start[id] + 1);
                    for (uint32_t producer : tasks[id].predecessors) {
                        EXPECT_LT(rank[producer], rank[id]);
                        EXPECT_LE(plan->finish[producer], plan->first_start[id]);
                    }
                }
            }
        }
    }
}

TEST(PercounterResourceOrder, SingleVectorUsesMultipleWavesAndReleasesWorkers) {
    std::vector<ResourceOrderTask> tasks(2);
    tasks[0].active_mask = tasks[1].active_mask = 2;
    tasks[0].blocks = 5;
    tasks[1].predecessors = {0};
    for (uint32_t vectors : {1U, 2U}) {
        const auto plan = make_resource_order(tasks, 2, vectors);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->finish[0], vectors == 1 ? 3U : 2U);
        EXPECT_EQ(plan->first_start[1], plan->finish[0]);
        EXPECT_EQ(plan->duration, vectors == 1 ? 4U : 3U);
    }
}

TEST(PercounterResourceOrder, SingleVectorMixContendsWithVectorButCubeCanOverlap) {
    std::vector<ResourceOrderTask> tasks(2);
    tasks[0].active_mask = 2;
    tasks[1].active_mask = 3;
    const auto mix = make_resource_order(tasks, 1, 1);
    ASSERT_TRUE(mix.has_value());
    EXPECT_EQ(mix->first_start[0], 0U);
    EXPECT_EQ(mix->first_start[1], 1U);
    EXPECT_EQ(mix->duration, 2U);
    tasks[1].active_mask = 1;
    const auto cube = make_resource_order(tasks, 1, 1);
    ASSERT_TRUE(cube.has_value());
    EXPECT_EQ(cube->first_start[1], 0U);
    EXPECT_EQ(cube->duration, 1U);
}

TEST(PercounterResourceOrder, SingleVectorSyncRequiresWholeClusterCapacity) {
    for (uint8_t mask : {1, 2, 3}) {
        std::vector<ResourceOrderTask> tasks(1);
        tasks[0].active_mask = mask;
        tasks[0].sync = true;
        tasks[0].blocks = 2;
        const auto fits = make_resource_order(tasks, 2, 1);
        ASSERT_TRUE(fits.has_value());
        EXPECT_EQ(fits->duration, 1U);
        tasks[0].blocks = 3;
        EXPECT_FALSE(make_resource_order(tasks, 2, 1).has_value());
        tasks[0].sync = false;
        const auto waves = make_resource_order(tasks, 2, 1);
        ASSERT_TRUE(waves.has_value());
        EXPECT_EQ(waves->duration, 2U);
    }
    std::vector<ResourceOrderTask> tasks(3);
    for (auto &node : tasks)
        node.active_mask = 2;
    tasks[1].blocks = 2;
    tasks[1].sync = tasks[2].sync = true;
    const auto plan = make_resource_order(tasks, 2, 1);
    ASSERT_TRUE(plan.has_value());
    EXPECT_EQ(plan->tasks, (std::vector<uint32_t>{0, 2, 1}));
    EXPECT_EQ(plan->first_start[2], 0U);
    EXPECT_EQ(plan->first_start[1], 1U);
}

TEST(PercounterResourceOrder, SingleVectorEnvelopeReservesTypeAndReleasesIt) {
    for (uint8_t mask : {2, 3}) {
        std::vector<ResourceOrderTask> tasks(3);
        tasks[0].active_mask = mask;
        tasks[0].reserve_types = true;
        tasks[0].duration = tasks[0].depth = 3;
        tasks[1].active_mask = 1;
        tasks[2].active_mask = 2;
        const auto plan = make_resource_order(tasks, 2, 1);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->first_start[0], 0U);
        EXPECT_EQ(plan->first_start[1], mask == 2 ? 0U : 3U);
        EXPECT_EQ(plan->first_start[2], 3U);
        EXPECT_EQ(plan->duration, 4U);
    }
    std::vector<ResourceOrderTask> tasks(2);
    tasks[0].active_mask = 3;
    tasks[0].reserve_types = true;
    tasks[0].duration = 0;
    tasks[1].active_mask = 3;
    tasks[1].predecessors = {0};
    const auto immediate = make_resource_order(tasks, 1, 1);
    ASSERT_TRUE(immediate.has_value());
    EXPECT_EQ(immediate->first_start[1], 0U);
    EXPECT_EQ(immediate->duration, 1U);
}

TEST(PercounterResourceOrder, RejectsAbsentVectorLaneAndInvalidVectorCounts) {
    std::vector<ResourceOrderTask> tasks(1);
    for (uint8_t mask : {4, 5, 6, 7, 8, 255}) {
        tasks[0].active_mask = mask;
        for (bool reserve : {false, true}) {
            tasks[0].reserve_types = reserve;
            EXPECT_FALSE(make_resource_order(tasks, 2, 1).has_value());
        }
    }
    for (uint32_t vectors : {0U, 3U, UINT32_MAX})
        EXPECT_FALSE(make_resource_order({}, 1, vectors).has_value());
    for (uint32_t vectors : {1U, 2U}) {
        EXPECT_FALSE(make_resource_order({}, 0, vectors).has_value());
        EXPECT_FALSE(make_resource_order({}, UINT32_MAX / (vectors + 1) + 1, vectors).has_value());
        EXPECT_TRUE(make_resource_order({}, 1, vectors).has_value());
    }
}

TEST(PercounterResourceOrder, SingleVectorSmallDagsPreserveDependenciesAndSync) {
    for (uint32_t clusters : {1U, 2U}) {
        for (uint32_t graph = 0; graph < 64; ++graph) {
            for (uint32_t shape = 0; shape < 81; ++shape) {
                std::vector<ResourceOrderTask> tasks(4);
                uint32_t choices = shape, edge = 0;
                for (uint32_t id = 0; id < tasks.size(); ++id) {
                    tasks[id].active_mask = 1 + choices % 3;
                    choices /= 3;
                    tasks[id].sync = id % 2 != 0;
                    tasks[id].blocks = tasks[id].sync ? clusters : clusters + 1;
                    for (uint32_t p = 0; p < id; ++p, ++edge)
                        if (graph & (1U << edge)) tasks[id].predecessors.push_back(p);
                }
                const auto plan = make_resource_order(tasks, clusters, 1);
                ASSERT_TRUE(plan.has_value());
                ASSERT_EQ(plan->tasks.size(), 4U);
                auto sorted = plan->tasks;
                std::sort(sorted.begin(), sorted.end());
                EXPECT_EQ(sorted, (std::vector<uint32_t>{0, 1, 2, 3}));
                for (uint32_t id = 0; id < tasks.size(); ++id) {
                    EXPECT_GT(plan->finish[id], plan->first_start[id]);
                    if (tasks[id].sync) EXPECT_EQ(plan->finish[id], plan->first_start[id] + 1);
                    for (uint32_t p : tasks[id].predecessors)
                        EXPECT_LE(plan->finish[p], plan->first_start[id]);
                }
            }
        }
    }
}

TEST(PercounterResourceOrder, SwaSyncMixNeedsFortyEightAvailablePairs) {
    // The converted SWA t22 keeps sync_start and doubles its block count.
    std::vector<ResourceOrderTask> tasks(1);
    tasks[0].active_mask = 3;
    tasks[0].blocks = 48;
    tasks[0].sync = true;
    EXPECT_FALSE(make_resource_order(tasks, 47, 1).has_value());
    for (uint32_t clusters : {48U, 54U}) {
        const auto plan = make_resource_order(tasks, clusters, 1);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->first_start[0], 0U);
        EXPECT_EQ(plan->finish[0], 1U);
    }
}

TEST(PercounterResourceOrder, SwaOrdinaryVectorWidthsRunInWaves) {
    // SWA t9, t25 and t35 are ordinary Vector tasks, without sync_start.
    for (uint32_t blocks : {64U, 80U}) {
        std::vector<ResourceOrderTask> tasks(2);
        tasks[0].active_mask = 2;
        tasks[0].blocks = blocks;
        tasks[1].active_mask = 3;
        tasks[1].blocks = 48;
        tasks[1].sync = true;
        tasks[1].predecessors = {0};
        const auto plan = make_resource_order(tasks, 54, 1);
        ASSERT_TRUE(plan.has_value());
        EXPECT_EQ(plan->finish[0], 2U);
        EXPECT_EQ(plan->first_start[1], 2U);
        EXPECT_EQ(plan->finish[1], 3U);
    }
}

}  // namespace
