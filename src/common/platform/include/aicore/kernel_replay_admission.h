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

#include "task_interface/tmr_kernel_control.h"

// This line is read-only on AICore. Invalidate only that clean line before
// admission: a whole-cache writeback could flush unrelated, failed-round data.
__aicore__ inline uint64_t read_kernel_replay_epoch(__gm__ simpler::tmr::TmrReplayAdmission *admission) {
    dcci(admission, SINGLE_CACHE_LINE);
    const uint64_t epoch = admission->ready_epoch;
    if ((epoch & 1) == 0 || admission->sequence != epoch || read_aicore_teardown_control(&admission->fault) != 0)
        return 0;
    return epoch;
}
