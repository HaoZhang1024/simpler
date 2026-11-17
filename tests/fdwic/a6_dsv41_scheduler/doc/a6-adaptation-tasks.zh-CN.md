# A6 percounter SWA 分步实施任务

[返回索引](../README.zh-CN.md) · [迁移分析](a6-migration.zh-CN.md) · [黄区接口查证](a6-environment.zh-CN.md)

目标是让现有 SWA 在 A6 单卡生产 percounter 上构建、执行、校验并正常退出。适配范围包含 percounter 依赖的 Host orchestration、AICPU 生命周期与 HBG/common 共享源码；独立 `host_build_graph` resident 调度器不作为前置交付。性能优化在功能验收后开展。

## 当前基础与蓝区待修改总表

当前分支已包含：SWA 的 19 个 kernel 注册、固定输入和参考 fixture、A5 HBG/percounter 验证记录、两个 MIX 核的 A6 1C1V 改写，以及 plan 转换工具。归档的 A6 核编译、链接和机器码提取为 19／19 通过；设备执行待黄区验证。SWA 保持 16 个任务，A5 为 578 个执行实例，A6 转换后为 570 个。

下表各项为待完成工作；已有离线工具作为实现基础复用。

| 步骤 | 蓝区待修改内容 | 主要代码位置 | 黄区依赖 | 交付与验收 |
| --- | --- | --- | --- | --- |
| 1. 接通构建和组包 | 串联 fixture 校验、目标核编译、plan 转换和 callable 组装；接入定向构建与缓存 | `prepare.py`、`compile_kernels.py`、`prepare_plan.py`、`production/CMakeLists.txt` | 现场 Host ABI 与 SDK 复核；完整组包依赖目标运行时接口 | A6 运行包及构建清单一致；单项修改只重建相关产物 |
| 2. 接入公共平台 | 完成 A6 平台发现、三类工具链、平台库和 dispatcher；实现映射、启动、完成与退出 | `simpler_setup/`、平台实现及共享生命周期代码 | Q1–Q4：核编号、寄存器、SSBUF、启动依据；Q5：计时与超时单位 | percounter 所需组件成套构建，基础加载、参数传递与启停验证通过 |
| 3. 适配 percounter | 修改资源排列、1C1V 协同、SSBUF、领取与完成协议，核对任务映像 ABI | `src/a5/runtime/percounter/` 对应实现及其共享依赖 | 公共平台规则与黄区设备验证 | 普通依赖链、MIX、sync_start、多波次和重复运行通过 |
| 4. 跑通完整 SWA | 接通目标运行入口与结果采集；核对两组 MIX 核，执行固定输入与参考检查 | `run.py`、`production/run.sh`、两个 MIX 核 | 步骤 2、3 可执行；黄区单卡占用方式 | 16 个任务完整执行，30 个可写 Device buffer 校验通过，正常退场 |
| 5. 固定交付与回归 | 完善环境准备、增量构建、运行和失败定位说明，组织 A5 受影响路径回归 | 用例 `doc/`、构建与运行脚本、相关测试 | 黄区从新目录复现 | 固定版本可复现，源码、fixture、产物及运行结果对应 |

```text
蓝区：构建与组包逻辑 ──────────────────────────────┐
黄区：Host plan 解码、目标核编译复核 ──────────────┤
黄区：Q1–Q4 接口依据 → 蓝区：公共平台与 percounter 适配
                                                  ↓
                                    percounter 基础用例验证
                                                  ↓
                                    A6 percounter 完整 SWA
                                                  ↓
                                        固定交付与回归

Q5 计时依据 → 超时单位核验与后续性能统计
```

### 步骤 1：接通构建和组包

**当前缺口：** `compile_kernels.py` 已支持 A6；`prepare.py build` 只接受 A5，并固定校验、记录 578 个实例；`prepare_plan.py` 独立输出 A6 plan，尚未接入完整组包。两份 kernel 编译入口各自组织直接编译。

