# A6 HBG SWA 迁移分析与实施对齐

[返回索引](../README.zh-CN.md) · [环境核对](a6-environment.zh-CN.md)

## 1. 目标、已有基础与阻塞点

**已确定：首轮只跑 A6 单卡 HBG 的独立 SWA，percounter 后续再考虑；构建和执行不调用 PyPTO／PTOAS。** 当前先固化可运行的 A5 精简用例；后续适配按改动内容拆成多个中文提交。尚未实施 A6 平台或计算核改动。

| 项目 | 当前状态 | 对工作的影响 |
| ---- | -------- | ------------ |
| SWA 提取 | C++、19 个核的选择清单、单卡输入／plan／参考已在用例目录；A5 已通过 | 复用现有材料，不把跑通双卡整网当成前提 |
| A6 工具链 | 远端给出 `dav-920r1-cube/vec` 及 `__NPU_ARCH__=9201`；PTO-ISA 与本地同 pin | 可以针对明确目标设计编译入口；17／19 是编译报告，不是运行结果 |
| 平台与 HBG | 当前没有 a6 平台入口和经过验证的 A6 运行时 | 需要处理 Host、AICPU、AICore、dispatcher 的构建和启动链 |
| 两组 MIX 计算 | 两个 AIC 核使用 A6 不接受的双目标 Acc→Vec 搬运 | 需要核对硬件配对后改写整个生产／消费协议，不能仅替换枚举 |
| 输入 ABI | 原快照来自 A5／aarch64 Host；A6 Host 是 x86_64 | 先核对布局和字段语义，再决定直接复用或转换 plan |
| 构建与现场执行 | CMake 版本、Ninja、项目 venv，以及无 task-submit 的运行入口尚需处理 | 属于构建与交接工作；与计算正确性问题分开解决 |

A5 基线的 **16 个任务、578 个执行实例**是原任务图规模。是否能原样保留取决于 A6 合法 lane 配对；优先保留计算语义、输入输出和依赖，结构变化须明确记录。当前没有证据支持承诺“只改两行即可跑通”。

## 2. 关键代码及拟采用的处理方式

### 平台、运行时与构建

| 位置 | 需要核对／处理 |
| ---- | -------------- |
| [platform_info.py](../../../../simpler_setup/platform_info.py)、[toolchain.py](../../../../simpler_setup/toolchain.py)、[build_runtimes.py](../../../../simpler_setup/build_runtimes.py) | 增加 A6 目标识别、编译与构建选择。Host 使用 x86_64 工具，AICPU 使用 aarch64 交叉工具，AICore 使用目标 ccec |
| [platform_config.h](../../../../src/a5/platform/include/common/platform_config.h)、[scheduler_cluster_mix.h](../../../../src/a5/runtime/host_build_graph/runtime/scheduler/scheduler_cluster_mix.h) | A5 配置是 36 个 block、每 block 1C2V，MIX 还涉及 lane mask、确认与完成协议。资源数量 54／54 不足以直接填新常量 |
| [onboard 平台实现](../../../../src/a5/platform/onboard/) | 核对 AICPU 启动、亲和与握手、核编号、寄存器、共享缓冲、内存可见性和时间戳；逐项确认可复用部分 |
| [prepare.py](../prepare.py)、[run.py](../run.py)、[production/CMakeLists.txt](../../dsv41_scheduler/production/CMakeLists.txt) | 当前 platform、include、运行库路径和预检仍面向 A5；新增 A6 构建与执行路径，首轮只选择 HBG |
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

这里 **MIX 是一个任务由 C 核和 V 核共同完成**；lane 是这项任务内部的执行角色，例如 C、V0、V1，不是 rank，也不是另一张卡。

“配对”具体指：这个 C 核能够直接给哪些 V 核的 UB 搬数据、发组内信号，并与它们同时执行。全卡一共有多少 C／V 核，并不能单独说明这个关系；当前只确认双目标搬运被 A6 后端拒绝，没有确认 A6 必须采用 1C1V。

