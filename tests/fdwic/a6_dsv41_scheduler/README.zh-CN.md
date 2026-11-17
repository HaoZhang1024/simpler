# A6：DSV4.1 SWA 用例迁移分析

基线：`origin/main@26b0511f3`，分支 `a6-migrate-case`。本阶段只分析迁移路径，未复制算子、修改构建或执行 A6 测试。

**建议先迁移 `pypto_lib_latest/swa` 的单卡回放。现有流程已经不调用 PyPTO 或 PTOAS；但重新编译仍需要 PTO-ISA 和 CANN，并且必须先具备适配 A6 的运行时。当前主线没有 `a6` 平台入口，不能直接宣称现有脚本已能在 A6 跑通。**

## 1. 当前已经有什么，哪些可以直接复用

这里的 SWA 是注意力子层，包括 mHC、量化、Q/KV 投影、缓存更新、Attention 和输出投影，不是单个 Attention kernel。[任务清单](../dsv41_scheduler/workloads/pypto_lib_latest/swa/tasks.tsv)包含 **16 个计算任务、578 个执行实例**；准备好边界输入快照后只需单卡，本切片没有跨卡通信及 deferred 等待。适合先验证计算、MIX 协同和调度，不能用它证明双卡 MoE／defer_wait 已适配。

| 已有材料 | 所在位置 | 可以省掉什么 |
| -------- | -------- | ------------ |
| 已生成／保留的计算核 C++ | `dsv41_scheduler/kernels/pypto_lib_latest/vendor/` | 不必从模型 Python 重新生成核源码 |
| 原始 Host 编排 C++ | `dsv41_scheduler/workloads/pypto_lib_latest/vendor/orchestration.cpp.gz` | 不必重新运行 PyPTO 生成编排源码 |
| runner、捕获／重放适配器源码 | `dsv41_scheduler/production/` | 不必重新实现执行器；仍需构建匹配的 Host 工具 |
| 已准备的 SWA 包 | 本地 `outputs/aicore-cost/inputs/swa/`，不随该分支提交 | 在兼容的 A5 环境下，直接跳过 `build.sh` 和 `prepare.py` |

表内前 3 项相对 `tests/fdwic/`，本地包路径相对仓库根目录。SWA 包含 `callable.bin`（编好的核与编排）、`plan-rank0.bin`、`slice.txt`、`rank0.txt`、输入快照和参考输出。**仓内 C++ 是源码，本地 `callable.bin` 才包含已编译机器码；两者不能混为“都已经编译好了”。**

已有包的直接执行流程：

```text
已有 SWA 包 + 匹配的 native-runner 与运行时库
  → run.sh → production/run.sh
  → 根据包的 device_count 启动 native-runner：独立 SWA 为 1 个 rank
  → C++ ChipWorker 加载运行时与 callable.bin
  → replay.cpp 按 plan 恢复 Tensor 视图、任务、依赖和 launch 参数
  → 生产 HBG Host 建图 → AICore 调度／计算 → 输出检查与计时
```

这里省掉的是上游生成和首次切包，**仍然走生产 HBG 建图与调度**。只有 MoE、跨层通信切片等双卡包才启动两个 rank。入口代码见 [run.sh](../dsv41_scheduler/production/run.sh)、[runner.cpp](../dsv41_scheduler/production/runner.cpp) 和 [replay.cpp](../dsv41_scheduler/production/replay.cpp)。

下面是现有接口，**不是已经可执行的 A6 命令**：

```bash
bash tests/fdwic/dsv41_scheduler/run.sh \
  "$SWA_BUNDLE" "$RUNTIME_LIB" "$RESULT_DIR" 0 1 10 \
  --runtime=host_build_graph
```

`0 1 10` 表示 L0、预热 1 次、测量 10 次；现有脚本自动通过 `task-submit` 分配设备，并进行 A5 架构检查。

## 2. 没有运行包，或者是全新 PyPTO 算子时，要补哪些步骤

**现有 DSV4.1 用例已经保存了 C++，所以可以从 B 开始；有兼容运行包时直接从 D 开始。全新算子通常先完成 A，再接入后续流程。**

