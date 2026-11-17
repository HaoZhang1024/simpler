# A6 percounter SWA 分步实施任务

[返回索引](../README.zh-CN.md) · [迁移分析](a6-migration.zh-CN.md) · [黄区接口查证](a6-environment.zh-CN.md)

目标是让现有 SWA 在 A6 单卡生产 percounter 上构建、执行、校验并正常退出。同事负责 A6 公共平台和 HBG，我们负责 percounter 适配及其 SWA 集成。双方共用平台、计算核和 fixture，分别验收运行时。性能优化在功能验收后开展。

## 1. 已有基础与分工

当前已包含 SWA 的 19 个 kernel 注册、设备 C++、固定输入和参考 fixture、A5 验证记录、两组 MIX 核的 A6 1C1V 改写，以及 plan 转换工具。A6 转换后为 16 个任务、570 个执行实例，A5 为 578 个。输入恢复、30 个可写 Device buffer 的参考比较和统计逻辑已有实现。

编译记录分为两个阶段：现场早期原始核为 17／19 编译通过，后续改写后蓝区为 19／19 编译、链接和机器码提取通过；A6 设备功能验证待完成。上述工具与数据直接复用。

| 工作范围 | 负责人 | 交付边界 |
| -------- | ------ | -------- |
| A6 平台发现、工具链、平台库、dispatcher、核与寄存器映射、设备启停 | 同事 | 公共平台代码、接口说明及对应验证结果 |
| Host orchestration、AICPU 生命周期的公共适配 | 同事 | 双方共用的接口与实现；percounter 自有 hook 由我们接入 |
| HBG resident image 与调度器 | 同事 | HBG 自有实现与验收结果 |
| SWA kernel、fixture、plan 转换工具 | 同事维护，我们复用 | 同一版本的源码、任务描述、数据与检查结果 |
| percounter 资源排列、任务映像、AICPU 图物化、AICore 调度协议 | 我们 | percounter 实现、基础测试及 A5 受影响路径回归 |
| percounter SWA 构建、组包、运行与验收说明 | 我们 | 复用现有工具的集成入口、构建清单与运行结果 |
| 环境和 Q1–Q5 查证、设备执行 | 同事协调黄区 agent；我们提供 percounter 检查项 | 公共资料双方复用，HBG 与 percounter 运行结果分别记录 |

公共平台修改与 HBG 专有修改分别交付。共享脚本由同事维护已有编译、转换工具，我们负责组包与 percounter 运行选择；涉及同一文件时先对齐接口和修改范围，再由对应负责人落地。

## 2. 实施步骤总表

| 步骤 | 我们要做的内容 | 现在可推进 | 等待的交付 | 完成条件 |
| ---- | -------------- | ---------- | ---------- | -------- |
| 1. 梳理并适配 percounter 逻辑 | 清点 A5 假设，修改逻辑 1C1V 资源模型，准备协议与基础测试 | 源码分析、Host 资源排列及 CPU 可验证部分、测试样本 | 物理编号与 SSBUF 等接口确定后接入设备路径 | 逻辑资源分配与执行集合检查通过，平台接口需求明确 |
| 2. 准备 SWA 集成 | 串联现有 fixture 检查、plan 转换和编译产物，准备 percounter 组包与运行参数 | 数据与转换结果检查、构建清单、脚本流程及结果采集 | 目标平台构建入口、参数 ABI 和运行时产物 | 完整运行包使用正确 plan、kernel 与 runtime |
| 3. 接入公共平台 | 集成同事交付，完成 percounter 自有映像、图物化、lane loop 与生命周期 hook | 先梳理共享源文件和 hook 的调用关系 | 公共平台代码、Q1–Q4 依据与基础启停结果；Q5 超时依据 | percounter 成套构建，基础调度和启退验证通过 |
| 4. 黄区功能验收 | 组织 percounter 基础用例、MIX 和完整 SWA 校验，定位问题 | 提前准备命令、通过条件及日志清单 | 步骤 3 可执行，黄区工具链与设备占用方式就绪 | 16 任务、570 实例、30 个可写 buffer 校验及重复运行通过 |
| 5. 固定交付与回归 | 更新操作说明，完善增量构建，验证受影响的 A5 路径 | 随实现补充文档和回归范围 | 黄区功能结果及固定集成版本 | 新目录复现，源码、数据、产物与结果对应 |

