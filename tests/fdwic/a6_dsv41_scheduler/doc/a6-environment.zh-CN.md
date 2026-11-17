# A6 环境核对与待补信息

[返回索引](../README.zh-CN.md) · [迁移分析](a6-migration.zh-CN.md)

## 1. 当前结论与证据范围

**环境信息已收到，不再要求 A6 端从头填表。首轮只验证 HBG 的独立 SWA，percounter 暂不考虑。** 已知编译目标；同 pin PTO-ISA 的 `include/pto/npu/a6/SyncAll.hpp` 明确采用 1C1V，删除了 A5 第二个 V 的信号等待。运行时启动和端到端正确性尚未验证。

资料来自 2026-11-17 的 [现场报告](a6-env-reprot.md) 与 [原始查询输出](a6-evidence-2026-11-17)，已作为历史材料提交，用户名及机器专属路径替换为占位符。本文与当前源码核对；报告中的建议不等同于实测结论。

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
| Simpler | 首次采集时 A6 端为 `a6-migrate-case@4b2d9ca4b501c57abeea4a9dc86e0f6d08bedab4` | 该提交尚不包含本地新增的独立 SWA 入口、夹具和 A5 复测；需要同步后续提交 |
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
| 54 AIC／54 AIV 可直接用于改拓扑常量 | PTO-ISA 已提供 1C1V 的独立源码依据，但资源数量仍不能决定物理核编号、寄存器映射或共享资源布局 |
| query 注释证明每 cluster 有 2 AIV、设备有 2 dies | [query.cpp](../../../../tools/cann-examples/query/query.cpp) 的“2 AIV per cluster”是固定打印文字；附件也未给出 die 数的独立查询结果 |
| 两个核改为两次 SingleModeVec0 就能解决 | 两次写 Vec0 不会自动写入另一个 AIV 的 UB；数据分片、接收端、信号和完成条件必须一起重做，方案见迁移分析 |
| AIV block_num 为 80／64／64，因此 A6 会无法启动或必然更慢 | 逻辑 block 不必等于物理核数，多波次有可行基础；A6 的资源映射与推进仍需验证，性能不能仅由核数推断 |
| A6 复用 A5 PTO 指令，因此运行时没有架构风险 | PTO-ISA 已有 A6 专用同步等实现。运行时的寄存器、共享缓冲、可见性、配对及启动协议还没有上机证据，不能宣称只改名称和数量就能运行 |

## 4. 给 A6 端 agent 的补充查证任务

**目标：查清 A6 HBG 与硬件对接所需的规则，返回有出处的答案；本轮只查询资料，不要求实现运行时或跑通 SWA。** 目标型号为 `Ascend960DT_966B7`，编译目标为 `dav-920r1-*`。已有 54 AIC／54 AIV、1C1V 的依据，不必再重复证明核数和配对数量。