如果最终选择一个 V 核处理完整结果，候选逻辑是：先处理前 128 列，再处理后 128 列，C 核改等这一个消费者的确认。两半计算都还在，变化的是谁来执行与如何同步。以 32 个 block 为例，原来每 block 启动 C、V0、V1 共 3 份核执行，即 96 个实例；若能等价改成 C、V 共 2 份，就是 64 个实例，V 内部多做一半工作。**这只是解释方案，不代表已经决定改配对或减少实例。**

代码中的 `get_sub_block_id(args) * 128` 决定 AIV 写哪一半，`VEC_OFFSET=16` 对应第二组同步标志。**只改成 SingleModeVec0 会同时留下数据覆盖、另一半结果和双向等待问题。** 对 [sparse_gather_vf.cpp](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/sparse_gather_vf.cpp) 同样要一起检查 `DualModeSplitM`、`signal_both/wait_both`、KV 生产、softmax/PV 分片与环形缓冲。

先查明合法配对，再选择实现：

| 硬件接口核对结果 | 可评估方案 | 必须同时验证 |
| ---------------- | ---------- | ------------ |
| 一个 MIX 组可合法使用两个 AIV，并有支持的数据通路 | 使用受支持的拆分传输或中转，保留双 AIV 分工 | 两个目的 UB、lane 标识、信号与完成协议，不能把两次 Vec0 写当成双目标写 |
| 只能使用一个配对 AIV | 让一个 AIV 处理完整输出或顺序处理两半，调整 AIC 发放和确认逻辑 | 计算覆盖、UB 容量、布局、循环次数与同步，重新生成相应任务描述 |
| 片上路径资料不足或适配暂时困难 | 若接受功能过渡版，可用 GM 中转解耦 | 显式依赖、可见性与额外搬运；性能须标明该实现差异 |

这些候选方案还没有选定。当前困难是：A6 允许的目的 UB 和组内信号关系未明确，两个核又把数据分片、流水缓冲和双消费者确认绑在一起；必须保证两半都算到且不会等一个不再执行的消费者。GM 中转可以绕开部分直接传输限制，但需要新增工作区、搬运与依赖，用户尚未决定采用。不是已证明可运行的实现。PTO-ISA 的 `TDeInterleave` 软件拆分例子不能直接证明 Acc→Vec 的目标选择可行。AIV 的独立核 block 数 80／64／64 也不必因物理核数较小而砍掉：保留逻辑工作量，验证 HBG 多波次推进。

### Tensor／plan ABI 与输入复用

[record.h](../../dsv41_scheduler/production/record.h) 直接保存 `Header`、`Operand` 和 `TensorData`，读取时只有 magic 与 `sizeof(Operand)` 等检查。这不是跨架构的自描述格式。

先在两个构建上核对 `sizeof/alignof/offsetof`、字段类型和字节序，再检查 shape／stride／offset、别名、buffer 标识及 kernel 签名；同大小不等于同语义，Host 架构不同也不自动等于不兼容。用原构建与 A6 构建的 `record-tool` 解码结果逐项比对；若不兼容，从原构建导出语义字段后重建目标 plan。

复用的是 [输入与参考](../fixtures/fixture.json)，A5 的核机器码不进入 A6 运行包。如果改变 MIX lane 结构，应显式重建对应任务描述并保留变更清单，不修改原始夹具。按实际使用的 kernel ID 重编组包可继续借鉴 [tmr_prepare.py](../../dsv41_scheduler/production/tmr_prepare.py) 的做法，执行路线仍是 HBG。

## 3. 工作顺序与阶段产物

**顺序是定位问题的建议，不是要求全部串行等待。** 输入 ABI 检查、构建入口和核方案可以同时准备；涉及未知硬件接口的实现以资料或探针结果为依据。

| 步骤 | 做什么 | 交付／通过条件 |
| ---- | ------ | -------------- |
| 1. 对齐版本与缺口 | 同步本地新增用例与夹具；确认 SDK、MIX／同步接口、设备占用方式；处理构建工具 | A6 能拿到同一份源码和输入；未知项有明确记录 |
| 2. HBG 最小启动 | 分别验证普通 AIV、普通 AIC，再验证带实际依赖的短任务链 | 生产 HBG Host 建图、AICPU 启动、AICore 调度与完成路径真实执行，结果通过 |
| 3. 两组 MIX 核 | 核对配对与同步接口，适配 t22／t28 的数据传输和消费者协议 | 保留原有输出检查；本轮不新增局部非零测试用例 |
| 4. 完整 SWA | ABI 核对、正式编译链接、组包加载，执行单卡 SWA | 对照参考验证全部可写输出；记录任务、实例和核实现差异 |
| 后续：HBG 性能 | 首轮跑通后再决定测量安排；A5 先沿用已有归档 | 不作为本轮跑通的交付前提 |