步骤 1、2 可同时推进。步骤 3 按公共平台接口和代码分批接入；集成时间由公共部分的交付情况决定，HBG 完整 SWA 验收单独推进。

```text
同事：黄区接口查证 → 公共平台、共享生命周期 → 分批交付
                          │                    │
                          │                    ├→ 同事：HBG 适配与验收
                          │                    │
我们：percounter 逻辑与测试 ─────────────────────┤
我们：SWA 组包与运行集成准备 ────────────────────┤
                                               ↓
                                  接入公共平台与硬件接口
                                               ↓
                                  percounter 基础用例验证
                                               ↓
                                  A6 percounter 完整 SWA
                                               ↓
                                      固定交付与回归
```

## 3. 我们现在可以先做

### 步骤 1：percounter 逻辑与测试

以下路径相对于 `src/a5/runtime/percounter/`，作为目标适配的现有代码入口。

| 文件 | 现在推进的内容 | 接口交付后完成的内容 |
| ---- | -------------- | -------------------- |
| `host/resource_order.h` | 梳理 `cluster * 3`、双 V 容量、参与 mask；适配逻辑 1C1V 资源分配、回收、排序及 sync_start 容量检查 | 将逻辑资源接到公共平台提供的物理映射 |
| `host/image/image_pack.h`、`runtime/task_image_layout.h`、`aicpu/graph_prepare.h` | 梳理 Host 打包、AICPU 图物化、AICore 读取的数据契约，核对 block、mask、Tensor 别名及依赖 | 使用目标 ABI 构建并验证三端数据一致性 |
| `aicore/lane_loop.h`、`runtime/scheduler/wire_types.h` | 分析协调者、参与者、任务领取、会合、完成与代际复用，准备 1C1V 协议测试 | 接入真实 C/V 编号、共享资源和可见性规则 |
| `runtime/scheduler/ssbuf.h` | 列出 percounter 区域容量、字段和访问顺序需求 | 根据同事交付的可用区域、共享范围与屏障规则适配 |
| `runtime/scheduler/gm.h`、`async_completion.h` | 梳理完成计数、依赖发布及退出条件，准备重复运行测试 | 在 A6 验证原子访问、可见性与完成观察 |
| `build_config.py` | 梳理共享源码、include 顺序、自有入口与 hook | 接入同事交付的 A6 平台和构建发现机制 |

- [ ] 整理 percounter 对公共平台的接口需求，交给同事并入 Q1–Q5 查证。
- [x] 完成 Host 资源排序的逻辑 1C1V 模型及 CPU 测试，保留 A5 当前有效的 1C2V 行为。两个生产调用方显式传入平台 AIV 数；设备协议适配继续按下列待办推进。
- [ ] 准备普通 AIC/AIV 依赖、1C1V MIX、sync_start、多波次、连续调用和 Worker 重建的验收用例。
- [ ] 核对任务映像及图物化中的 A5 假设，明确需要目标 ABI 验证的字段。

**阶段产物：** percounter 逻辑修改、可执行的离线检查、基础用例，以及逐项对应代码的接口需求。物理地址、寄存器值和 SSBUF 布局采用公共平台交付的定义。

2026-11-17 资源模型验证：`make_resource_order` 显式接收每组 Vector 数，统一用于参与 mask 校验、容量、分配、释放和整类资源预留。测试独立为 `tests/ut/cpp/a5/runtime/percounter/test_resource_order.cpp`，注册目标 `test_percounter_resource_order`，保留原有 6 项 A5 测试并新增 8 项。Windows LLVM-MinGW 下直接编译该测试和仓库指定的 GoogleTest 1.14.0，14／14 通过；新增小图遍历覆盖 10,368 组 1C1V 图，原有 A5 遍历覆盖 768 组。编译启用 `-Wall -Wextra -Werror`。

本轮覆盖 Host 逻辑模型，完整 CMake 测试目标、生产运行时构建及设备执行留待后续环境验证。Linux 标准入口为构建 `test_percounter_resource_order` 后执行 `ctest --test-dir tests/ut/cpp/build -R '^test_percounter_resource_order$' --output-on-failure`。本地测试结果保存在 `build/a6-resource-model/results.xml`。

