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
#include "measurement.h"

#include <acl/acl.h>
#include <rt_external_device.h>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void check(int rc, const char *operation) {
    if (rc) throw std::runtime_error(std::string(operation) + " rc=" + std::to_string(rc));
}

void write_rounds(const std::vector<Observation> &data, Operation op, const char *label, std::ostream &csv) {
    for (uint32_t round = 0; round < kRounds; ++round) {
        uint32_t returned_zero = 0;
        for (uint32_t slot = 0; slot < kLanes; ++slot) {
            const auto &s = data[round * kLanes + slot];
            const bool valid_value = op == Operation::Exchange ? s.value <= 1 : s.value == 1;
            if (s.round != round || s.slot != slot || s.vector_lane != unsigned(slot >= kPairs) ||
                s.begin == 0 || s.end <= s.begin || !valid_value || (slot == 0 && s.target_after_barrier != 1)) {
                throw std::runtime_error(std::string(label) + " invalid sample round=" + std::to_string(round) +
                                         " slot=" + std::to_string(slot));
            }
            returned_zero += s.value == 0;
            csv << label << ',' << round << ',' << slot << ',' << s.core << ',' << s.vector_lane << ',' << s.begin
                << ',' << s.end << ',' << s.value << ',' << s.target_after_barrier << '\n';
        }
        if (op == Operation::Exchange && returned_zero != 1) throw std::runtime_error("invalid exchange history");
    }
    csv.flush();
    std::cout << label << " validated " << kRounds << " rounds x " << kLanes << " lanes\n";
}

void measure(int device, bool notify, const char *file) {
    const char *soc = aclrtGetSocName();
    int64_t cubes = 0, vectors = 0;
    check(aclrtGetDeviceInfo(device, ACL_DEV_ATTR_CUBE_CORE_NUM, &cubes), "query AIC");
    check(aclrtGetDeviceInfo(device, ACL_DEV_ATTR_VECTOR_CORE_NUM, &vectors), "query AIV");
    std::cout << "device=" << device << " soc=" << (soc ? soc : "?") << " available=" << cubes << "C+" << vectors
              << "V launched=48C+48V clock_hz=1000000000\n";
    if (!soc || std::string(soc) != "Ascend960DT_966B7" || cubes < kPairs || vectors < kPairs)
        throw std::runtime_error("expected an allocated Ascend960DT_966B7 with 48 resident pairs");

    aclrtStream stream{};
    check(aclrtCreateStream(&stream), "create stream");
    void *word = nullptr;
    aclrtCntNotify counter{};
    rtDevResInfo resource{0, RT_PROCESS_CP1, RT_RES_TYPE_STARS_CNT_NOTIFY_RECORD, 0, 0};
    if (notify) {
        check(aclrtCntNotifyCreate(&counter, 0), "create CntNotify");
        check(aclrtCntNotifyGetId(counter, &resource.resId), "get CntNotify id");
        uint64_t address = 0;
        uint32_t length = 0;
        rtDevResAddrInfo mapping{&address, &length};
        check(rtGetDevResAddress(&resource, &mapping), "map CntNotify SET/read");
        if (address == 0 || address % alignof(uint32_t) || length < sizeof(uint32_t))
            throw std::runtime_error("invalid SET/read mapping");
        word = reinterpret_cast<void *>(address);
        std::cout << "mapped SET/read id=" << resource.resId << " bytes=" << length << '\n';
    } else {
        check(aclrtMalloc(&word, 64, ACL_MEM_MALLOC_HUGE_FIRST), "allocate shared GM word");
    }

    std::vector<Observation> samples(kLanes * kRounds);
    const size_t bytes = samples.size() * sizeof(Observation);
    void *buffer = nullptr;
    check(aclrtMalloc(&buffer, bytes, ACL_MEM_MALLOC_HUGE_FIRST), "allocate record buffer");
    std::ofstream csv;
    csv.exceptions(std::ios::failbit | std::ios::badbit);
    csv.open(file);
    csv << "scenario,round,slot,core_id,is_vector,begin_tick,end_tick,observed,final_at_slot0\n";
    auto run = [&](Operation op, const char *label) {
        check(aclrtMemset(buffer, bytes, 0xff, bytes), "mark empty records");
        launch_measurement(op, static_cast<uint32_t *>(word), static_cast<Observation *>(buffer), stream);
        check(aclrtSynchronizeStreamWithTimeout(stream, 10000), label);
        check(aclrtMemcpy(samples.data(), bytes, buffer, bytes, ACL_MEMCPY_DEVICE_TO_HOST), "copy samples");
        write_rounds(samples, op, label, csv);
    };
    if (notify) {
        run(Operation::Load, "cnt_notify_read");
        run(Operation::Store, "cnt_notify_write");
    } else {
        run(Operation::Load, "gm_ldst_read");
        run(Operation::AddZero, "gm_atomic_read");
        run(Operation::Store, "gm_ldst_write");
        run(Operation::Exchange, "gm_atomic_write");
    }
    csv.close();
    check(aclrtFree(buffer), "free record buffer");
    if (notify) {
        check(rtReleaseDevResAddress(&resource), "release SET/read mapping");
        check(aclrtCntNotifyDestroy(counter), "destroy CntNotify");
    } else {
        check(aclrtFree(word), "free GM word");
    }
    check(aclrtDestroyStream(stream), "destroy stream");
}
}  // namespace

int main(int argc, char **argv) {
    if (argc != 4 || (std::string(argv[2]) != "gm" && std::string(argv[2]) != "cnt_notify")) return 2;
    bool initialized = false, selected = false;
    int device = 0;
    try {
        device = std::stoi(argv[1]);
        check(aclInit(nullptr), "aclInit");
        initialized = true;
        check(aclrtSetDevice(device), "select device");
        selected = true;
        measure(device, std::string(argv[2]) == "cnt_notify", argv[3]);
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        if (selected) aclrtResetDevice(device);
        if (initialized) aclFinalize();
        return 1;
    }
    const int reset_rc = aclrtResetDevice(device);
    const int finalize_rc = aclFinalize();
    if (reset_rc || finalize_rc) std::cerr << "cleanup rc=" << reset_rc << ',' << finalize_rc << '\n';
    return (reset_rc || finalize_rc) ? 1 : 0;
}
