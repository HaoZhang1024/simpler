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

#include "aicpu/platform_regs.h"

int32_t platform_retire_aicore_group(const AicoreExitTarget *, size_t count, uint64_t, bool *released) {
    if (released != nullptr) {
        for (size_t i = 0; i < count; ++i)
            released[i] = true;
    }
    return 0;
}

int32_t platform_retire_aicore_current_ack_group(
    const AicoreExitTarget *targets, size_t count, uint64_t deadline, bool *released
) {
    return platform_retire_aicore_group(targets, count, deadline, released);
}
