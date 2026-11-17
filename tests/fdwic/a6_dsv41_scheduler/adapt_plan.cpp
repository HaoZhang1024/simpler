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
#include <fstream>
#include <iostream>
#include <stdexcept>

#include "record.h"  // NOLINT(build/include_subdir): shared capture format, supplied by the compiler include path.

int main(int argc, char **argv) {
    try {
        if (argc != 3) throw std::runtime_error("Usage: adapt-plan input-plan output-plan");
        std::ifstream input(argv[1], std::ios::binary);
        auto records = dsv41::read_records(input);
        const auto slice = dsv41::select_slice(records, 8, 35);
        int changed = 0;
        for (size_t i = slice.begin; i < slice.end; ++i) {
            auto &h = records[i].header;
            if (h.operation != dsv41::Operation::SUBMIT || (h.task_id != 22 && h.task_id != 28)) continue;
            const bool attention = h.task_id == 22;
            const int aic = attention ? 18 : 21;
            const int aiv = attention ? 19 : 22;
            const int blocks = attention ? 24 : 32;
            if (h.kernels[0] != aic || h.kernels[1] != aiv || h.kernels[2] != aiv || h.block_num != blocks) {
                throw std::runtime_error("Expected original SWA 1C2V task; refuse a modified or already adapted plan");
            }
            h.kernels[2] = -1;
            if (attention) h.block_num *= 2;
            ++changed;
        }
        if (changed != 2) throw std::runtime_error("Expected both SWA MIX tasks");
        std::ofstream output(argv[2], std::ios::binary);
        dsv41::write(output, dsv41::record_magic);
        dsv41::write(output, uint64_t{sizeof(dsv41::Operand)});
        for (const auto &record : records) {
            dsv41::write(output, record.header);
            for (const auto &operand : record.tensors)
                dsv41::write(output, operand);
            for (const auto scalar : record.scalars)
                dsv41::write(output, scalar);
            for (const auto dependency : record.dependencies)
                dsv41::write(output, dependency);
        }
        output.close();
        if (!output) throw std::runtime_error("Failed to finish converted plan");
        std::cout << "Converted t22 to 48 x 1C1V and t28 to 32 x 1C1V\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