### 参与者、任务映像与完成协议核对结果

| 代码位置 | 当前处理逻辑 | 后续动作与归属 |
| -------- | ------------ | -------------- |
| HBG 共享 `runtime/scheduler/scheduler_topology.h` | 已接收 aiv_per_cluster，但按启动 worker 连续排列推导同组 C/V | 同事确认 A6 启动编号和实际配对关系；我们复用该映射接口 |
| percounter `aicpu/supervisor.h` | 握手后统计实际 C/V，按平台 AIV 数检查配比并发布拓扑 | 我们接入平台常量；黄区确认实际可用完整配对数 |
| `host/region_plan.h`、`runtime/scheduler/argument_metadata.h` | mask 校验仍按最多三个槽位；参数函数数组按平台 lane 数遍历 | 我们补齐目标拓扑的 mask 校验；三端槽位 ABI 按 Q6 明确后统一修改 |
| `runtime/scheduler/wire_types.h`、`aicore/lane_loop.h` | claim shape 使用三位 mask；会合按实际 mask 遍历参与者，MIX 协调者为逻辑 lane 1；入口仍实例化 lane 2 | 保留有效的参与者逻辑，适配目标 lane 实例和边界检查；编号依据来自 Q1/Q4 |
| `host/region_plan.h`、`host/graph_template.h` | 完成总量来自 block_num × 实际 subtask 数；counter preset 为 1 − 总量 | 使用转换后 mask 和 block 数，分别验证普通任务、图体和 shell sink 计数；当前计数语义可复用 |
| `host/image/image_pack.h`、`runtime/task_image_layout.h` | 静态断言核对固定任务 stride 和偏移，percounter 保留 AICPU 图物化 | 按 Q6 核对三端 sizeof/alignof/offsetof 与 kernel_id 槽位；逻辑 lane 数与序列化格式分别处理 |
| `runtime/scheduler/gm.h`、`ssbuf.h` | GM 观察使用 DCCI/DSB，SSBUF 发布和读取带屏障；SSBUF 使用 A5 固定区域 | 我们按 Q3/Q7 确认的规则接入，设备端验证可见性与代际复用 |

