# A6 环境核对与待补信息

[返回索引](../README.zh-CN.md) · [迁移分析](a6-migration.zh-CN.md)

## 1. 当前结论与证据范围

**环境信息已收到，不再要求 A6 端从头填表。首轮只验证 HBG 的独立 SWA，percounter 暂不考虑。** 已知编译目标和两个不兼容的计算核；实际 MIX 配对、运行时启动和端到端正确性尚未验证。

资料来自 2026-11-17 的本地交接文件 `a6-env-reprot.md`、`a6-evidence-2026-11-17`。本文提取脱敏后的事实，并与当前源码核对；原件含机器路径，仅作本地参考。报告中的建议不等同于实测结论。

| 项目 | 收到的信息 | 证据及限制 |
| ---- | ---------- | ---------- |
| 设备 | Ascend960DT_966B7／Ascend960DT，真机，设备 0 | 原始 query 输出及设备节点；报告称仅有一张卡 |
| Host | x86_64，Ubuntu 20.04.6 | 原始系统输出；A5 基线 Host 为 aarch64 |
| 可见计算资源 | AIC 54、AIV 54、AICPU 8；Cube 1800 MHz | query 输出；数量不等于 MIX 配对规则，Cube 频率不等于已确认的计时器频率 |
| 存储 | L1 512 KiB、L0A/B 各 64 KiB、L0C 256 KiB、UB 376 KiB、L2 128 MiB；可见 HBM 175.88 GiB | 原始查询值；不能据旁边的固定注释推断 die／cluster 归属 |
| CANN | 9.3.0，组件时间戳 `20261103_000323501` | 版本输出；使用选中的 SDK，避免落到另一份旧 SDK |
| 编译目标 | `dav-920r1-cube`／`dav-920r1-vec`；`__NPU_ARCH__=9201`、`__CCE_AICORE__=920` | 架构宏和 ini 节选；`dav-9201-*` 被编译器拒绝 |
| 编译与链接 | 报告记录 ccec clang 15.0.5；LLD 15.0.5；AICPU 交叉 g++ 14.3.0 | Host 工具使用 x86_64；AICPU 工具目标仍是 aarch64，两者要分开 |
| 驱动 | `7.12.T0.0.B280`，ascendhal `7.35.23` | 原始版本输出 |
| PTO-ISA | `83b1b2b52ded9ec5d91e02532a57cd95e497ba86`，与本分支 pin 相同 | 报告称工作树干净；本地同 SHA 的 A6 宏与静态断言已核对 |
| Simpler | A6 端为 `a6-migrate-case@4b2d9ca4b501c57abeea4a9dc86e0f6d08bedab4` | 该提交尚不包含本地新增的独立 SWA 入口、夹具和 A5 复测；需要同步这些工作树改动 |
| Host 构建工具 | Python 3.11.14／3.14.8，g++ 9.4.0，CMake 3.16.3；无 Ninja、项目 `.venv` | 报告及工具输出；构建环境处理见 [使用方法](usage.zh-CN.md) |
| 设备与代码交接 | 未找到 task-submit、npu-smi；报告称暂不能 pull | 属于当地执行和同步方式待确认，不等于没有可用设备 |

## 2. 编译结果说明了什么

交接报告记录 **19 个（源码、core_type）组合中 17 个编译通过、2 个失败**。附带汇总没有逐核完整日志和 ELF，因此这里保留“远端报告的编译结果”口径；本地源码可以独立确认以下限制：

| 失败核 | 调用位置 | 同 pin PTO-ISA 中的限制 |
| ------ | -------- | ----------------------- |
| `_gather_sparse_vf_rows_aic` | [sparse_gather_vf.cpp](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/sparse_gather_vf.cpp) 的 `store_qk_final`、`TINSERT` 使用 `DualModeSplitM` | `include/pto/npu/a5/common.hpp` 的 `GetDualDstCtl` 对 A6 拒绝双目标搬运 |
| `_o_proj_a_aic` | [o_proj_a.cpp](../../dsv41_scheduler/kernels/pypto_lib_latest/vendor/external/o_proj_a.cpp) 的 `QuantizeOutput` 使用 `DualModeSplitN` | `include/pto/npu/a5/TMov.hpp` 的 `TMovCcToUb` 对 A6 只接受 `SingleModeVec0` |

**17 个通过只证明当时参数下的编译阶段通过。** 它没有证明正式链接、`.text` 提取、加载、AICore 调度或输出正确；两组 MIX 核的 AIV 部分即使能编译，也可能需要随 AIC 一起修改。

