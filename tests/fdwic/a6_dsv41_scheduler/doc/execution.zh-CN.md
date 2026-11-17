# SWA 执行原理与依赖

[返回索引](../README.zh-CN.md)

## 已有什么，实际执行了什么

**仓内保留的是 C++ 源码；`callable.bin` 才包含编译后的核机器码和编排。** 已有源码省掉上游代码生成，仍需用目标平台的 CANN 编译器生成机器码。

| 材料 | 位置与用途 |
| ---- | ---------- |
| 计算核 C++ | [vendor/](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/)，复用已生成的核实现 |
| 原始 Host 编排 C++ | [orchestration.cpp.gz](../../dsv41_scheduler/workloads/pypto_lib_latest/vendor/orchestration.cpp.gz)，供原整网构建／捕获使用 |
| 原生执行与回放工具 | [production/](../../dsv41_scheduler/production/)，提供 native-runner、capture/replay、组包及统计逻辑 |
| 用例目录输入夹具 | [swa.tar.gz](../fixtures/swa.tar.gz)，约 104 KB，保存 rank0 输入、plan、参考；不含核机器码 |
| 夹具来源与校验和 | [fixture.json](../fixtures/fixture.json)，正常使用无需访问旧机器的输出目录 |
| 本机旧 A5 包 | 仓库根目录下 `outputs/aicore-cost/inputs/swa/`，用于此次提取，不随分支提交 |
| 新构建包 | 用例目录 `build/a5/bundle/`，含 `callable.bin`、`plan-rank0.bin`、`slice.txt`、`rank0.txt`、输入及参考 |

现在的执行路径：

```text
prepare.py build
  ├─ 解开固定输入、原始 plan 和参考输出
  ├─ 编译 native-runner、replay、record-tool
  └─ 只编 SWA 的 19 个 C++ 核 → 组装 callable.bin
                    ↓
run.py → 原 production/run.sh → 启动 1 个 rank
  → C++ ChipWorker 加载运行时与 callable.bin
  → replay.cpp 恢复 Tensor 视图、任务、依赖和 launch 参数
  → 生产 HBG 建图／所选 AICore 调度器执行
  → 原有输出检查与端点计时
```

**省掉的是上游生成和整网切包，生产建图与调度仍然执行。** 具体入口见 [prepare.py](../prepare.py)、[run.py](../run.py)、[runner.cpp](../../dsv41_scheduler/production/runner.cpp) 和 [replay.cpp](../../dsv41_scheduler/production/replay.cpp)。plan 保留原捕获中的视图、别名及边界元数据，实际只提交 SWA task 8～35；读取其余元数据不会执行整网。

原通用用例接口仍可用于已有兼容包：

```bash
bash tests/fdwic/dsv41_scheduler/run.sh \
  "$SWA_BUNDLE" "$RUNTIME_LIB" "$RESULT_DIR" 0 1 10 \
  --runtime=host_build_graph
```

`0 1 10` 为 L0、预热次数、测量次数。独立 SWA 只启动一个 rank；MoE、跨层通信等双卡包才启动两个 rank。此接口目前也有 A5 架构检查，不能直接当作 A6 命令。

## 编译、准备与运行分别需要几张卡

**编译不需要 NPU；已有快照的独立 SWA 运行只需要一张卡。** 以前的双卡要求来自 EP2 完整模型的首次数据准备，不是编译要求。

| 操作 | 需要的设备 | 当前是否还要做 |
| ---- | ---------- | -------------- |
| C++ 核、runner 和运行时编译 | 不需要 NPU，使用 Host 工具链 | 换到 A6 时需要重编 |
| 从原 EP2 完整模型捕获任务、保存 SWA 边界输入与参考 | 原流程需要两张卡运行 | 已完成，结果保存在 `fixtures/`，无需在 A6 重做 |
| 解包快照、检查 plan、组装目标运行包 | 不需要 NPU | 使用本目录 `prepare.py build` |
| 单独执行 SWA 并对照参考 | 一张卡 | A5 已通过；A6 待运行时与核适配后执行 |

SWA 截取后的数据已经包含它原先从前面网络接收的中间结果。每次测试直接加载这些数据，所以不必再运行前面的网络，也不必再准备第二张卡。

## 依赖分别在哪一阶段使用

| 组件 | 构建已有 C++ 用例 | 执行已构建包 |
| ---- | ----------------- | ------------ |
| PyPTO／PyPTO-lib | 不需要重新生成源码 | 不需要 |
| PTOAS | 不需要；走 C++ → ccec | 不需要 |
| PTO-ISA | 需要目标平台头文件与指令实现 | 相应实现已进入核二进制，不在现场编译 |
| CANN | ccec、链接器、头文件 | 匹配的驱动与运行库 |
| Simpler | 编译工具、Host runner、HBG 头文件和运行时 | Host／AICPU／AICore 库与 dispatcher |
| Python／Torch | 构建脚本需要 Python；本 SWA 不需要 Torch | 启动和统计使用 Python；原生 C++ 执行不需要 Torch 或 Simpler Python bindings |

## 全新算子需要补什么

**全新 PyPTO 算子从 A 开始；已有 C++ 从 B 开始；用例目录已有输入快照，构建时跳过 C；已有兼容运行包直接做 D。**

```text
A. 上游代码生成：仅全新／修改过的算子需要
   Python → PyPTO
     ├─ Host 编排 C++
     └─ PTO IR → PTOAS → 核 C++（常规 PTO 后端）
   保存源码、kernel manifest、参数、输入与正确性参考
                    ↓
B. C++ 编译：原通用 build.sh／build_sources.py
   ├─ 编译 runner、capture/replay 和原始 Host 编排 .so
   └─ 核 C++ + PTO-ISA → CANN ccec／链接器 → 核机器码与 callable.bin
                    ↓
C. 原 DSV4.1 套件的首次切包：production/prepare.py
   ├─ 双卡跑原始完整 forward，捕获实际任务提交
   ├─ export_cases.py 按切分位置生成各用例包
   └─ materialize.py 运行前缀与参考，保存边界输入和参考输出
                    ↓
D. 独立运行：run.sh／用例目录 run.py
   反复运行 SWA，复用准备好的输入与参考
```

B 的代码见 [build_sources.py](../../dsv41_scheduler/production/build_sources.py)；C 见 [production/prepare.py](../../dsv41_scheduler/production/prepare.py)、[export_cases.py](../../dsv41_scheduler/production/export_cases.py)、[materialize.py](../../dsv41_scheduler/production/materialize.py)。**用例目录的 `prepare.py build` 是 SWA 构建入口，与 C 的整网准备脚本不同。**

这些通用脚本仍按 DSV4.1 清单工作，接入全新算子需补入口、manifest、输入、参考和选择范围。如果算子本来独立，直接准备自身任务图和输入即可，不必为测试它跑 40 层 forward。外部 DSL 核走自身的代码生成链，不统一归为 PTOAS。
