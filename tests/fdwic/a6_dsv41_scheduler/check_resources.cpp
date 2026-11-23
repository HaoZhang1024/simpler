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
#include <charconv>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "record.h"
#include "resource_order.h"

namespace {
uint32_t positive_count(const char *text) {
    uint32_t value = 0;
    const std::string input(text);
    const auto result = std::from_chars(input.data(), input.data() + input.size(), value);
    if (result.ec != std::errc{} || result.ptr != input.data() + input.size() || value == 0)
        throw std::runtime_error("Resource counts must be positive integers");
    return value;
}
}  // namespace

int main(int argc, char **argv) {
    try {
        if (argc != 4) throw std::runtime_error("Usage: check-resources PLAN CLUSTERS AIVS_PER_CLUSTER");
        const uint32_t clusters = positive_count(argv[2]);
        const uint32_t vectors = positive_count(argv[3]);
        if (!simpler::percounter::make_resource_order({}, clusters, vectors))
            throw std::runtime_error("Expected one or two Vector lanes per cluster and a valid worker count");
        std::ifstream input(argv[1], std::ios::binary);
        if (!input) throw std::runtime_error("Could not open plan");
        const auto records = dsv41::read_records(input);
        const auto slice = dsv41::select_slice(records, 8, 35);
        std::ostringstream tasks_json;
        uint32_t tasks = 0, minimum_clusters = 1;
        uint64_t executions = 0;
        for (size_t i = slice.begin; i < slice.end; ++i) {
            const auto &h = records[i].header;
            if (h.operation != dsv41::Operation::SUBMIT) continue;
            const std::string prefix = "Task " + std::to_string(h.task_id) + ": ";
            if (h.block_num <= 0 || (h.sync_start != 0 && h.sync_start != 1))
                throw std::runtime_error(prefix + "invalid block count or sync_start");
            uint8_t mask = 0;
            for (uint32_t lane = 0; lane < 3; ++lane) {
                if (h.kernels[lane] < -1) throw std::runtime_error(prefix + "invalid kernel ID");
                if (h.kernels[lane] >= 0) mask |= static_cast<uint8_t>(1U << lane);
            }
            const uint32_t available_mask = (1U << (vectors + 1)) - 1;
            if (mask == 0 || mask == 4 || (mask & ~available_mask) != 0)
                throw std::runtime_error(
                    prefix + "kernel mask " + std::to_string(mask) + " is incompatible with the selected topology"
                );
            const uint32_t blocks = static_cast<uint32_t>(h.block_num);
            const uint32_t width_per_cluster = mask == 2 ? vectors : 1;
            const uint32_t required = h.sync_start ? (blocks - 1) / width_per_cluster + 1 : 1;
            if (required > clusters)
                throw std::runtime_error(
                    prefix + "sync_start requires " + std::to_string(required) + " clusters; available " +
                    std::to_string(clusters)
                );
            minimum_clusters = std::max(minimum_clusters, required);
            simpler::percounter::ResourceOrderTask task;
            task.active_mask = mask;
            task.blocks = blocks;
            task.sync = h.sync_start != 0;
            const auto plan = simpler::percounter::make_resource_order({task}, clusters, vectors);
            if (!plan) throw std::runtime_error(prefix + "resource model rejected the task");
            executions += uint64_t{blocks} * static_cast<uint32_t>(__builtin_popcount(mask));
            if (tasks++ != 0) tasks_json << ',';
            tasks_json << "{\"id\":" << h.task_id << ",\"blocks\":" << blocks
                       << ",\"mask\":" << static_cast<uint32_t>(mask) << ",\"sync_start\":" << h.sync_start
                       << ",\"isolated_waves\":" << plan->duration << '}';
        }
        if (tasks != 16) throw std::runtime_error("Expected 16 SWA compute tasks");
        std::cout << "{\"runtime_executed\":false,\"scope\":\"per-task resource capacity\",\"clusters\":" << clusters
                  << ",\"aivs_per_cluster\":" << vectors << ",\"tasks\":" << tasks << ",\"executions\":" << executions
                  << ",\"minimum_clusters\":" << minimum_clusters << ",\"task_resources\":[" << tasks_json.str()
                  << "]}\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