蓝区修改：

- [ ] 将原始 fixture 校验、目标 plan 转换、核编译、Host 工具构建和 callable 组装接成可独立重试的流程。A5 与 A6 各自采用当前有效的任务描述和实例数。
- [ ] 在目标 Host 解码原 plan，核对 2735 条记录的语义，再转换 t22/t28；将转换后的 plan 装入 A6 运行包，原始 fixture 保留为来源。
- [ ] 在 `production/CMakeLists.txt` 中梳理平台与参数接口头文件来源，使 native-runner、replay、record-tool 与 percounter 使用同版本契约。
- [ ] 复用 Simpler 的编译缓存，按平台、编译器、PTO-ISA、源码与头文件依赖区分产物；核编译、Host 工具、plan 和组包分别管理。
- [ ] 生成构建清单，记录目标平台、kernel 注册、实际 plan、任务数、实例数及运行包内容。

**验收：** 离线检查能识别原始 A5 plan 和转换后的 A6 plan；A6 使用 16 个任务、570 个实例；重复构建复用缓存，单核修改只重编受影响目标并重新组包。完整运行包在步骤 2、3 的接口确定后联调。

### 步骤 2：接入公共平台与共享生命周期

**当前缺口：** `toolchain.py` 已有 A6 CCEC 目标，`platform_info.py` 的平台注册和运行时发现仍未包含 A6。核编译工具目前借用 A5 参数接口头文件，目标 Device ABI 仍待验证。

蓝区修改：

- [ ] 沿 `platform_info.py`、`toolchain.py`、`build_runtimes.py`、`runtime_builder.py`、`kernel_compiler.py` 接通 A6。分别配置 x86_64 Host、aarch64 AICPU 和 `dav-920r1-cube/vec` 工具链。
- [ ] 根据构建依赖确定 A6 平台目录与共享源码引用，构建 percounter、必要平台库和 dispatcher。
- [ ] 根据 Q1/Q2 实现物理核、逻辑 C/V 对、驱动资源 ID 和寄存器窗口映射；参考入口为 `src/a5/platform/onboard/host/host_regs.cpp` 与 `platform_config.h`。
- [ ] 根据 Q3/Q4 核对 SSBUF 共享范围、访问屏障、联合启动、READY/完成/EXIT 握手以及参数可见性。
- [ ] 适配 percounter 复用的 Host orchestration 和 AICPU 生命周期；运行时、kernel 与 replay 的 ABI 同步更新。
- [ ] 在架构预检中识别现场 Ascend960DT，使用 Q5 核验超时与计时单位。

**黄区返回：** Q1–Q5 逐项答案与原始依据，目标 Host 的 plan 检查结果、SDK 编译结果和设备使用方式。

**验收：** 组件加载、基础 AIC/AIV 调用、参数读写、重复启动及正常退出通过。基础调度链在步骤 3 的 percounter 路径内验证。

### 步骤 3：适配 percounter 调度

以下路径均相对于 `src/a5/runtime/percounter/`，作为 A6 实现的现有代码入口。

| 文件 | 需要处理的内容 | 验收重点 |
| --- | --- | --- |
| `build_config.py` | 架构发现、共享源文件与 include 顺序；保留 percounter 自有任务映像及 AICore 入口 | 构建选择正确，实际加载 percounter |
| `host/resource_order.h` | 当前 worker 排列含 `cluster * 3`、`worker / 3`、`worker % 3` 与三 lane 遍历 | 1C1V 分配、回收、排序及容量一致 |
| `runtime/scheduler/ssbuf.h` | 当前采用 A5 偏移 2 KiB、大小 1 KiB 区域 | A6 布局、容量、发布与读取屏障正确 |
| `aicore/lane_loop.h`、`runtime/scheduler/wire_types.h` | 协调者、参与 mask、任务领取、参数发布、会合、完成及代际复用 | 每个有效 block 正好执行一次，实际参与者完成后发布完成 |
| `runtime/scheduler/gm.h`、`async_completion.h` | 原子访问、完成计数、依赖可见性与退出判断 | 消费者就绪顺序正确，重复运行状态正确 |
| `host/image/image_pack.h`、`runtime/task_image_layout.h`、`aicpu/graph_prepare.h` | Host 打包、AICPU 物化和 AICore 读取的数据契约 | Tensor、标量、block、mask、同步与依赖一致 |