```text
A. 仅全新／修改过的 PyPTO 算子需要：上游代码生成
   算子 Python → PyPTO 编译
     ├─ Host 编排 C++
     └─ 核的 PTO IR → PTOAS → 核 C++（常规 PTO 后端）
   保存源码、kernel manifest、参数／输入与正确性参考
   将这些材料接入用例构建和准备入口
                  ↓
B. build.sh：把已有 C++ 编译成可执行产物
   ├─ 编译 native-runner、capture/replay 适配器
   ├─ 编译原始 Host 编排 .so
   └─ 核 C++ + PTO-ISA 头文件 → CANN ccec／链接器 → 核机器码
   组装原始 callable.bin；这里不再调用 PyPTO／PTOAS
                  ↓
C. production/prepare.py：当前 DSV4.1 整网切片的首次准备
   ├─ 双卡跑原始完整 forward，捕获实际任务提交
   ├─ export_cases.py 按切分位置生成各用例运行包
   └─ 对 SWA 等独立切片，materialize.py 做前缀与参考运行
      保存切片输入快照与参考输出，解除后续测试对前缀的依赖
                  ↓
D. run.sh：反复运行已准备好的独立用例
   SWA 只跑单卡切片；不再生成代码，也不再运行完整 forward
```

[build_sources.py](../dsv41_scheduler/production/build_sources.py) 负责 B 的核编译与组包；[prepare.py](../dsv41_scheduler/production/prepare.py)、[export_cases.py](../dsv41_scheduler/production/export_cases.py)、[materialize.py](../dsv41_scheduler/production/materialize.py) 负责 C。**这些脚本目前面向已有 DSV4.1 清单，不会自动接收任意新 PyPTO 算子。** 新算子需补齐入口、manifest、输入、参考与选择范围；如果本来就是独立算子，直接准备它自己的任务图和输入即可，不必为了测试它再跑 40 层双卡 forward。外部 DSL 核使用自身的上游生成链，也不应统一算作 PTOAS 路径。

## 3. 后续调优时，哪些要重做

```text
没有兼容包：首次完成 B、C；有包则直接复用
    ↓
选定同一个用例包，测 L0 基线，另采详细泳道
    ↓
只修改调度器实现 → 重编匹配的 runtime
    ↓
同一个运行包、相同输入／核／任务图再次测试
    ↓
比较耗时并执行该用例实际支持的正确性检查 → 继续修改和复测
```

**仅改调度算法且 ABI、算子和输入契约不变时，不需要反复执行 A、B、C。** 若改了 Tensor／调用 ABI，需要重编相应 runner、适配器或核，并重建不兼容的 plan／包；改了模型逻辑、shape 或任务图，则回到相应生成与准备步骤。切换 Git 分支不会自动更新磁盘上已编译的运行时库。

MoE 要区分版本：DSL 固定回放 MoE 可以按上图复测，并保留其参考检查；**最新 `pypto_lib_latest/moe` 执行原始 native Host 编排，保留动态 `get_tensor_data`，不是冻结任务回放。** 它复用已准备的输入和核，但每轮仍执行原始控制逻辑；当前该性能用例明确记录 `numerical_validation: false`，不能把运行成功称为数值校验通过。SWA 回放则保留逐轮输出检查，见 [用例说明](../dsv41_scheduler/README.md)。

| 组件 | 重新构建 SWA 包 | 执行已构建的 SWA 包 |
| ---- | --------------- | ------------------- |
| PyPTO／PyPTO-lib | 不需要；已保留生成后的 C++ | 不需要 |
| PTOAS | 不需要；走 C++ → ccec，不走 PTO IR → PTOAS | 不需要 |
| PTO-ISA | 需要目标平台支持的头文件与指令实现 | 不需现场编译，但相应实现已进入核二进制 |
| CANN | 需要目标平台的 ccec、链接器及头文件 | 需要匹配的驱动／运行库 |
| Simpler | 需要编译工具、Host runner、匹配的 HBG 头文件与运行时 | 需要 Host／AICPU／AICore 运行时和 dispatcher |
| Python／Torch | 构建脚本使用 Python；本 SWA 路线不需要 Torch | 启动与统计脚本使用 Python；不需要 Torch 或 Simpler Python bindings |

