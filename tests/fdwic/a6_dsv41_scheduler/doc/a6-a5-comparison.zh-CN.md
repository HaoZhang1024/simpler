# A6 与 A5 单卡 percounter SWA 差异

SWA 当前采用 A6 的 t25 54 块方案。按同卡配对实验，A6 Device 均值 355.528 µs，对照 A5 已有基线 296.698 µs，还差 **58.830 µs（19.8%）**。当前核内调查集中在 t25 生成 FP8 输出的路径。[逐批数据、执行命令和回填](a6-swa-performance-progress.zh-CN.md)

## 环境与硬件

| 项目 | A6 | A5 |
| --- | --- | --- |
| 设备 / Host | Ascend960DT_966B7，x86_64，Ubuntu 20.04.6 | Ascend950DT_9581，aarch64 |
| CANN / 编译器 | CANN 9.3.0，ccec / LLD 15.0.5，AICPU 交叉 g++ 14.3.0 | 安装标签 9.3.0，compiler 组件 9.2.0，ccec clang 15.0.5 |
| AICore 编译目标 / PTO-ISA | dav-920r1-cube / vec，83b1b2b5 | dav-c310-cube / vec，83b1b2b5 |
| 每个逻辑 block 的槽位 | 1 AIC + 1 AIV | 1 AIC + 2 AIV |
| 平台配置上限 / 本例 L4 实际执行 | 54 组，54C+54V / 54C+54V | 36 组，36C+72V / 32C+64V |
| 每组 SSBUF 容量 / runtime 预留 | 2 KiB / 256 B | 3 KiB / 1024 B |
| 计时基准 | L4 SYS_CNT 1 GHz；query 的 Cube 工作时钟为 1800 MHz | L4 计时器 1 GHz |

A6 现场 query 还报告 8 个 AICPU、L1 512 KiB、L0A/L0B 各 64 KiB、L0C 256 KiB、每 AIV 的 UB 376 KiB 和 L2 128 MiB。驱动为 7.12.T0.0.B280，ascendhal 为 7.35.23。[A6 查询原文](../results/2026-11-17-a6-environment/device-query.txt) · [A5 环境和逐轮统计](../results/2026-11-17-a5/summary.json)