两个 MIX 核已经改写，本地 19／19 个 A6 核通过编译、链接和机器码提取，见 [本地验证记录](a6-migration.zh-CN.md#6-2026-11-17-本地验证记录)。当前需要补齐下面的接口规则；核能编译不等于运行时能正确启动和协调这些核。

### 需要回答的问题

| 编号 | 要查的答案 | 用途与当前 A5 代码 |
| ---- | ---------- | ------------------ |
| Q1 核编号 | `get_coreid()` 在 C／V 上的编码与有效位是什么？如何映射到同一组 C/V、逻辑 worker 及驱动 `res_id`？可用核编号是否连续，有屏蔽核时如何处理？ | 找对执行者和同组伙伴。`src/a5/platform/onboard/host/host_regs.cpp` 当前按 2 die、每 die 18 个 C 及双 V 排列计算索引；A6 不能只按 54／54 猜映射 |
| Q2 寄存器 | A6 上 `halResMap(RES_AICORE)` 的合法 `res_id`、进程类型、返回窗口布局是什么？C/V 窗口偏移，以及 `DATA_MAIN_BASE`、`COND`、`CTRL` 的偏移、访问宽度和允许读写方是否兼容 A5？ | 用于启动／状态／退出握手。`src/a5/platform/include/common/platform_config.h` 的 A5 数值是参考，不能直接作为 A6 结论；若应换用其他受支持接口，给出该接口或样例 |
| Q3 SSBUF | A6 的 SSBUF 容量和地址约定是什么？哪些 C/V 共享同一块区域？`__ssbuf__` 的读写可见性需要什么屏障，是否有预留区域？ | 同组调度器交换任务、准备与完成状态。A5 的 `scheduler_cluster_signal.h` 使用 3 KiB 中最后 1 KiB，并用 DSB 配合访问；需确认 A6 可用区域与同步规则 |
| Q4 启动样例 | 本机是否已有 A6 的 C/V 联合启动样例或 Simpler/HBG 适配分支？其中 blockDim、任务类型、sub-block 编号、AICPU 启动／退出如何配置？ | 优先复用已有平台实现。给出仓库、提交号和关键文件，不只给分支名或“支持 A6”的描述 |
| Q5 计时依据 | `get_sys_cnt()` 对应计时器频率及获取方法是什么？ | 后续计时与超时参数需要；1800 MHz Cube 主频不能直接代入。不必等这项齐全才返回 Q1–Q4 |

**找到函数声明，只能证明接口存在。** 还需确认规则适用于 A6；A5 实现、通用头文件、其他 Ascend960 SKU 都要标明来源，不能自动视为当前型号的依据。若资料明确说明与 A5 兼容，请返回那段说明。

### 直接执行的查询命令

在仓库根目录、已加载现场 CANN 环境的 shell 中执行。使用 `rg`，不新增采集脚本；输出写入用例的 `build/`，如果目录已有结果，先换一个输出目录名。

```bash
: "${ASCEND_HOME_PATH:?请先加载现场 CANN 的 set_env.sh}"
A6_INFO_DIR=tests/fdwic/a6_dsv41_scheduler/build/a6-interface-info
mkdir -p "$A6_INFO_DIR"

# 完整平台配置；判断以 Ascend960DT_966B7.ini 为准，其余型号仅供参考。
rg -n -L -g '*960*.ini' '^' "$ASCEND_HOME_PATH" \
  > "$A6_INFO_DIR/a6-platform-ini.txt" 2>&1

# SDK 中的定义、实现和说明，保留文件名、行号及上下文。
rg -n -L -i -C 3 \
  -g '*.h' -g '*.hpp' -g '*.c' -g '*.cpp' -g '*.ini' -g '*.md' -g '*.txt' \
  'ssbuf|DATA_MAIN_BASE|SPR_COND|set_cond|get_coreid|get_subblockid|halResMap|RES_AICORE|get_sys_cnt' \
  "$ASCEND_HOME_PATH" \
  > "$A6_INFO_DIR/a6-runtime-interfaces.txt" 2>&1
```

`rg` 返回 1 表示无匹配，返回 2 表示存在读取等错误；保留报错并区分“没有找到”与“没有权限读取”。这些命令只搜索文件，不调用设备接口，也不读写硬件寄存器。

随后查看命中位置的完整定义、周围注释和架构条件，按 Q1–Q5 整理答案。若 SDK 只有声明，可在本机已有的驱动头文件／源码、A6 示例、平台适配仓库或接口资料中继续找；记录搜索范围。不要通过试写未知寄存器、猜 SSBUF 地址或反复启动不匹配的运行时来代替资料查证。

### 返回材料与答案格式

返回上面两个文本文件，以及一份简短的 `a6-interface-answers.md`，按下表逐项填写。**不知道的填“未找到”，并写清查过哪里；推测单独标注。** 每项附相关原文或源码片段、文件相对路径和行号、SDK 版本或仓库提交号；单独给远端路径不足以供这边核对。

| 编号 | 结论／具体值 | 证据来源与片段 | 状态与剩余问题 |
| ---- | ------------ | -------------- | -------------- |
| Q1 核编号 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q2 寄存器 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q3 SSBUF | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q4 启动样例 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q5 计时依据 | 待填写 | 待填写 | 已确认／部分确认／未找到 |

分享时将机器专属路径替换为 `${ASCEND_HOME_PATH}`、`${ASCEND_DRIVER_PATH}` 或仓库相对路径，保留文件内部路径与行号。若部分规则只能从平台维护者获得，指出具体缺哪一项即可；不要求先跑通 HBG，也不用上传整套 SDK。

[使用方法](usage.zh-CN.md) 中的 `compile_kernels.py`／`prepare_plan.py` 是另外两项离线适配检查，可独立执行；它们的 `summary.json` 不能替代这里的硬件接口答案。

## 5. 协作方式

这里完成源码分析、代码修改与离线检查；本机 CANN 也接受 `dav-920r1-*`，可以先编译计算核。A6 端仍需用现场 SDK 复核编译并运行；本地目标编译通过不等于设备通过。

```text
同步同一份源码、SWA 夹具和版本清单
  → A6 端返回 Q1–Q5 的资料与答案
  → 这里完成平台适配，接通生产 HBG 的启动与完成路径
  → A6 端编译、单卡执行 SWA 并返回校验结果
  → 先完成跑通，性能另行安排
```

本地统一维护提交与 fork，A6 端负责同步代码、编译和单卡验证，不承担提交工作；设备使用由 A6 端安排。若当地仍不能 pull，可传带提交号与校验和的离线包。首个本地提交固化 A5 用例，后续 A6 修改分成多个中文提交，见 [迁移分析](a6-migration.zh-CN.md)。