因此，**不装 PTOAS 验证 SWA 是可行的迁移路线；不等于 A5 的旧二进制可以直接放到 A6 上执行。** 若最终必须从模型重新生成 A6 C++，才需要重新评估 PyPTO／PTOAS 生成链，这不是当前第一步。

## 4. A6 迁移的关键点

1. **先明确 A6 平台能力。** [platform_info.py](../../../simpler_setup/platform_info.py) 目前没有 `a6`；[toolchain.py](../../../simpler_setup/toolchain.py) 的 A5 目标写的是 `dav-c310-cube/vec`。必须确认 A6 SDK、目标架构名、PTO-ISA 支持分支及 HBG 运行时来源，核对启动、核拓扑、同步与计时接口；不能只把目录名或字符串换成 A6。
2. **只构建 SWA 所需内容。** 当前 `build_sources.py --flavor pypto_lib_latest` 会编全部核并追加 native MoE；`prepare.py` 会跑整网。迁移入口应从 SWA 的实际 plan 收集使用的 kernel ID，只重编这些核和回放入口，避免把“先跑通整网”变成前置条件。[tmr_prepare.py](../dsv41_scheduler/production/tmr_prepare.py) 已有“选取使用的核、重编、重新组包”的参考实现；借鉴流程，不引入 TMR 调度来替代 HBG。
3. **检查业务核的可移植性。** SWA 包含 MXFP8 投影、量化和混合核，例如 [mxfp8_projection.hpp](../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/mxfp8_projection.hpp) 使用 `TMATMUL_MX`。需确认 A6 对数据格式、Tile 布局、核内存容量及 Cube／Vector 协同的支持。先保持逻辑任务、计算量与依赖；若必须调整分块或同步，单独记录，不能把变化全部当成调度收益。
4. **输入与 ABI 要一起核对。** 可利用已有 SWA 输入快照和参考输出，但不能复用 A5 `callable.bin` 中的机器码。`plan-rank0.bin` 也不是通用图格式：[record.h](../dsv41_scheduler/production/record.h) 直接保存 `TensorData`，限定同构建布局；尺寸一致也不等于语义一致。需核对字段、shape／stride／offset、别名、数据布局和 kernel 签名，必要时由原构建解码，再按目标 ABI 重新生成。只有 `tasks.tsv`／`deps.json` 不足以执行。
5. **隔离构建与硬件检查。** 参数化当前写死的 `KernelCompiler("a5")`、A5 include 路径、设备预检查及缓存身份。A6 的核、运行时、dispatcher 和 replay 库必须成套，使用独立输出目录；确认平台支持后再给出实际 A6 命令，不借用 A5 检查结果。

## 5. 计划与验收

1. 确认 A6 的 SDK／PTO-ISA／运行时组合，先验证简单核和 HBG 启动路径；没有这些条件时停在平台适配，不启动整网编译。
2. 准备匹配来源的 SWA plan、输入快照和参考输出，建立只重编所需 C++ 核的路径，重新组装目标包。已保存的快照用于跳过原完整 forward 准备。
3. 在未配置 PyPTO／PTOAS 的干净环境完成构建和单卡执行，保存实际编译命令及依赖版本，证明不是命中了旧 A5 编译缓存。
4. 先验功能，再测 L0：保留输出检查，核对 16 个计算任务、578 个执行实例及依赖／MIX 语义；性能记录 AICore 窗口、Device wall 和 Host 准备时间，详细泳道另采。现有零权重夹具按字节比较，只能证明这份固定用例；若跨代出现数值差异，先定位并明确比较标准，再增加非零输入验证，不能直接跳过检查。

当前结论：**可以把“无 PTOAS 的 SWA 单卡回放”作为首个迁移目标；未确认的关键条件是 A6 平台／HBG 运行时及现有 C++ 核的支持情况，而不是缺少模型 Python。** 后续再扩展其他算子、双卡通信与完整 forward。