- [ ] 核对上述 A5 假设，落实到 A6 当前平台契约，生产者、消费者和测试同步修改。
- [ ] 复用现有 acquire/cohort 测试语义，覆盖普通 AIC/AIV 依赖、1C1V MIX、sync_start、超出物理核数的多波次，以及连续调用和 Worker 重建。
- [ ] 实现前核对主仓对完成观察、参数预打包、SSBUF 和 MIX 准备的相关改动，选定集成基线并冻结验证版本。

**验收：** percounter 基础用例正常执行和退出，任务完成计数与实际执行集合一致。此阶段直接使用 percounter，HBG/common 按共享依赖参与构建。

### 步骤 4：完整 SWA 功能验证

蓝区修改与检查：

- [ ] `run.py` 和 `production/run.sh` 参数化平台、运行库、预检与设备选择，A6 目标选择 percounter。沿用黄区确认的占用方式，保留环境检查和错误提示。
- [ ] 接通每轮输入恢复、30 个可写 Device buffer 的参考比较、异常退出、日志和结果汇总。分别记录功能结果和计时数据。
- [ ] 检查 `sparse_gather_vf.cpp`：48 个 1C1V block 覆盖原 24 个 1C2V block 的两半 head；核对 token/partial 槽位、KV gather、UB 和事件使用。
- [ ] 检查 `o_proj_a.cpp`：32 个 block 下单 V 与内部列循环覆盖完整输出，核对量化和 READY/RELEASE/STORE_DONE 顺序。
- [ ] 准备可区分前后半 head/列的非零小样本，针对两组 MIX 核检查漏算、重复写回与偏移；完整 SWA 继续使用固定 fixture。

**验收：** 黄区运行 A6 percounter SWA，核对 16 个任务、570 个实例及完整计算覆盖，逐轮输出比较通过，重复运行与退场正常。参考来自现有固定数据；独立 HBG 运行结果不作为验收依赖。

### 步骤 5：交付与增量回归

- [ ] 整理环境检查、构建、运行和结果收集命令，每条命令标明输入、输出和通过条件；黄区 agent 按固定步骤执行并返回报告及小日志。
- [ ] 在新构建目录复现交付版本，确认只需要 Simpler、配套 PTO-ISA、CANN 和基础构建工具，使用已有设备 C++ 省去上游生成链路。
- [ ] 对修改涉及的 A5 构建、共享生命周期和计算核执行定向回归，A5 与 A6 结果分别归档。
- [ ] 按可独立构建和验证的边界整理提交：构建与组包、公共平台与 percounter、SWA 功能与交付。黄区按固定版本更新。

| 修改内容 | 重建范围 |
| --- | --- |
| 单个 kernel 或其头文件 | 受影响的 AIC/AIV 编译目标，再组装 callable |
| plan 转换 | 转换与语义检查，再组包 |
| Host 工具或 Tensor/参数 ABI | 相关工具及依赖组件，再核验 plan 和组包 |
| percounter 或平台代码 | 受影响运行时、dispatcher 与共享依赖，再运行对应基础检查 |
| fixture | 数据覆盖检查及完整输出校验 |
| 工具链、PTO-ISA 或平台版本 | 按身份失效相关缓存，重验目标组件 |

功能交付通过后，另行安排 A5/A6 percounter 性能比较及硬件优化。