| 编译选项 | 当前处理依据 |
| -------- | ------------ |
| `-fno-jump-tables` | 建议保留。[elf_parser.py](../../../../simpler_setup/elf_parser.py) 只装载 `.text`，拒绝外置已分配数据；远端记录开关实验产生了不同的 `.rodata` |
| `-mllvm -cce-vf-aa-between-iters=true` | 先保留现有设置。远端记录编译器接受，且 4 个核开关前后 `.text` 相同；不能扩展为所有核或所有 VF 行为已经验证 |

完整阶段仍是：**编译 → 链接与 `.text` 校验 → 组包加载 → 设备执行 → 数值检查**。不能把当前 17／19 写成运行通过率。

## 3. 对原报告的修正与保留意见

| 原判断 | 当前核对后的结论 |
| ------ | ---------------- |
| A6 缺输入包，需双卡捕获或重新造夹具 | 本地已提供 [swa.tar.gz](../fixtures/swa.tar.gz) 和 [fixture.json](../fixtures/fixture.json)，包含 plan、单卡输入与参考；同步后无需重新做整网捕获。ABI 兼容性仍要检查 |
| 54 AIC／54 AIV 可直接用于改拓扑常量 | 这是资源数量，不能决定每个 MIX block 的配对、可用核编号或共享资源关系；不能直接把 1C2V 改成 1C1V |
| query 注释证明每 cluster 有 2 AIV、设备有 2 dies | [query.cpp](../../../../tools/cann-examples/query/query.cpp) 的“2 AIV per cluster”是固定打印文字；附件也未给出 die 数的独立查询结果 |
| 两个核改为两次 SingleModeVec0 就能解决 | 两次写 Vec0 不会自动写入另一个 AIV 的 UB；数据分片、接收端、信号和完成条件必须一起重做，方案见迁移分析 |
| AIV block_num 为 80／64／64，因此 A6 会无法启动或必然更慢 | 逻辑 block 不必等于物理核数，多波次有可行基础；A6 的资源映射与推进仍需验证，性能不能仅由核数推断 |
| A6 复用 A5 PTO 指令，因此运行时没有架构风险 | PTO-ISA 已有 A6 专用同步等实现。运行时的寄存器、共享缓冲、可见性、配对及启动协议还没有上机证据，不能宣称只改名称和数量就能运行 |

## 4. 只补影响实施的资料

已明确的型号、工具版本和目标字符串不用重复采集。以下是后续查证项，不要求对方先跑通 HBG：

| 待补信息 | 需要什么 | 用来决定什么 |
| -------- | -------- | ------------ |
| MIX 配对与同步 | 匹配型号的完整平台 ini；SDK 的 MIX launch、sub-block 编号、intra-block 信号与可访问 UB／共享缓冲说明或示例 | 是否能保留双 AIV 分工；核改写和调度 lane 映射 |
| 运行时硬件接口 | A6 的核编号／die 映射、寄存器或受支持启动接口、共享缓冲与计时器说明 | A5 平台代码哪些可复用、哪些必须替换；计时单位如何标定 |
| 两个失败与正式编译链 | 原编译脚本、两个完整报错；其余核的源码指纹及编译参数清单 | 对齐结果来源，并复查正式链接／组包是否还有问题；无需传大批目标文件 |
| 执行和交接方式 | 单卡占用方式，以及 pull 或离线文件同步是否可用 | 生成可实际执行的复现命令；不要求先安装 task-submit |

远端专有资料需要返回小文件或相关片段及来源，单独给一个远端路径无法在这里核对。缺失资料先标明未知，不把猜测写成平台常量。

## 5. 协作方式

这里完成源码分析、适配设计、代码修改与离线检查；A6 端使用实际 SDK 编译并运行，返回明确失败阶段与日志。远端目前没有带回足以在本机完成 A6 构建的 SDK，完整验证需要这一轮往返。

```text
同步同一份源码、SWA 夹具和版本清单
  → 核对 MIX／启动接口；处理项目构建工具
  → 复用已有最小任务验证 HBG；核对 MIX 接口
  → 两个核适配、SWA 组包和校验
  → 先完成跑通，性能另行安排
```

本地统一维护提交与 fork，A6 端负责同步代码、编译和单卡验证，不承担提交工作；设备使用由 A6 端安排。若当地仍不能 pull，可传带提交号与校验和的离线包。首个本地提交固化 A5 用例，后续 A6 修改分成多个中文提交，见 [迁移分析](a6-migration.zh-CN.md)。
