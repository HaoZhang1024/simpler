# A6 环境核对与待补信息

[返回索引](../README.zh-CN.md) · [迁移分析](a6-migration.zh-CN.md)

**11 月 19 日更新。** A6 单卡 percounter SWA 已通过正式 10 轮输出校验，A5/A6 的同级 L4 结果已入库。设备与工具链按平台并排列在[硬件对照表](a6-result.md#21-拓扑与参数)，L0 与逐任务 L4 见[时延对照表](swa-l4-comparison.zh-CN.md)。黄区当前在测 CntNotify 时延。[现场反馈与待办](a6-l4-feedback.md)

## 1. 首轮环境采集（11 月 17 日）

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
| Simpler | 首次采集时 A6 端为 `a6-migrate-case@4b2d9ca4b501c57abeea4a9dc86e0f6d08bedab4` | 该提交尚不包含本地新增的独立 SWA 入口、fixture 和 A5 复测；需要同步后续提交 |
| Host 构建工具 | Python 3.11.14／3.14.8，g++ 9.4.0，CMake 3.16.3；无 Ninja、项目 `.venv` | 报告及工具输出；构建环境处理见 [使用方法](usage.zh-CN.md) |
| 设备与代码交接 | 未找到 task-submit、npu-smi；报告称暂不能 pull | 属于当地执行和同步方式待确认，不等于没有可用设备 |

## 2. 首轮编译记录（适配前）

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

## 3. 首轮报告评审记录

| 原判断 | 当前核对后的结论 |
| ------ | ---------------- |
| A6 缺输入包，需双卡捕获或重新造 fixture | 本地已提供 [swa.tar.gz](../fixtures/swa.tar.gz) 和 [fixture.json](../fixtures/fixture.json)，包含 plan、单卡输入与参考；同步后无需重新做整网捕获。ABI 兼容性仍要检查 |
| 54 AIC／54 AIV 可直接用于改拓扑常量 | PTO-ISA 已提供 1C1V 的独立源码依据，但资源数量仍不能决定物理核编号、寄存器映射或共享资源布局 |
| query 注释证明每 cluster 有 2 AIV、设备有 2 dies | [query.cpp](../../../../tools/cann-examples/query/query.cpp) 的“2 AIV per cluster”是固定打印文字；附件也未给出 die 数的独立查询结果 |
| 两个核改为两次 SingleModeVec0 就能解决 | 两次写 Vec0 不会自动写入另一个 AIV 的 UB；数据分片、接收端、信号和完成条件必须一起重做，方案见迁移分析 |
| AIV block_num 为 80／64／64，因此 A6 会无法启动或必然更慢 | 逻辑 block 不必等于物理核数，多波次有可行基础；A6 的资源映射与推进仍需验证，性能不能仅由核数推断 |
| A6 复用 A5 PTO 指令，因此运行时没有架构风险 | PTO-ISA 已有 A6 专用同步等实现。运行时的寄存器、共享缓冲、可见性、配对及启动协议还没有上机证据，不能宣称只改名称和数量就能运行 |

## 4. 移植时的接口查证清单

**目标：查清 A6 percounter 与硬件对接所需的规则，返回有出处的答案；按文末计划逐步完成资料核对、离线复现与可执行的上板测试。** 目标型号为 `Ascend960DT_966B7`，编译目标为 `dav-920r1-*`。已知设备报告 54 AIC／54 AIV；本轮采集单次启动中的实际配对数量和来源。

两个 MIX 核已经改写，本地 19／19 个 A6 核通过编译、链接和机器码提取，见 [本地验证记录](a6-migration.zh-CN.md#6-2026-11-17-本地验证记录)。当前需要补齐下面的接口规则；核能编译不等于运行时能正确启动和协调这些核。

### 黄区查证顺序与交接

先复用已有 A6 平台代码和实测记录，再补齐下列接口。

| 顺序 | 本次重点 | 返回内容 | 对应工作 |
| ---- | -------- | -------- | -------- |
| 1 | 同事的公共平台实现与交付状态 | 可下载的代码版本、已改文件、构建命令、已验证范围；公共平台与 HBG 专有修改的边界 | 确定 percounter 接入位置，复用已有实现 |
| 2 | Q1/Q4：实际可用配对资源与启动编号 | 实际可分配和启动的 C/V 数、同组对应关系、保留或屏蔽核；worker_id、block_idx、sub_block_id、物理 core ID 对照及样例来源 | 转换后的 SWA t22 保持 sync_start，48 个 1C1V block 要求至少 48 组可用 C/V；验证是否满足 |
| 3 | Q2/Q3：寄存器与 SSBUF | 访问规则、窗口布局、共享范围、可用区间、kernel 使用区间及屏障依据 | 平台启动接口与 percounter 会合、完成协议 |
| 4 | Q6/Q7：数据布局与内存可见性 | 三端结构布局、编译配置，以及原子和缓存操作的适用说明 | 任务映像读取、参数发布和依赖完成观察 |
| 5 | Q5 及现场离线复核 | 计时频率、工具版本、plan 转换与 kernel 编译 summary | 超时配置和完整运行包准备 |

SWA 的 t9/t25/t35 分别为 80/64/64 个普通 Vector block，原始记录中 sync_start 均为 0；它们采用多波次。t22 的同步启动条件与这些普通任务分别检查。以上来自当前 fixture 的 record-tool 解码及现有 adapt-plan 转换规则。

### 接口问题明细

| 编号 | 要查的答案 | 用途与当前 A5 代码 |
| ---- | ---------- | ------------------ |
| Q1 核编号 | `get_coreid()` 在 C／V 上的编码与有效位是什么？如何映射到同一组 C/V、逻辑 worker 及驱动 `res_id`？可用核编号是否连续，有屏蔽核时如何处理？ | 找对执行者和同组伙伴。`src/a5/platform/onboard/host/host_regs.cpp` 当前按 2 die、每 die 18 个 C 及双 V 排列计算索引；A6 不能只按 54／54 猜映射 |
| Q2 寄存器 | A6 上 `halResMap(RES_AICORE)` 的合法 `res_id`、进程类型、返回窗口布局是什么？C/V 窗口偏移，以及 `DATA_MAIN_BASE`、`COND`、`CTRL` 的偏移、访问宽度和允许读写方是否兼容 A5？ | 用于启动／状态／退出握手。`src/a5/platform/include/common/platform_config.h` 的 A5 数值是参考，不能直接作为 A6 结论；若应换用其他受支持接口，给出该接口或样例 |
| Q3 SSBUF | A6 的 SSBUF 容量和地址约定是什么？哪些 C/V 共享同一块区域？`__ssbuf__` 的读写可见性需要什么屏障，是否有预留区域？ | 同组调度器交换任务、准备与完成状态。A5 percounter 的 `runtime/scheduler/ssbuf.h` 使用 3 KiB 中最后 1 KiB，并用 DSB 配合访问；需确认 A6 可用区域与同步规则 |
| Q4 启动样例 | 本机是否已有 A6 的 C/V 联合启动样例或 Simpler 平台适配分支？其中 blockDim、任务类型、sub-block 编号、AICPU 启动／退出如何配置？ | 优先复用已有平台实现。给出仓库、提交号和关键文件，不只给分支名或“支持 A6”的描述 |
| Q5 计时依据 | `get_sys_cnt()` 对应计时器频率及获取方法是什么？ | 后续计时与超时参数需要；1800 MHz Cube 主频不能直接代入。不必等这项齐全才返回 Q1–Q4 |
| Q6 数据布局 | 公共平台适配后，Host、AICPU、AICore 各自采用哪些 Tensor、Task、Payload 定义？kernel_id 槽位数、sizeof、alignof、关键 offsetof 是否一致？逻辑 lane 数改为 2 后，序列化槽位如何定义？ | percounter `host/image/image_pack.h` 与 `runtime/task_image_layout.h` 使用固定布局；保留自有 AICPU 图物化路径，核对三端 ABI。返回定义、编译参数和已有静态断言结果；现场用 `prepare_plan.py` 验证捕获数据的 Host 解码 |
| Q7 GM 原子与缓存 | A6 对当前 percounter 所用 GM 原子、DCCI、DSB 的宽度、对齐、可见范围有何要求？C/V、AICPU 及跨 die 观察依赖完成值后，读取参数和 Tensor 的屏障序列是什么？ | `runtime/scheduler/gm.h`、`async_completion.h`、`aicpu/graph_prepare.h`；返回 A6 资料或已验证样例及来源，用于完成计数和参数发布协议 |

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
  'ssbuf|DATA_MAIN_BASE|SPR_COND|set_cond|get_coreid|get_subblockid|halResMap|RES_AICORE|get_sys_cnt|dcci|dsb|atomic|compare_exchange' \
  "$ASCEND_HOME_PATH" \
  > "$A6_INFO_DIR/a6-runtime-interfaces.txt" 2>&1
```

`rg` 返回 1 表示无匹配，返回 2 表示存在读取等错误；保留报错并区分“没有找到”与“没有权限读取”。这些命令只搜索文件，不调用设备接口，也不读写硬件寄存器。

随后查看命中位置的完整定义、周围注释和架构条件，按 Q1–Q7 整理答案。若 SDK 只有声明，可在本机已有的驱动头文件／源码、A6 示例、平台适配仓库或接口资料中继续找；记录搜索范围。不要通过试写未知寄存器、猜 SSBUF 地址或反复启动不匹配的运行时来代替资料查证。

### 返回材料与答案格式

返回上面两个文本文件，以及一份简短的 `a6-interface-answers.md`，按下表逐项填写。**不知道的填“未找到”，并写清查过哪里；推测单独标注。** 每项附相关原文或源码片段、文件相对路径和行号、SDK 版本或仓库提交号；单独给远端路径不足以供这边核对。

| 编号 | 结论／具体值 | 证据来源与片段 | 状态与剩余问题 |
| ---- | ------------ | -------------- | -------------- |
| Q1 核编号 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q2 寄存器 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q3 SSBUF | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q4 启动样例 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q5 计时依据 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q6 数据布局 | 待填写 | 待填写 | 已确认／部分确认／未找到 |
| Q7 GM 原子与缓存 | 待填写 | 待填写 | 已确认／部分确认／未找到 |

分享时将机器专属路径替换为 `${ASCEND_HOME_PATH}`、`${ASCEND_DRIVER_PATH}` 或仓库相对路径，保留文件内部路径与行号。若部分规则只能从平台维护者获得，指出具体缺哪一项即可；返回与目标平台有关的接口片段及来源。

## 5. 黄区 agent 测试与反馈计划

从 Simpler 根目录执行。首次反馈优先回答两个问题：现场是否有可运行的 A6 Cube + Vector 联合启动入口；一次启动能证实多少对可同时工作的 Cube 和 Vector。各阶段单独记录结果，先反馈已取得的证据。

| 步骤 | 执行条件 | 测试与反馈 |
| ---- | -------- | ---------- |
| 1. 离线复现 | Simpler、匹配的 PTO-ISA、Host 编译器和现场 CANN | 记录版本，返回 fixture、plan、资源检查和 kernel 编译结果 |
| 2. 实测核映射 | 已分配 A6 单卡，现场已有适用于该型号的 C/V 联合启动样例 | 返回同一次启动的 worker 明细、完整配对数、配对依据和退出状态 |
| 3. 核对设备接口 | 可访问对应 SDK、平台源码或已验证样例 | 填写 Q1–Q7，优先处理影响启动、参数读取和完成计数的缺项 |
| 4. 验证 percounter | 已交付 A6 percounter 构建与运行入口，平台握手可用 | 先验证单个 MIX block，再单卡回放 SWA，返回执行集合和输出差异 |

### 步骤 1：复现离线输入与构建

首次下载使用空目录，在其中运行以下命令。已有 checkout 先用 `git status --short --branch` 确认版本及本地改动；已有 PTO-ISA 可直接核对版本。只需 Simpler 和 PTO-ISA 两个源码仓。

```bash
git clone --branch a6-swa-port --single-branch https://github.com/HaoZhang1024/simpler.git
cd simpler
git clone https://github.com/hw-native-sys/pto-isa.git build/pto-isa
git -C build/pto-isa checkout --detach "$(cat pto_isa.pin)"
```

加载现场 CANN 环境并激活项目 Python venv。在同一 Bash 会话执行以下命令。每次创建新的结果目录；任一步失败时保留日志，其他独立项仍可执行。

```bash
SWA=tests/fdwic/a6_dsv41_scheduler
mkdir -p "$SWA/build"
OUT=$(mktemp -d "$SWA/build/yellow-XXXXXX")
git rev-parse HEAD > "$OUT/simpler-version.txt"
git -C build/pto-isa rev-parse HEAD > "$OUT/pto-version.txt"
diff -u pto_isa.pin "$OUT/pto-version.txt"
git -C build/pto-isa status --porcelain
python "$SWA/test_fixture.py" -v > "$OUT/fixture.log" 2>&1
python "$SWA/prepare_plan.py" --output "$OUT/plan" > "$OUT/plan.log" 2>&1
python "$SWA/test_resources.py" -v > "$OUT/resources.log" 2>&1
python "$SWA/compile_kernels.py" --pto-isa build/pto-isa \
  --output "$OUT/kernels" > "$OUT/kernels.log" 2>&1
```

逐条记录退出码。PTO-ISA 应与 pin 一致且工作区干净。预期 plan 解码 2735 条原始记录，转换后 16 个计算任务、570 个子任务；资源测试验证 47 对时 t22 拒绝、48 对时通过；19 个核逐个完成编译、链接和机器码提取。返回 `plan/summary.json`、`kernels/summary.json`、两项测试结果。失败时附第一条报错、对应命令和出错阶段。若现场缺 CANN，先完成 fixture、plan 和资源测试。

### 步骤 2：采集一次启动的 worker 映射（Q1、Q4）

1. 查现场已运行过的 A6 C/V 联合启动样例或平台测试。记录代码版本、入口函数、实际构建和启动命令、申请的设备及 blockDim。先在本次分配中确认设备型号为 Ascend960DT_966B7。入口只有单核启动能力时，记录它能证明的字段，列出缺少的联合启动入口。
2. 按样例支持的资源参数，选能覆盖至少 48 对的配置启动一次，记录请求值和实际握手值。优先使用样例已有的启动日志。需要补打印时，在现场样例握手完成后一次性导出 worker 记录；保存临时 diff 和命令。源码参考 `scheduler_cluster_coordinate_from_worker()` 和 `percounter_post_handshake_init()`。前者按 worker 顺序计算逻辑坐标，后者检查上报的 C/V 数量。
3. 一行对应一个已握手 worker，整张表使用同一次启动的数据。列为 `run_id, worker_id, core_type, physical_core_id, block_idx, sub_block_id, cluster, lane, mapping_source`。硬件上报、驱动映射、软件计算分别标明来源；未提供的字段填“未暴露”。额外记录保留或屏蔽核以及正常退出标记。
4. 按 cluster 检查重复 worker、重复 lane、缺 C 或缺 V。分别给出已握手 C/V 数、逻辑完整组数、由平台映射规则或同组通信验证支持的配对数。若只有软件计算坐标，填写“物理配对待证”，保留原表。若样例最多申请少量核，按本次覆盖数量反馈，另记样例上限。
5. 得到实际可用对数后，按[资源预检命令](usage.zh-CN.md#swa-逻辑资源预检)构建 check-resources，plan 路径使用本轮 `$OUT/plan/plan-a6-rank0.bin`，将示例参数 54 换成本轮已证实的对数，保存 stdout、stderr 和退出码。少于 48 对时先反馈资源限制以及 t22 的诊断，保留原始 sync_start。

### 步骤 3：核对启动、数据布局和可见性

按第 4 节命令查询适用型号与 SDK 版本，填写 Q1–Q7 表。Q2/Q3 记录受支持的寄存器映射接口、SSBUF 所有者、核间共享范围、可用偏移与屏障；采用现场 SDK 或已验证样例给出的区间。Q6 用现场 Host、AICPU、AICore 三套编译目标分别检查 `host/image/image_pack.h` 与 `runtime/task_image_layout.h` 中的布局断言，记录各目标、类型、sizeof、alignof、关键 offsetof、kernel 槽数以及编译结果。缺少某个编译入口时标出该端。

Q7 对照 `runtime/scheduler/gm.h` 记录一个具体的发布与观察顺序：哪端写参数、更新哪一个计数、另一端经什么原子或屏障观察计数后读取数据。区分 SDK 文档规定与设备执行结果。Q5 单列计数器来源、单位和频率；Cube 主频单独保留。

### 步骤 4：percounter 功能验收

使用已交付的 **A6 percounter** 构建和运行入口；本目录现有 `run.py` 提供的是 A5 入口。若现场尚无 A6 入口，反馈缺少的平台库、启动接口或 runner，步骤 1–3 的结果可先交付。

1. 构建对应版本的 runtime、runner、replay adapter 和 A6 核，记录工具版本、实际命令与加载的库。用最小 1C1V MIX 用例跑一个 block，记录两个参与者的 worker/lane、发布和完成计数、输出校验与退出状态。
2. 最小用例通过且本次资源满足 t22 后，用冻结输入执行一轮 SWA。依据 plan 逐任务核对 task ID、block 和参与 lane；预期 16 个计算任务、570 个子任务。重点核对 t22 的 48 个同步 MIX block，以及 t9/t25/t35 的 80/64/64 个普通 Vector block。执行集合证据缺失的项单独标记。
3. 用 fixture 的参考输出和既有校验范围逐项比较，保留比较器结果、首个不匹配的 tensor 和位置，以及正常退出记录。若启动超时，使用现场样例或作业系统的超时与回收机制，保留最后一次握手、最后完成的 task/block/lane 和设备退出状态。

### 首轮反馈模板

原始日志留在黄区。将以下摘要交给用户，附可分享的关键输出片段、仓库相对路径和行号。每个结果注明“设备实测／离线测试／源码依据／待验证”。

```text
轮次、设备型号、Simpler 与 PTO-ISA 版本、实际使用的 CANN：
已执行步骤、命令与退出码：
离线：fixture / plan / 资源预检 / kernel 编译分别结果：
启动：样例版本、入口、请求资源、握手 C/V 数、完整组数、配对证据：
本次可证实的可用对数；是否满足 t22 的 48 对要求：
Q1–Q7：已确认项与来源；部分确认或缺少的接口：
设备：单 MIX / SWA 执行集合 / 输出校验 / 退出状态分别结果：
首个失败位置、关键原文、已查范围、下一步需要的具体接口：
黄区保留材料：worker 明细表、summary、构建与运行日志的相对路径：
```
