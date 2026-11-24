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

#include <array>
#include <cstdint>
#include <gtest/gtest.h>

#include "aicpu/platform_regs.h"

namespace {

TEST(PercounterIpcRegisters, CommandAndAcknowledgementUseSeparate64BitWords) {
    constexpr size_t ipc0 = 0x5500 / sizeof(uint64_t);
    constexpr size_t ipc4 = 0x5520 / sizeof(uint64_t);
    std::array<uint64_t, ipc4 + 2> window{};
    window.fill(UINT64_MAX);
    const auto base = reinterpret_cast<uint64_t>(window.data());

    write_reg(base, RegId::DATA_MAIN_BASE, 0x123456787ffffffdULL);
    EXPECT_EQ(window[ipc0], 0x123456787ffffffdULL);
    EXPECT_EQ(window[ipc0 + 1], UINT64_MAX);
    EXPECT_EQ(window[ipc4], UINT64_MAX);
    EXPECT_EQ(read_reg(base, RegId::DATA_MAIN_BASE), window[ipc0]);

    window[ipc4] = 0x87654321a5a5a5a5ULL;
    EXPECT_EQ(read_reg(base, RegId::COND), window[ipc4]);
    write_reg(base, RegId::DATA_MAIN_BASE, AICORE_EXIT_SIGNAL);
    EXPECT_EQ(window[ipc0], static_cast<uint64_t>(AICORE_EXIT_SIGNAL));
    EXPECT_EQ(window[ipc4], 0x87654321a5a5a5a5ULL);
}

}  // namespace
