# A6 percounter SWA 迁移分析与实施对齐

[返回索引](../README.zh-CN.md) · [环境核对](a6-environment.zh-CN.md)

蓝区待修改总表、实施顺序和逐步验收统一见 [A6 percounter SWA 分步实施任务](a6-adaptation-tasks.zh-CN.md)。percounter 复用 HBG 的部分 Host orchestration 和 AICPU 生命周期，同时使用独立任务映像与 AICore lane loop。本次按这些实际依赖适配共享代码，直接在 percounter 路径完成基础测试和 SWA 验收。

## 1. 移植起点（2026-11-17）

**目标为 A6 单卡生产 percounter SWA。复用已有设备 C++、fixture 和 HBG/common 共享代码，完成构建、功能校验与正常退场。** A5 基线已单独提交；A6 的核编译入口、两个 MIX 核及任务描述转换已实现，本地 19／19 个核通过编译、链接和机器码提取。下表记录首次移植时的条件。11 月 19 日更新的[硬件对照表](a6-result.md#21-拓扑与参数)与[SWA 实测对照](swa-l4-comparison.zh-CN.md)包含后续上板结果。

| 项目 | 当前状态 | 对工作的影响 |
| ---- | -------- | ------------ |
| SWA 提取 | C++、19 个核的选择清单、单卡输入／plan／参考已在用例目录；A5 已通过 | 复用现有材料，不把跑通双卡整网当成前提 |
| A6 工具链 | 独立编译入口使用 `dav-920r1-cube/vec`，PTO-ISA 与远端同 pin | 本地原始核 17／19 通过，适配后 19／19 通过；尚无设备数值结果 |
| 平台与 percounter | 当前没有 a6 平台入口和经过验证的 A6 运行时 | 需要处理 Host、AICPU、AICore、dispatcher 的构建和启动链 |
| 两组 MIX 计算 | 按 PTO-ISA 明确的 1C1V 改写，分工见下文 | A5 目标的 19 个机器码指纹与改动前完全相同；A6 正确性待上板 |
| 输入 ABI | 本地原生 C++ 解码 2735 条记录，与归档语义指纹相同 | 远端 x86_64 仍须运行同一检查；通过后再使用转换的 plan |
| 构建与现场执行 | CMake 版本、Ninja、项目 venv，以及无 task-submit 的运行入口尚需处理 | 属于构建与交接工作；与计算正确性问题分开解决 |

A5 基线是 **16 个任务、578 个执行实例**；A6 转换后为 **16 个任务、570 个执行实例**。只改 t22／t28 的 lane 及 t22 的 block 数；全部 Tensor 字段、标量、依赖和其余任务逐项比对不变。原始 fixture 不覆盖。

## 2. 关键代码及拟采用的处理方式

### 平台、运行时与构建

| 位置 | 需要核对／处理 |
| ---- | -------------- |
| [platform_info.py](../../../../simpler_setup/platform_info.py)、[toolchain.py](../../../../simpler_setup/toolchain.py)、[build_runtimes.py](../../../../simpler_setup/build_runtimes.py) | 增加 A6 目标识别、编译与构建选择。Host 使用 x86_64 工具，AICPU 使用 aarch64 交叉工具，AICore 使用目标 ccec |
| [platform_config.h](../../../../src/a5/platform/include/common/platform_config.h)、[resource_order.h](../../../../src/a5/runtime/percounter/host/resource_order.h) | A5 配置是 36 个 block、每 block 1C2V，MIX 还涉及 lane mask、确认与完成协议。资源数量 54／54 不足以直接填新常量 |
| [onboard 平台实现](../../../../src/a5/platform/onboard/) | 核对 AICPU 启动、亲和与握手、核编号、寄存器、共享缓冲、内存可见性和时间戳；逐项确认可复用部分 |
| [prepare.py](../prepare.py)、[run.py](../run.py)、[production/CMakeLists.txt](../../dsv41_scheduler/production/CMakeLists.txt) | 当前 platform、include、运行库路径和预检仍面向 A5；新增 A6 构建与执行路径，A6 选择 percounter |
| [query](../../../../tools/cann-examples/query/query.cpp)、[预检脚本](../../../../.claude/skills/onboard-arch-precheck/check.sh) | 正确识别 Ascend960DT；无 task-submit 时按当地确认的设备占用方式执行，不能靠伪造环境变量绕过当前入口 |

建议复用确认兼容的公共逻辑，集中隔离硬件差异；不预先复制整套 A5 后端，也不假定所有 A5 平台代码都可复用。A6 核、运行时、dispatcher、Host replay 成套构建，输出和缓存与 A5 分开。

### 两组 MIX 核：改的是数据和同步协议

[任务清单](../../dsv41_scheduler/workloads/pypto_lib_latest/swa/tasks.tsv) 中，t22 为 24 个 block、t28 为 32 个 block，均是 **1 个 AIC＋2 个 AIV** 的逻辑任务。

以 [o_proj_a.cpp](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/o_proj_a.cpp) 为例：

```text
A5：AIC 生成 256 列结果
       ├─ DualModeSplitN → AIV0 的 UB：前 128 列 → 量化与写回
       └─                → AIV1 的 UB：后 128 列 → 量化与写回
    AIC 等待两份 RELEASE／STORE_DONE，再推进或结束
```

这里 **MIX 是一个任务由 C 核和 V 核共同完成**；lane 是任务内部的执行角色，例如 C、V0、V1，不是 rank，也不是另一张卡。

同 pin PTO-ISA 的 `include/pto/npu/a6/SyncAll.hpp` 明确写出 A6 一个 C 配一个 V，并删掉第二个 V 的信号等待。这是选择 1C1V 的依据，不是由 54／54 的核数猜出来的。

**t28 输出投影：每次算 128 列，增加内部列循环。** A5 每次算 256 列交给两个 V；A6 每次算 128 列交给一个 V，后续循环继续算另一半。保留原量化与写回算法，只使用一个消费者的 READY／RELEASE／STORE_DONE 信号。32 个 block 不变，实例从 96 变为 64。

**t22 稀疏 Attention：两个 1C1V block 分担原来一个 1C2V block 的 head。** 新 block `2b` 处理 head 0–31，`2b+1` 处理 head 32–63；两者各自 gather 完整 KV。核内用 `block/2`、`blocks/2` 保持原 token、区间和 partial 槽位归属，用 `block%2` 决定输出哪半 head。原 24 个 block 改为 48 个，实例从 72 变为 96；输入、输出和工作区大小不变。

Attention 保留现有 softmax、PV 累积和分片合并算法；C 核改算 32 行并向单 V 搬运。单 V 的 gather 从 32 扩到 64 条，因此 raw／NZ 缓冲增大，UB 为 **333184 B（325.375 KiB）**，小于现场报告的 376 KiB。NZ 的 MTE3↔V 事件使用 5／6／2／3，P staging 用 7；全部在编译器要求的 0–7 范围内，且与 MTE2↔V 的 raw 事件处于不同管线对。

```text
原 t22：b → C(64 heads) + V0(32 heads) + V1(32 heads)
A6 t22：2b   → C(前 32 heads) + V(完整 KV、前 32 heads)
        2b+1 → C(后 32 heads) + V(完整 KV、后 32 heads)
```

这版没有引入 GM 中转或新增工作区。分开 head 会重复读取 KV，输出投影的列循环也增加，因此当前是功能适配候选，不能把后续跨代性能差值都解释为调度收益。AIV 独立任务的 80／64／64 个逻辑 block 保留，运行时需支持多波次推进。

### Tensor／plan ABI 与输入复用

[record.h](../../dsv41_scheduler/production/record.h) 直接保存 `Header`、`Operand` 和 `TensorData`，读取时只有 magic 与 `sizeof(Operand)` 等检查。这不是跨架构的自描述格式。

[prepare_plan.py](../prepare_plan.py) 在目标 Host 编译原生 `record-tool` 和转换工具，解开原 fixture 后核对全部 **2735 条记录的规范化语义指纹**，覆盖 Tensor 字段、shape／stride／offset、别名、buffer 标识、标量及依赖。解码不一致立即报错，不继续转换。随后只改两处 MIX 描述，再逐字段检查其余数据不变。原捕获和 A6 plan 分开保存；这验证 Host 记录格式，不替代 A6 Device 的参数 ABI 验证。

复用的是 [输入与参考](../fixtures/fixture.json)，A5 的核机器码不进入 A6 运行包。如果改变 MIX lane 结构，应显式重建对应任务描述并保留变更清单，不修改原始 fixture。按实际使用的 kernel ID 重编组包可继续借鉴 [tmr_prepare.py](../../dsv41_scheduler/production/tmr_prepare.py) 的做法，执行路线为 percounter。

## 3. 工作顺序与阶段产物

**顺序是定位问题的建议，不是要求全部串行等待。** 输入 ABI 检查、构建入口和核方案可以同时准备；涉及未知硬件接口的实现以资料或探针结果为依据。

| 步骤 | 做什么 | 交付／通过条件 |
| ---- | ------ | -------------- |
| 已完成：核与 plan | A6 目标编译、1C1V 核改写、plan 转换和离线检查 | 本地 19／19 核编译／链接／提取通过；2735 条原记录解码一致，转换只改约定字段 |
| 待完成：平台与 percounter | 取得硬件接口依据，接入公共平台及 percounter 的 1C1V、SSBUF、领取与完成协议 | percounter 普通 AIV／AIC、依赖链、MIX、sync_start 及重复启停通过 |
| 待完成：完整 SWA | 现场编译、Device ABI 核对、组包加载与单卡执行 | 保留原有全部可写输出检查，并准备两组 MIX 的非零定向验证 |
| 后续：percounter 性能 | 首轮跑通后再决定测量安排；A5 先沿用已有归档 | 不作为本轮跑通的交付前提 |

这里做代码与离线检查，A6 端做实际 SDK 编译及设备验证。每次返回明确的失败阶段、命令、版本和小日志，避免一次堆积平台、核和输入三类问题。A6 端无需为了迁移此切片先装 PyPTO／PTOAS 或跑整网。

CMake／Ninja／`.venv` 的处理写入 [复现前的构建环境说明](usage.zh-CN.md)。沿用当前运行时构建时，CMake 3.20 有实际 DEPFILE 使用依据；无需升级系统软件，可以在项目环境提供。更换生成器或兼容旧 CMake 属于另一种构建适配，不能只改最低版本声明。

## 4. 已确认范围与提交安排

| 事项 | 当前决定 |
| ---- | -------- |
| 目标 | 完成精简 SWA 在 A6 单卡 percounter 上运行，交付范围聚焦该用例及其依赖 |
| A5 基线 | 已验证的构建／运行脚本、fixture、统计结果和文档先形成一个本地提交，后续适配与它分开 |
| 后续提交 | 使用中文标题与说明，按构建／平台、MIX 核、组包／运行入口等具体修改拆分；不把所有适配混成一次提交 |
| 正确性 | 使用已有 fixture 和参考逐字节检查，并准备两组 MIX 的非零定向验证；出现差异后定位计算与精度原因 |
| 性能 | 先跑通再说；对照先沿用已归档 A5 数据，不安排本轮 A5 重测 |
| 分工 | 本地修改和离线检查，A6 端用实际 SDK 编译、单卡执行并返回日志 |
| Git 协作 | 蓝区维护开发分支与交付版本，黄区同步固定版本并返回执行结果 |
| 设备 | 单卡使用方式由 A6 端安排，复现命令按当地环境提供 |
| 待补依赖 | A6 percounter 所需的物理核编号／寄存器映射、SSBUF 与启动接口依据；已有 1C1V 的 PTO-ISA 证据不能替代这些平台接口 |

建议的提交粒度是“增加 A5 SWA 精简用例”“接入 A6 所需的平台与构建”“适配 SWA 的 A6 MIX 数据与同步”“接通 A6 SWA 组包与单卡运行”。实际以可独立审阅的改动边界拆分，不预先承诺尚未查明的核实现。

### 运行时还缺什么

本次检查的主线为 `254fe41ba225e056d012f4ca3a92b3c1388830f6`，没有 `src/a6` 后端。当前新增的是核编译目标，未将 A5 的运行时冒充为 A6。

| 现有代码 | A5 写死的约定 | A6 需要的依据 |
| -------- | ------------- | ------------- |
| `src/a5/platform/onboard/host/host_regs.cpp` | 2 die、每 die 18 个 C，以及 C／V0／V1 的索引和寄存器窗口偏移 | `halResMap(RES_AICORE)` 的合法索引、返回窗口布局、核 ID 到 C/V 对的映射 |
| `src/a5/platform/include/common/platform_config.h` | `DATA_MAIN_BASE`／`COND` 等偏移、SSBUF 大小、物理核上限 | A6 对应定义或已可工作的平台代码；不能只把 36 改成 54、3 改成 2 |
| percounter AICore 入口与组内同步 | 核 ID、SSBUF 和组内 lane 共同决定任务认领、完成与退出 | A6 的共享缓冲可见性、容量和访问约定；1C1V 的启动方式 |
| 计时常量 | A5 使用自己的计时器频率 | A6 实际计时源；1800 MHz Cube 主频不能直接代入 |

若已有 A6 Simpler 分支，优先复用其平台实现；否则需要 SDK／硬件接口材料中的上述定义。**不要求 A6 端先跑通 SWA，也不要求补采整网；现在需要补的是平台接口依据。** 取得这些信息后，接通生产 percounter、组包与单卡运行入口。

## 5. 验收与性能解释

| 项目 | 依据与边界 |
| ---- | ---------- |
| A5 已有功能证据 | HBG／percounter 各 11 轮通过，每轮比较 30 个可写 Device buffer；这是已有基线，不扩展本轮 A6 范围 |
| A6 功能 | 真实 percounter 执行、MIX 依赖与完成正确，计算覆盖完整；使用固定输入与参考及 MIX 定向验证 |
| 实例数 | 原始基线为 16 任务／578 实例；若配对变化，列清差异并证明数学工作量完整，不能只追求计数相同 |
| 构建独立性 | 不调用 PyPTO／PTOAS；保留源与工具指纹、正式编译／链接命令，排除 A5 核缓存误用 |
| 性能（后续） | 首轮不以性能为交付前提；后续使用现有统计器，AICore 窗口与 Device wall 分列；硬件、Host 架构、SDK、分片和中转差异都注明，不能把 A5→A6 差值归为调度收益 |
| 数据限制 | 零权重 fixture 通过不能替代真实权重精度；出现跨代误差先定位，不静默放宽检查；L3 不混入 L0 样本 |

SWA 切片不覆盖双卡通信或 defer_wait。后续扩展 MoE 时也需区分 DSL 固定回放与 native Host 编排；原 `pypto_lib_latest/moe` 性能用例记录 `numerical_validation: false`，不能沿用 SWA 的数值校验结论，见 [原用例说明](../../dsv41_scheduler/README.md)。

## 6. 2026-11-17 本地验证记录

证据在 [results/2026-11-17-a6-offline](../results/2026-11-17-a6-offline/)，约 62 KiB；编译目标是 A6，执行检查的 Host 仍是本地 aarch64，**没有运行 A6 设备**。

| 检查 | 结果 | 能说明什么 |
| ---- | ---- | ---------- |
| 原始 A6 核 | 17／19 编译、链接和提取通过 | 复现两个 DualMode 搬运报错 |
| 适配后 A6 核 | 19／19 编译、链接和提取通过 | 已消除编译链阻塞，不代表核同步或数值正确 |
| A5 改前／改后 | 19 个核的 `.text` SHA256 逐一相同 | 本次条件适配没有改变已验证 A5 核的机器码 |
| Host plan | 原始 2735 条记录语义一致；仅两处约定转换 | 本地转换未改输入、标量或依赖；x86_64 解码待现场执行 |
| 拒绝重复转换 | 非零退出，未创建输出 | 不会把已经翻倍的 Attention block 再翻倍 |
| 原有 fixture 检查 | 2 项通过 | 输入／参考覆盖及损坏检测仍有效 |
| A6 设备执行与参考比较 | 未执行 | 平台接口资料与启动适配尚缺，不能宣称跑通 |

编译入口曾因 include 顺序误用 SDK 自带 PTO，已改为优先使用仓库 pin；不把该次结果当作原核基线。
MIX 初版还遇到 NZ 事件超出 0–7 的错误，按不同管线对重新安排后通过。
相关失败日志压缩保留；最终源码指纹、编译参数、版本、计划转换与 A5 机器码对比均可核查。
最终两次目标编译的 UTC 起止时间见 `*-after-run.json`；早期基线未记录精确起止时间。

复现使用 [使用方法](usage.zh-CN.md) 的两条离线命令。原始输入仍是 `fixtures/swa.tar.gz`；核二进制留在本地 `build/`，不提交到仓库。A5 上板性能沿用已有归档，本轮没有新增性能数字。