SWA 资源边界已补入 CPU 测试：转换后 t22 为 48 个同步 MIX block，47 组 1C1V 资源时拒绝，48／54 组时通过；普通 Vector 的 64／80 block 在 54 组下分两波。该结果表示逻辑资源可容纳性，实际可分配 C/V 数和配对关系由黄区确认。查证顺序、问题及返回模板统一维护于 [黄区接口查证](a6-environment.zh-CN.md#黄区查证顺序与交接)。

### 步骤 2：SWA 集成准备

当前 `compile_kernels.py` 已支持 A6，`prepare_plan.py` 已输出 A6 plan；`prepare.py build` 和 `run.py` 仍使用 A5 平台约束。

- [ ] 复用现有 fixture 校验和 `prepare_plan.py`，在组包流程中接入转换后的 16 任务、570 实例 plan。
- [ ] 梳理 `prepare.py`、`production/CMakeLists.txt` 的工具及参数头文件来源，准备 percounter 构建和 callable 组装流程。
- [ ] 准备 `run.py`、`production/run.sh` 的平台、runtime 和设备选择参数，复用输入恢复、参考比较及结果统计。
- [ ] 生成构建清单，关联平台、kernel 注册、plan、任务数、实例数与运行包内容。
- [ ] 为黄区准备已有 plan 解码、转换和 kernel 编译检查命令，明确输入、输出及通过条件。

**阶段产物：** 集成脚本与离线检查。完整目标运行包在平台、ABI 和 percounter 产物就绪后组装验证。kernel 与 plan 工具内部的问题交由同事维护，双方共用修复结果。

## 4. 等待同事交付及接入工作

### 公共部分交付清单

| 交付项 | 具体内容 | 我们用于 |
| ------ | -------- | -------- |
| 平台与构建代码 | A6 平台发现、Host/AICPU/AICore 工具链、平台库、dispatcher、构建命令与共享源文件位置 | 注册并构建 percounter，接通运行包 |
| 核与寄存器接口（Q1/Q2） | C/V core ID、逻辑配对、有效资源、驱动 res_id、寄存器窗口与读写规则，附依据 | 逻辑 worker 映射、参数发布及启动退出 |
| SSBUF 规则（Q3） | 容量、同组共享范围、可用偏移、kernel 预留区域、访问屏障 | percounter 自有 SSBUF 布局和会合协议 |
| 启动与共享生命周期（Q4） | 联合启动、blockDim、sub-block、READY/完成/EXIT、公共接口和已有样例 | 接入 percounter 自有 hook 与 lane loop |
| 计时依据（Q5） | 计数器单位、频率及获取方法 | 超时核验和结果统计 |
| 验证与版本 | 对应代码版本、工具链、基础加载及启退日志、已确认范围与待查项 | 冻结集成版本，复用平台证据并组织 percounter 验收 |

同事按已确认的接口和可用代码分批交付，我们逐项接入。共享生命周期修改需覆盖 percounter 的调用契约：当前 percounter 复用 Host orchestration 和 AICPU 生命周期，同时保留自有 image packer、AICPU 图物化及 AICore 入口。

### 步骤 3：接入并验证 percounter

- [ ] 集成公共平台代码，接通 percounter 构建配置与共享源码引用。
- [ ] 将逻辑 1C1V 模型接到实际核映射，落实 SSBUF、屏障和参与者编号。
- [ ] 完成 Host 打包、AICPU 图物化与 AICore lane loop 的目标 ABI 验证。
- [ ] 验证 percounter 的初始化、参数传递、任务领取、完成观察和退出。
- [ ] 在黄区执行基础用例，检查每个有效 block 正好执行一次、依赖顺序正确及重复运行状态正确。

**验收：** percounter 成套构建，基础用例和生命周期验证通过。公共平台问题由同事修复，percounter 协议问题由我们修复，共享接口变更由双方同步接入。

## 5. 黄区验收与交付

### 环境准备

| 已有信息 | 执行安排 |
| -------- | -------- |
| Host 为 x86_64、Ubuntu 20.04.6，AICPU 目标为 aarch64 | 黄区本地构建 Host 工具，先验证原 plan 的 2735 条记录与转换结果；工具链按目标分别配置 |
| CANN 9.3.0，目标为 `dav-920r1-cube/vec`，PTO-ISA 与当前 pin 一致 | 使用交付版本复核 19 个 kernel 的编译、链接和机器码提取 |
| 54 AIC、54 AIV、8 AICPU，PTO-ISA 有 1C1V 同步实现 | 平台映射采用同事确认的接口，percounter 验证逻辑资源与真实执行集合 |
| 记录 CMake 3.16.3，缺 Ninja、项目 venv | 黄区离线检查前准备项目 venv、满足构建要求的 CMake 和 Ninja |
| 可从 GitHub 下载；旧记录缺 task-submit、npu-smi | 黄区确认下载及单卡占用方式，使用同事适配的设备预检入口 |

### 步骤 4：完整 SWA 功能验收

- [ ] 同事提供两组 MIX 核的针对性非零样本与检查结果，我们复用到 percounter 执行验证，覆盖前后半 head、列和写回范围。
- [ ] 黄区运行完整 SWA，检查 16 个任务、570 个实例及 30 个可写 Device buffer 的参考输出。
- [ ] 执行连续调用与 Worker 重建，检查每轮输入恢复、完成计数和正常退出。
- [ ] 汇总功能结果、运行版本及日志；kernel／plan 问题交由同事，percounter 问题由我们处理。

### 步骤 5：固定交付与回归

- [ ] 在新构建目录复现，只构建 SWA、percounter 及必要公共依赖；源码仓为 Simpler 与配套 PTO-ISA，使用已有设备 C++。
- [ ] 按实际重编范围复用缓存，区分平台、编译器、PTO-ISA、源码与头文件依赖。
- [ ] 我们验证 percounter 修改影响的 A5 路径；同事提供公共平台、共享生命周期和 kernel 修改的对应回归结果。
- [ ] 更新黄区构建、运行及失败定位说明，固定集成版本和结果清单。

功能交付通过后，另行安排 A5/A6 percounter 性能比较及硬件优化。
