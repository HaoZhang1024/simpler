# Copyright (c) PyPTO Contributors.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------


add_a2a3_runtime_test(test_kernel_scheduler_retirement a2a3/test_kernel_scheduler_retirement.cpp
    ${A2A3_RUNTIME_DIR}/scheduler/scheduler_cold_path.cpp
    ${A2A3_RUNTIME_DIR}/scheduler/scheduler_dispatch.cpp
    ${A2A3_RUNTIME_DIR}/scheduler/scheduler_completion.cpp
    ${A2A3_RUNTIME_DIR}/shared/runtime.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/shared/aicpu/pmu_collector_aicpu.cpp)
target_compile_options(test_kernel_scheduler_retirement PRIVATE -fno-access-control)
target_sources(test_kernel_scheduler_retirement PRIVATE
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/aicpu_device_config.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/args_dump_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/chip_swimlane_collector_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/device_phase_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/sim/aicpu/inner_platform_regs.cpp)
add_executable(test_kernel_gm_ack
    a2a3/test_kernel_gm_ack.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/runtime/tensormap_and_ringbuffer/aicore/aicore_executor.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/shared/aicpu/platform_regs.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/sim/aicpu/inner_platform_regs.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu/device_time.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu/cache_ops.cpp)
target_include_directories(test_kernel_gm_ack PRIVATE
    ${GTEST_INCLUDE_DIRS}
    ${A2A3_RUNTIME_DIR}
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/runtime/tensormap_and_ringbuffer/common
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/runtime/tensormap_and_ringbuffer/orchestration
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/sim/aicore
    ${CMAKE_SOURCE_DIR}/../../../src/a2a3/platform/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/task_interface
    ${CMAKE_SOURCE_DIR}/../../../src/common/log/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/host_build_graph
    ${CMAKE_SOURCE_DIR}/../../../src/common)
target_link_libraries(test_kernel_gm_ack PRIVATE ${GTEST_MAIN_LIB} ${GTEST_LIB} pthread)
add_test(NAME test_kernel_gm_ack COMMAND test_kernel_gm_ack)
set_tests_properties(test_kernel_gm_ack test_kernel_scheduler_retirement PROPERTIES TIMEOUT 45)

add_a5_runtime_test(test_a5_kernel_scheduler_retirement a2a3/test_kernel_scheduler_retirement.cpp)
target_sources(test_a5_kernel_scheduler_retirement PRIVATE
    ${A5_RUNTIME_DIR}/scheduler/scheduler_cold_path.cpp
    ${A5_RUNTIME_DIR}/scheduler/scheduler_dispatch.cpp
    ${A5_RUNTIME_DIR}/scheduler/scheduler_completion.cpp
    ${A5_RUNTIME_DIR}/shared/runtime.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a5/platform/shared/aicpu/pmu_collector_aicpu.cpp)
target_compile_options(test_a5_kernel_scheduler_retirement PRIVATE -fno-access-control)
target_sources(test_a5_kernel_scheduler_retirement PRIVATE
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/aicpu_device_config.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/args_dump_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/chip_swimlane_collector_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/shared/aicpu/device_phase_aicpu.cpp
    ${CMAKE_SOURCE_DIR}/a5/kernel_retirement_stubs.cpp)

add_executable(test_a5_kernel_gm_ack
    a5/test_kernel_gm_ack.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a5/runtime/tensormap_and_ringbuffer/aicore/aicore_executor.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a5/platform/shared/aicpu/platform_regs.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/a5/platform/sim/aicpu/inner_platform_regs.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu/device_time.cpp
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu/cache_ops.cpp)
target_include_directories(test_a5_kernel_gm_ack PRIVATE
    ${GTEST_INCLUDE_DIRS}
    ${A5_RUNTIME_DIR}
    ${CMAKE_SOURCE_DIR}/../../../src/a5/runtime/tensormap_and_ringbuffer/common
    ${CMAKE_SOURCE_DIR}/../../../src/a5/runtime/tensormap_and_ringbuffer/orchestration
    ${CMAKE_SOURCE_DIR}/../../../src/a5/platform/sim/aicore
    ${CMAKE_SOURCE_DIR}/../../../src/a5/platform/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/sim/aicpu
    ${CMAKE_SOURCE_DIR}/../../../src/common/platform/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/task_interface
    ${CMAKE_SOURCE_DIR}/../../../src/common/log/include
    ${CMAKE_SOURCE_DIR}/../../../src/common/host_build_graph
    ${CMAKE_SOURCE_DIR}/../../../src/common)
target_link_libraries(test_a5_kernel_gm_ack PRIVATE ${GTEST_MAIN_LIB} ${GTEST_LIB} pthread)
add_test(NAME test_a5_kernel_gm_ack COMMAND test_a5_kernel_gm_ack)

set_tests_properties(test_a5_kernel_gm_ack test_a5_kernel_scheduler_retirement PROPERTIES TIMEOUT 45)