拓扑直接改变本例的工作分配。t22 在 A5 提交 24 个 1C2V block，A6 拆成 48 个 1C1V block，各处理一半 head 并各自 gather 完整 KV。t28 在两端都提交 32 块，A6 的一个 V 分两次处理原先两个 V 的列。原始 t25 发 64 块时，A5 的 64 个 AIV 各接一块，A6 有 10 个 AIV 需要再接一块。改发 54 块后，同样的 64 个 head 由 44 个单 head 块和 10 个双 head 块覆盖。[plan 转换](../prepare_plan.py) · [逐块身份和尾块](a6-swa-performance-progress.zh-CN.md#54-块按-block_idx-分组)

## 寄存器、GM 与同步

| 通路 | A5 | A6 的实测和 runtime 选择 |
| --- | --- | --- |
| DATA_MAIN_BASE，0xD0 | percounter 通过寄存器传启动和退出信号 | AICPU 写后可从 MMIO 回读，AIC 侧 SPR 未观察到同值。启动及退出分别走 GM 的 `aicpu_ready`、`exit_request` |
| COND，0x5108 | A5 上有寄存器交互路径，具体角色取决于 runtime | 现场探针中 AIC set_cond 与 AICPU MMIO 未互通；GM-only 探针跳过该偏移 |
| CntNotify SET / INC | 同址 SET 读写已测，INC 别名为 SET+0x08 | 同址 SET 读写和 INC 已测，现场 INC 别名为 SET+0x20 |
| IPC，0x5500 / 0x5520 | HBG 通路 | 本例 percounter 未使用，现场记录未验证 |

同址并发测试每轮固定 96 核（A5 32C+64V，A6 48C+48V），硬件 SYNCALL 对齐起跑，预热 1 轮、正式 192 轮。下表是每轮相对最早起跑的**第 96 个完成时刻均值**，单位 µs。A6 的 GM 原子完成计数可继续作为基线；t22 在生产图上何时观察到阈值，仍需由实际调度事件定位。

| 单次 32-bit 同址访问 | A6 | A5 |
| --- | ---: | ---: |
| GM 普通读 / 写后 DSB | 0.495 / 1.665 | 1.660 / 8.931 |
| GM 原子加零取返回 / exchange 后 DSB | 1.043 / 1.046 | 16.387 / 16.385 |
| CntNotify SET 读 / 写后 DSB | 1.225 / 1.331 | 1.199 / 1.447 |

A6 同批扩展项中，GM 加一取返回后 DSB 为 1.051 µs，CntNotify INC 后 DSB 为 1.336 µs。[正式探针](../probes/a6_same_address/) · [A5 对照数值来源](../probes/a6_same_address/summarize.py) · [黄区 96 / 108 核原始回填](https://github.com/HaoZhang1024/simpler/blob/2d4396a56/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#L98-L138)

## 整图时延与当前定位点

| L0 均值（µs） | A5 基线 | A6 64 块 | A6 54 块 | A6 同卡节省 | 54 块距 A5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Device | 296.698 | 360.507 | 355.528 | 4.979 | +58.830 |
| AICore wall | 185.173 | 267.075 | 262.205 | 4.870 | +77.032 |

A6 是同卡 64→54→54→64 四批（每批预热 1 轮、正式 10 轮）；A5 是独立的 10 轮基线。AICore wall 取首个核开始到末核结束，Device 还包含设备侧启动与收尾。较早的 64 块单批 A6 记录为 AICore 267.511、Device 360.831 µs。[四批实测](a6-swa-performance-progress.zh-CN.md#t25-的-64--54-block-对照) · [A5 原始样本](../results/2026-11-17-a5/samples.csv)

| 定位点 | 已量到的差异 | 仍要解释的时间 |
| --- | --- | --- |
| t25 / func20 | 原 64 块，单 head 首块量化 A6 7.808、A5 4.260 µs，差 3.548 µs。另一次诊断窗口差 3.7250 µs，其中随 72 个有效行增加的差为 3.5195 µs | 从准备 scale 到 FP8 输出，正在比归一化、限幅、转换、打包和 UB 写入；蓝区已有 A5 的 16 批基线 |
| t22 / func18、19 | 首次 L4 对照中，t18 完成到 t22 首 dispatch 多 11.173 µs，t22 核执行跨度多 14.290 µs | 分开看 1C1V 的 gather 工作量与依赖放行、同步会合 |
| t35 / func27 | 同轮 L4 的启动分散多 17.292 µs，核执行跨度多 20.249 µs；A6 仍有 10 个块复用 worker | 区分单块计算与第二波接块、最后完成块的等待 |
| 其他前驱 | 首核到 t22 首核的 L4 区间多 42.651 µs；t25 末核到 t35 首核多 28.890 µs | 两段都含其他任务的计算，按可见前驱和核占用继续拆 |

L4 各取一轮，A5 无预热、A6 取预热后的正式轮。这些窗口可以重叠；整图收益以同卡 L0 对照为准。[L4 明细与复算](a6-swa-performance-progress.zh-CN.md#l4-endpoints) · [t25 本轮详细交接](a6-swa-performance-progress.zh-CN.md#a6-fp8-output)

历史移植记录保留平台注册、MIX mask 折叠、寄存器映射、现场错误码和测试覆盖。A5 独立用例记录保留准备过程、构建证据和旧 PR 基线。[黄区移植原报告](https://github.com/HaoZhang1024/simpler/blob/37b531376ec4434833d28c8c05a51f1b7adbe796/tests/fdwic/a6_dsv41_scheduler/doc/a6-result.md) · [A5 独立用例原报告](https://github.com/HaoZhang1024/simpler/blob/37b531376ec4434833d28c8c05a51f1b7adbe796/tests/fdwic/a6_dsv41_scheduler/doc/a5-results-2026-11-17.zh-CN.md)