这里做代码与离线检查，A6 端做实际 SDK 编译及设备验证。每次返回明确的失败阶段、命令、版本和小日志，避免一次堆积平台、核和输入三类问题。A6 端无需为了迁移此切片先装 PyPTO／PTOAS 或跑整网。

CMake／Ninja／`.venv` 的处理写入 [复现前的构建环境说明](usage.zh-CN.md)。沿用当前运行时构建时，CMake 3.20 有实际 DEPFILE 使用依据；无需升级系统软件，可以在项目环境提供。更换生成器或兼容旧 CMake 属于另一种构建适配，不能只改最低版本声明。

## 4. 已确认范围与提交安排

| 事项 | 当前决定 |
| ---- | -------- |
| 目标 | 先完成精简 SWA 在 A6 单卡 HBG 上运行；不扩展通用 A6 能力、percounter、通信或整网 |
| A5 基线 | 已验证的构建／运行脚本、夹具、统计结果和文档先形成一个本地提交，后续适配与它分开 |
| 后续提交 | 使用中文标题与说明，按构建／平台、MIX 核、组包／运行入口等具体修改拆分；不把所有适配混成一次提交 |
| 正确性 | 使用已有夹具和参考；本轮不新增局部非零用例。先逐字节检查，出现差异后定位并对齐容差 |
| 性能 | 先跑通再说；对照先沿用已归档 A5 数据，不安排本轮 A5 重测 |
| 分工 | 本地修改和离线检查，A6 端用实际 SDK 编译、单卡执行并返回日志 |
| Git 协作 | 本地统一维护提交和 fork；A6 端不承担提交工作。此次先做本地 commit，不自动推送 |
| 设备 | 单卡使用方式由 A6 端安排，复现命令按当地环境提供 |
| 仍需解释与查证 | MIX 合法配对、lane／实例调整和 GM 中转方案尚未选定，不把候选方案当作用户已接受的要求 |

建议的提交粒度是“增加 A5 SWA 精简用例”“接入 A6 所需的平台与构建”“适配 SWA 的 A6 MIX 数据与同步”“接通 A6 SWA 组包与单卡运行”。实际以可独立审阅的改动边界拆分，不预先承诺尚未查明的核实现。

## 5. 验收与性能解释

| 项目 | 依据与边界 |
| ---- | ---------- |
| A5 已有功能证据 | HBG／percounter 各 11 轮通过，每轮比较 30 个可写 Device buffer；这是已有基线，不扩展本轮 A6 范围 |
| A6 功能 | 真实 HBG 执行、MIX 依赖与完成正确，计算覆盖完整；本轮沿用固定输入与参考，不新增非零用例 |
| 实例数 | 原始基线为 16 任务／578 实例；若配对变化，列清差异并证明数学工作量完整，不能只追求计数相同 |
| 构建独立性 | 不调用 PyPTO／PTOAS；保留源与工具指纹、正式编译／链接命令，排除 A5 核缓存误用 |
| 性能（后续） | 首轮不以性能为交付前提；后续使用现有统计器，AICore 窗口与 Device wall 分列；硬件、Host 架构、SDK、分片和中转差异都注明，不能把 A5→A6 差值归为调度收益 |
| 数据限制 | 零权重夹具通过不能替代真实权重精度；出现跨代误差先定位，不静默放宽检查；L3 不混入 L0 样本 |

SWA 切片不覆盖双卡通信或 defer_wait。后续扩展 MoE 时也需区分 DSL 固定回放与 native Host 编排；原 `pypto_lib_latest/moe` 性能用例记录 `numerical_validation: false`，不能沿用 SWA 的数值校验结论，见 [原用例说明](../../dsv41_scheduler/README.md)。
