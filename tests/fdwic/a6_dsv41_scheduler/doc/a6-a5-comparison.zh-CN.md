# A6 与 A5 单卡 percounter SWA 性能对比

## 集成版整图与调度下限

同一 SWA 切口、参考输出校验通过。A5 在设备 4（Ascend950DT_9582，32C+64V）运行 t25=64，A6 在设备 0（Ascend960DT_966B7，54C+54V）运行 t25=54。两端均使用 CANN 9.3.0 和 PTO-ISA `45435c062`，每种采样级别各 1 轮预热、10 轮正式。A5 每轮 578 次 kernel 执行，A6 每轮 560 次。[A5 集成版采集配置与十轮明细](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-a5-comparison.zh-CN.md#集成版-a5-swa-对照基线) · [A6 集成版原始回填](a6-swa-performance-progress.zh-CN.md#integrated)

| 十轮均值（µs） | A5 | A6 | A6 − A5 |
| --- | ---: | ---: | ---: |
| AICore L0 实测 | 164.483 | 239.870 | +75.387 |
| Device L0 实测（含启动和收尾） | 227.184 | 305.495 | +78.311 |
| 固定 worker 和核上顺序的模型 | 120.710 | 198.730 | +78.020 |
| 自由分核模型最优值 | 120.260 | 197.150 | +76.890 |

A6 在固定 worker 和核上顺序的情况下，实测与模型相差 **41.140 µs**，占 AICore L0 的 17.2%。A5 相差 43.773 µs，占 26.6%。这个差值还包含 L0 头尾、L2 采样和模型假设的影响。A6 从固定分核改为自由分核，模型均值减少 1.580 µs。

| 十轮均值（µs） | A5 · 32C+64V | A6 · 54C+54V | A6 − A5 |
| --- | ---: | ---: | ---: |
| L2 首个 kernel 开始至末个返回 | 169.528 | 246.625 | +77.097 |
| 实际关键链上 kernel 窗口之和 | 114.749 | 195.559 | +80.810 |
| 实际关键链上 kernel 间隔之和 | 54.779 | 51.067 | −3.713 |

前三行来自同一 L2 窗口，逐轮沿最新可见前驱或同 worker 上一块回溯。两端可以走不同的链，kernel 窗口包含该调用内部的计算、访存和等待。自由分核模型另行求解。A6 的整图差距优先沿关键链上的 kernel 和分块查。

| 时间 | 怎么得到 | 用它判断什么 |
| --- | --- | --- |
| 当前实测 | A6 原版 percounter，L0 预热 1 轮、正式 10 轮。主指标是 AICore wall 均值，另报中位数、最快一轮和 Device 均值 | 当前方案已经达到的整图性能 |
| 固定每块落核与核上顺序的理想时间 | 每轮 L2 保留 560 条 kernel 的时长、实际 worker 与执行顺序、DAG 前驱、MIX 同块起跑和 `sync_start`。把取任务、通知和派发的耗时设为零，重排开始时间 | 沿用本轮排块决策，执行窗口理论上能压到多短。实际错峰与模型的严格同步规则形成环时，该轮标记为空并统计有效轮数 |
| 自由排块的理想时间 | 同一轮时长和依赖，允许求解器重新安排 block，限制 AIC/AIV 各 54 个。报求解下界、可行解和最优状态 | 固定排块与自由排块之间还有多少空间。求解区间收敛以后再给单一最优值 |

两种模型均按 0.1 µs 向下量化单个 kernel 时长。自由排块模型按核类型计容量，MIX 配对的物理 cluster、访存争用随排布改变的影响均未单独建模。以上极限适用于这张 SWA 图和这批时长。AICore L0 从最早的业务 kernel 调用前计到最晚一次返回后的写屏障完成，Device L0 另含设备启动和收尾。L2 模型使用独立十轮采集的 kernel 调用至返回时长。

<details>
<summary>A5 集成版设备 4 的逐轮模型值（µs）</summary>

| 正式轮 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 固定排块 | 126.0 | 125.9 | 123.9 | 121.9 | 119.0 | 118.4 | 118.3 | 120.2 | 116.1 | 117.4 |
| 自由排块，10/10 最优 | 125.7 | 124.6 | 123.6 | 121.6 | 118.4 | 118.2 | 118.0 | 120.0 | 116.0 | 116.5 |

</details>

<a id="l1-comparison"></a>

## L1 实测：关键链核内时间

两端使用原集成版，各预热 1 轮、正式采集 10 轮。A5 每轮 578 次调用，A6 每轮 560 次，数值与每个任务的 AIC/AIV 调用数校验均通过。L1 将单次调用从 kernel 开始前计到返回后的写屏障完成，包含计算、访存和核内等待。[采集命令、版本与 A6 回填 JSON](a6-swa-performance-progress.zh-CN.md#swa-l1)

| 十轮均值 | A5 | A6 | A6 − A5 |
| --- | ---: | ---: | ---: |
| 首次调用至末次结束（µs） | 166.056 | 239.376 | +73.320 |
| 实际关键链上 kernel 窗口之和（µs） | 113.697 | 197.008 | **+83.311** |
| 关键链上窗口之间的时间（首尾跨度减去上一行，µs） | 52.359 | 42.368 | −9.991 |
| 至少一个核在 kernel 窗口内（µs） | 144.335 | 222.442 | +78.107 |
| 所有核都在 kernel 窗口外（µs） | 21.721 | 16.934 | −4.787 |
| 全部 AIC 的 kernel 时间累加（核·µs） | 1912.357 | 3584.519 | +1672.162 |
| 全部 AIV 的 kernel 时间累加（核·µs） | 3336.011 | 4359.864 | +1023.853 |

A6 的关键链上，kernel 窗口多用 83.311 µs，窗口之间少用 9.991 µs，合计多用 73.320 µs。两端分别沿各自实际执行的链回溯。全核空档按所有核的窗口取并集后计算；关键链在等待时，其他核仍可能执行任务。[L1 统计方法](../analysis/swa_l1.py)

AIC 与 AIV 累计时间分别增长 87.4% 和 30.7%，包含多个核同时工作的时间。定位整图差距优先看各任务在关键链上占用的时间。已有 L2 中，t28 和 t29 两段输出投影的链上窗口分别多用 13.014 和 11.187 µs。t25 单独走 AIV，它的 `VPACKV2` 属于向量量化路径。[逐任务 L2 对照](#task-gains) · [t25 计划中的核类型](../analysis/swa_sync_bound.py#L89-L94)

## 环境与硬件

下表保留移植期 query 和 L4 使用的环境。集成版 A5 性能在 9582 上采集，两端集成版均用 PTO-ISA `45435c062`；表中 9581 和 `83b1b2b5` 对应早期测量。

| 项目 | A6 | A5 |
| --- | --- | --- |
| 设备 / Host | Ascend960DT_966B7，x86_64，Ubuntu 20.04.6 | Ascend950DT_9581，aarch64 |
| CANN / 编译器 | CANN 9.3.0，ccec / LLD 15.0.5，AICPU 交叉 g++ 14.3.0 | 安装标签 9.3.0，compiler 组件 9.2.0，ccec clang 15.0.5 |
| AICore 编译目标 / PTO-ISA | dav-920r1-cube / vec，83b1b2b5 | dav-c310-cube / vec，83b1b2b5 |
| 每个逻辑 block 的槽位 | 1 AIC + 1 AIV | 1 AIC + 2 AIV |
| 平台配置上限 / 本例 L4 实际执行 | 54 组，54C+54V / 54C+54V | 36 组，36C+72V / 32C+64V |
| 每组 SSBUF 容量 / runtime 预留 | 2 KiB / 256 B | 3 KiB / 1024 B |
| 计时基准 | L4 SYS_CNT 1 GHz；query 的 Cube 工作时钟为 1800 MHz | L4 计时器 1 GHz |

A6 现场 query 还报告 8 个 AICPU、L1 512 KiB、L0A/L0B 各 64 KiB、L0C 256 KiB、每 AIV 的 UB 376 KiB 和 L2 128 MiB。驱动为 7.12.T0.0.B280，ascendhal 为 7.35.23。[A6 查询原文](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/results/2026-11-17-a6-environment/device-query.txt) · [A5 环境和逐轮统计](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/results/2026-11-17-a5/summary.json)

拓扑直接改变本例的工作分配。t22 在 A5 提交 24 个 1C2V block，A6 拆成 48 个 1C1V block，各处理一半 head 并各自 gather 完整 KV。t28 在两端都提交 32 块，A6 的一个 V 分两次处理原先两个 V 的列。原始 t25 发 64 块时，A5 的 64 个 AIV 各接一块，A6 有 10 个 AIV 需要再接一块。改发 54 块后，同样的 64 个 head 由 44 个单 head 块和 10 个双 head 块覆盖。[plan 转换](../prepare_plan.py) · [逐块身份和尾块](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#54-块按-block_idx-分组)

### Host 如何找到同一物理核的寄存器窗口

| 地址表（按物理核号索引） | A5 | A6 |
| --- | --- | --- |
| 每个 HAL 资源窗 | 3 MiB：C 在窗首，V0 在 +1 MiB，V1 在 +2 MiB | 2 MiB：C 在窗首，V 在 +1 MiB |
| 每 die 的核号排列 | 18 个 C，随后 18 对 V；两 die 共 36 个资源、108 项 | 35 个 C，随后 35 个 V。die0 为 C 0–34、V 35–69，die1 为 C 70–104、V 105–139；共 70 个资源、140 项 |
| 本例实际使用 | 32C + 64V | 54C + 54V；硬件编号为屏蔽核保留位置 |

A6 由上报的物理核号取资源和子窗口。例如 V 核 68 位于 die0、资源 33，CP1 在该资源窗首加 1 MiB 后，再加 IPC 偏移。A6 的参考实现与 HBG 实卡握手为该布局提供了依据。两端也向 PMU 接口传递这张基址表，本节的实卡结果覆盖启动与退出。[A5 地址表](../../../../src/a5/platform/onboard/host/host_regs.cpp) · [A6 地址表](../../../../src/a6/platform/onboard/host/host_regs.cpp) · [A6 参考映射与设备验证](https://github.com/mihudaner/simpler/blob/392fae8b8efa15dc65cff15e6ce1f764ecd60d9a/tests/fdwic/a6_dsv41_scheduler/doc/a6-migration.zh-CN.md#L165-L184)

## 寄存器、GM 与同步

| 控制方向或操作 | A5 | A6 实卡验证的通路 |
| --- | --- | --- |
| AICPU → AICore，放行或发送 EXIT | AICPU 写目标子核窗口 `+0xD0`，核读 `DATA_MAIN_BASE` | HBG 的 AICPU（CP1）以 64 位写目标子核窗口 `+0x5500`，核用 `get_ipc_reg_0()` 读 IPC0 |
| AICore → AICPU，回送本轮退出确认值 | 核写 `COND`，AICPU 从该子核窗口 `+0x5108` 读回 | HBG 的核用 `set_ipc_reg_4(value)` 写 IPC4，CP1 从同一子核窗口 `+0x5520` 以 64 位读回 |
| CntNotify SET / INC | 同址 SET 读写已测，INC 别名为 SET+0x08 | 同址 SET 读写和 INC 已测，现场 INC 别名为 SET+0x20 |

| 哪次测试 | 已确认的结果 | 测量范围 |
| --- | --- | --- |
| 黄区早期 percounter，A6 沿用 A5 的两组地址与核侧指令 | AICPU 写 `+0xD0` 后能自行回读 `0x7ffffffd`，AIC 读 `DATA_MAIN_BASE` 未看到同值，启动等待超时。反向的 `set_cond()` 与 `+0x5108` 也未打通 | 旧组合的跨端连通性。[现场报告](https://github.com/HaoZhang1024/simpler/blob/cf78bd31a/tests/fdwic/a6_dsv41_scheduler/doc/a6-result.md#L30-L37) |
| A6 HBG SWA 迁移基线（`a6-migrate-case`），IPC0 / IPC4 | 核端写旧 COND 时，CP1 在 `+0x5520` 收不到回执。改写 IPC4 后，54C + 54V 全部完成启动与退出，30 个可写缓冲区通过校验 | 实卡已验证命令和回执双向连通，单次 IPC 往返时延未单独测量。[实卡记录与产物指令](https://github.com/mihudaner/simpler/blob/392fae8b8efa15dc65cff15e6ce1f764ecd60d9a/tests/fdwic/a6_dsv41_scheduler/doc/a6-migration.zh-CN.md#L182-L194) |
| CntNotify SET / INC 与 GM 同址访问 | A6 的 INC 别名经 SET 读回终值校验；96 核和 108 核的逐名次时延见下表 | 多核对同一计数地址的并发访问 |
| 本分支 percounter，A6 IPC0 / IPC4 | 蓝区已在 A6 核侧产物核对读 IPC0、写 IPC4，CP1 产物核对 64 位加载和存储，CPU 用例核对两个窗口偏移和高低 32 位 | A6 percounter 实卡功能、连续运行与 L0 GM/IPC 整图对照由黄区回填。[命令与结果位置](a6-swa-performance-progress.zh-CN.md#ipc-lifecycle) |

**当前 percounter 协议。** AICPU 在 GM 发布本轮 READY 和拓扑后，通过 IPC0 放行或发 EXIT。核结束后，从 GM 取本轮退出确认值并写 IPC4。AICPU 核对回执、关闭窗口并回读，再在 GM 允许核返回。C 核与 V 核在 t22 内仍用 SSBUF 传递 `fanin_ready`。本页已有的 A6 AICore **239.870 µs** 和 Device **305.495 µs** 来自迁移初期的 GM 启动与退出检查版本。[核侧寄存器访问](../../../../src/a5/platform/onboard/aicore/inner_kernel.h) · [AICPU 确认与放行](../../../../src/a6/platform/shared/aicpu/platform_regs.cpp)

### CntNotify 与 GM 同址测试

每轮所有参与核用硬件 `SYNCALL<Mix>` 对齐起跑，每核向同一个 32 位地址访问一次。预热 1 轮后测 192 轮。每轮以最早开始时刻为零点，按结束时刻排名，再对同一名次取 192 轮均值。平均相邻间隔按每轮（末名时刻 − 首名时刻）除以（核数 − 1）计算。写后有 DSB 的组计到屏障返回；无 fence 的组计到指令发出。

**A5 · 96 核（32 AIC + 64 AIV），11 月 19 日复测。** 总表的 A5 基线取自这批可复算的记录。[逐名次原始数据](https://github.com/mihudaner/simpler/blob/0d76a7d55bcf8976a25777a5dc2ce9b5cbed2eeb/tests/fdwic/a6_dsv41_scheduler/results/002-hbg-same-address-access/a5-ranks.json)

| 操作 | 路径 | 第 1 名（µs） | 第 48 名（µs） | 第 96 名（µs） | 第 96 名 P10–P90（µs） | 平均相邻间隔（ns） |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 读 | GM 普通读 | 0.073 | 0.866 | 1.660 | 1.625–1.703 | 16.7 |
| 读 | GM 原子加零，取返回值 | 0.207 | 8.236 | 16.387 | 16.277–16.581 | 170.3 |
| 读 | CntNotify SET 读 | 0.133 | 0.616 | 1.199 | 1.181–1.218 | 11.2 |
| 写 + DSB | GM 普通写 | 0.064 | 4.516 | 8.931 | 8.852–8.987 | 93.3 |
| 写 + DSB | GM 原子交换 | 0.208 | 8.238 | 16.385 | 16.278–16.531 | 170.3 |
| 写 + DSB | CntNotify SET 写 | 0.207 | 0.735 | 1.447 | 1.431–1.464 | 13.1 |

<details>
<summary>A5 原图的六组读数（96 核，另一批测量）</summary>

| 操作 | 路径 | 第 1 名（µs） | 第 48 名（µs） | 第 96 名（µs） | 平均相邻间隔（ns） |
| --- | --- | ---: | ---: | ---: | ---: |
| 读 | GM ld/st | 0.082 | 0.803 | 1.530 | 15.2 |
| 读 | GM atomic | 0.234 | 8.305 | 16.946 | 175.9 |
| 读 | CntNotify | 0.143 | 0.627 | 1.203 | 11.2 |
| 写 + DSB | GM ld/st | 0.075 | 4.579 | 9.231 | 96.4 |
| 写 + DSB | GM atomic | 0.237 | 8.310 | 16.956 | 176.0 |
| 写 + DSB | CntNotify | 0.218 | 0.747 | 1.463 | 13.1 |

</details>

**A6 · 96 核（48 AIC + 48 AIV），11 月 20 日复测。** 这组与 A5 的并发总数相同，两端的 C/V 比例见表题。

| 操作 | 路径 | 第 1 名（µs） | 第 48 名（µs） | 第 96 名（µs） | 平均相邻间隔（ns） |
| --- | --- | ---: | ---: | ---: | ---: |
| 读 | GM ld/st | 0.111 | 0.181 | 0.495 | 4.0 |
| 读 | GM atomic（add 0 取返回） | 0.241 | 0.768 | 1.043 | 8.4 |
| 读 | CntNotify SET | 0.160 | 0.696 | 1.225 | 11.2 |
| 写 + DSB | GM ld/st | 0.107 | 0.986 | 1.665 | 16.4 |
| 写 + DSB | GM atomic（exch） | 0.251 | 0.771 | 1.046 | 8.4 |
| 写 + DSB | GM atomic（faa，生产指令） | 0.251 | 0.773 | 1.051 | 8.4 |
| 写 + DSB | CntNotify SET | 0.223 | 0.779 | 1.331 | 11.7 |
| 写 + DSB | CntNotify INC（+0x20） | 0.223 | 0.771 | 1.336 | 11.7 |
| 写（无 fence） | GM ld/st / GM atomic issue / CntNotify INC | 0.002 | 0.021 | 0.048 | 0.5 |

**A6 · 108 核（54 AIC + 54 AIV），同批全核对照。** 中间名次取第 54 名，最后一个完成的是第 108 名。

| 操作 | 路径 | 第 1 名（µs） | 第 54 名（µs） | 第 108 名（µs） | 平均相邻间隔（ns） |
| --- | --- | ---: | ---: | ---: | ---: |
| 读 | GM ld/st | 0.113 | 0.210 | 0.525 | 3.9 |
| 读 | GM atomic（add 0 取返回） | 0.263 | 0.843 | 1.148 | 8.3 |
| 读 | CntNotify SET | 0.164 | 0.757 | 1.361 | 11.2 |
| 写 + DSB | GM ld/st | 0.115 | 1.424 | 2.350 | 20.9 |
| 写 + DSB | GM atomic（exch） | 0.269 | 0.849 | 1.153 | 8.3 |
| 写 + DSB | GM atomic（faa，生产指令） | 0.269 | 0.847 | 1.152 | 8.3 |
| 写 + DSB | CntNotify SET | 0.232 | 0.848 | 1.477 | 11.6 |
| 写 + DSB | CntNotify INC（+0x20） | 0.232 | 0.845 | 1.474 | 11.6 |
| 写（无 fence） | GM ld/st / GM atomic issue / CntNotify INC | 0.002 | 0.024 | 0.051 | 0.5 |

A6 无 fence 的三条路径在回填精度下读数相同，合列一行。CntNotify INC 在每轮同步后从 SET 读回的终值均等于参与核数；GM 原子加一取返回值（faa）的票号也逐轮覆盖 0 到核数减一。[黄区两组完整回填与校验](https://github.com/HaoZhang1024/simpler/blob/2d4396a56/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#L98-L138)

同为 96 核，GM 原子加零读的末名从 A5 的 **16.387 µs** 降到 A6 的 **1.043 µs**，CntNotify SET 读分别为 **1.199 / 1.225 µs**。在 A6 的完成计数对照中，GM 原子加一后 DSB 为 **1.051 µs**，CntNotify INC 后 DSB 为 **1.336 µs**。这组结果支持 SWA 继续使用 GM 完成计数；t22 等待第 48 个 block 到达的时间另看生产泳道。[t22 的 L4 端点](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#l4-endpoints)

### SWA 实际用了哪条计数通路

A5 Host 按同步组优先的顺序申请 CntNotify。有效 SET 地址按 32 字节对齐，ADD 别名为 SET + 0x08；槽位不足的项使用 GM。原集成版 L0 和 V0 实验的原版 L2 都记录了 `planned_chains=4 mapped_chains=4 eligible_tasks=16 mapped_tasks=16 mapped_sync=2 sync_cohorts=2`。L2 的 1 轮预热与 10 轮正式记录一致：这批 SWA 的两个同步组（含 t22）都取得了硬件计数器。[A5 分配与部分回退](../../../../src/a5/platform/onboard/host/scheduler_done_notifications.cpp) · [Host 映射计数的生成](../../../../src/a5/runtime/percounter/host/state.h)

A6 实卡探针已用 SET + 0x20 自增并从 SET 读回正确终值。本分支 A6 的 `scheduler_notification_increment_address()` 仍返回 0，Host 据此把 `completion_notify_address` 和 `sync_notify` 留为 0。任务完成走 GM 计数，跨 block 的同步起跑走分区 GM 到齐计数。若以后接入硬件计数，Host 的资源申请、映射和设备端由 SET 推导 ADD 的偏移都要配套；当前 IPC 改动只覆盖启动和退出。[A6 平台选择](../../../../src/a6/platform/include/host/scheduler_notification_address.h) · [Host 生成计数表](../../../../src/a5/runtime/percounter/host/region_plan.h) · [设备端 ADD 别名](../../../../src/a5/runtime/percounter/runtime/scheduler/wire_types.h) · [黄区源码比对原文](https://github.com/HaoZhang1024/simpler/blob/32885a2c1/tests/fdwic/a6_dsv41_scheduler/doc/a6-a5-comparison.zh-CN.md#背景与动机)

<a id="task-gains"></a>

## 任务对整图下限的影响

**逐个任务缩短 10%。** 每次只缩短该 task 的全部 block 和 lane，按原始周期乘 0.9 后再向下量化至 100 ns，保留其余任务、依赖、MIX、同步与容量，重新求整图最优值。每端十轮 × 16 个任务共 160 个对照，上下界全部收敛。表中“下限减少”是十轮模型收益均值，各项独立计算。实际关键链列使用原始执行数据，按 task 累加后取十轮均值，未上链的轮次按 0 计。

| 任务 | A5 下限减少（µs） | A6 下限减少（µs） | A5 链上 kernel（µs） | A6 链上 kernel（µs） |
| --- | ---: | ---: | ---: | ---: |
| t29 · 输出投影 B | 2.09 | 3.20 | 20.933 | 32.120 |
| t28 · 输出投影 A | 1.83 | 3.10 | 17.622 | 30.636 |
| t22 · 稀疏 gather MIX | 1.49 | 2.44 | 14.666 | 23.575 |
| t18 | 1.36 | 2.13 | 13.213 | 20.945 |
| t8 | 1.10 | 1.15 | 9.230 | 10.357 |
| t17 | 0.99 | 1.57 | 8.424 | 15.523 |
| t12 | 0.86 | 1.14 | 8.152 | 11.320 |
| t35 | 0.78 | 1.74 | 6.917 | 17.433 |
| t25 · 输出量化 | 0.77 | 2.13 | 6.354 | 20.932 |
| t16 | 0.70 | 1.05 | 5.734 | 10.025 |
| t9 | 0.09 | 0.12 | 0.988 | 1.241 |
| t19 / t20 / t31 / t33 / t34 | 各 0.00 | 各 0.00 | 0.814 / 0.481 / 1.221 / 0 / 0 | 0 / 0 / 1.452 / 0 / 0 |

两端前三项都为 t29、t28、t22。A6 上单独缩短 t29 或 t28 的全部 block 时，模型下限分别减少 3.20 或 3.10 µs；t25 的收益由 A5 的 0.77 增至 A6 的 2.13 µs。[A6 十轮任务敏感性原始回填](a6-swa-performance-progress.zh-CN.md#offline-l2)

## t25 单 head 时延与 VPACKV2 的来源

集成版 L2 逐轮取单 head 块的中位数，再对十轮取均值，A5 为 6.817 µs，A6 为 10.691 µs，相差 **3.874 µs**。本组 A5、A6 均使用 PTO-ISA `45435c062`。A6 的双 head 块为 20.924 µs，十轮最后结束的块都落在双 head 的 0–9 号。下面的指令对照来自此前使用 `83b1b2b5` 的单 head 量化实验。[本轮 A6 逐块回填](a6-swa-performance-progress.zh-CN.md#offline-l2) · [A5 集成版配置](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-a5-comparison.zh-CN.md#集成版-a5-swa-对照基线)

A5 十轮的末块为 62 号（7 轮）或 60 号（3 轮）。A6 当前计划将其余 10–53 号块分给单 head；早期 L4 的三轮末块为 8、8、6，也都属于双 head。[旧版逐块记录](https://github.com/HaoZhang1024/simpler/blob/97e3f0d3a/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#54-块按-block_idx-分组)

| 证据 | A5 | A6 |
| --- | --- | --- |
| SWA 源码 | 每个 256 元素的 chunk 调一次 `vcgmax(..., MODE_ZEROING)`，随后右移 23 位取指数 | 同一调用、同一输入规模。[量化循环](../kernels/vendor/external/o_quant_vf.hpp#L43-L71) |
| 已核验的 `quant_vf<80>` 机器码 | `VCGMAX → VSHRI` | `VCGMAXV2 → VPACKV2 → VSHRI`。每个有效行有两个 chunk，72 行比 A5 多执行 144 次向量打包，位置在求 scale 的依赖链上。[逐条反汇编](https://github.com/HaoZhang1024/simpler/blob/97e3f0d3a/tests/fdwic/a6_dsv41_scheduler/results/2026-11-23-t25-quant/quant-vf-80.asm.txt) |

**已定位到 CCEC 的实现。** 蓝区 CANN 9.3.0 安装目录下，`tools/bisheng_compiler/lib/clang/15.0.5/include/__clang_cce_vector_intrinsics_legacy.h` 第 11073–11099 行的 `__VF_VCG_V920` 宏实例化了 FP32 的 `vcgmax`。宏先调用 `vcgmaxv2` 内建函数，把中间结果交给 `vpackv2`，再把打包结果返回给使用 `MODE_ZEROING` 的调用方。这个显式展开解释了 A6 反汇编中额外指令的来源。

**设计动机和时延归因。** 一个独立 A6 测试项目记录了 8 组最大值中有 7 组出错，并列出 `vcgmaxv2 + vpackv2` 的处理方式。这支持“打包用于整理分组归约结果，使调用方按预期位置读取最大值”的解释。该提交记录的是使用者的观察；CCEC 最初引入该规则的提交及作者说明仍待查证。当前 3.874 µs 衡量整个单 head 块，多出的 `VPACKV2` 在这段差距中占多少仍待同版本对照测量。[独立项目的实测记录与提交差异](https://github.com/ivanmang/a6-vmi-dashboard/commit/78dfca536ab995dd4921db48a0c4e65281bcda89)

## t22 派发前与同步放行

从关键 block 的最后一个可见阻塞 kernel 返回起，到关键 lane 发出 dispatch 为止，按同一时间窗截取各事件段。提前完成的 claim 可以与前驱执行重叠。单位为 µs，数字为十轮均值。

| 派发前间隔 | A5 | A6 |
| --- | ---: | ---: |
| 前驱返回后、owner 开始 claim 前 | 0.000 | 0.000 |
| 落在 owner claim 内 | 0.084 | 0.094 |
| claim 结束到观察到 inputs_ready | 1.459 | 1.426 |
| inputs_ready 到关键 lane 的 entry_commit | 0.692 | 1.661 |
| entry_commit 到该 lane 的 ready | 4.794 | 4.576 |
| ready 到 dispatch | 0.184 | 0.293 |
| 合计 | 7.213 | 8.050 |

<a id="t22-release"></a>

### 以全组最后一次提交为界

| 十轮均值（µs） | A5 · 24 块 1C2V | A6 · 48 块 1C1V | A6 − A5 |
| --- | ---: | ---: | ---: |
| 关键 lane 等待，全组最后一次 `entry_commit` 之前 | 2.821 | 2.001 | −0.820 |
| 同一等待，最后一次 `entry_commit` 之后 | 1.973 | 2.575 | +0.602 |
| **关键 lane 等待合计** | **4.794** | **4.576** | **−0.218** |
| 最后一次 `entry_commit` 到全组首个 `ready` | 1.356 | 1.725 | +0.369 |
| 最后一次 `entry_commit` 到全组末个 `ready` | 2.428 | 3.235 | +0.807 |
| 全组从首个到末个 `ready` 的跨度 | 1.072 | 1.510 | +0.438 |

- **谁最晚提交。** A6 的 V lane 占 7/10 轮，C lane 占 3/10 轮。47 号块出现 6 轮，39 号块 2 轮，43、45 号块各 1 轮。A5 十轮都是 C lane。两端最晚提交者在同一 worker 上执行的上一项 kernel 都是 t18。在 A6，这十轮从该 worker 的 t18 结束到对应 block 的 `inputs_ready` 平均 4.889 µs。这个间隔包含前驱和调度工作，凭这两个打点还无法归因给 t18。
- **放行过程。** A6 全组首个 `ready` 晚了 0.369 µs，从首个到末个 `ready` 又多花 0.438 µs。两者相加，末个 `ready` 晚了 0.807 µs。`entry_commit` 打点在写入 `enter_ready` 之前，之后还要检查组内到齐、上报 block、检查全组放行和读取本地通知。这些操作共同落在观测窗口里。[MIX 同步路径](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1625-L1682)

**计数路径从哪一步开始影响 t22。** 两端的 C 都在簇内 SSBUF 发布 `fanin_ready`，V0 从 SSBUF 读；每个参与核记录 `entry_commit` 后把自己的 `enter_ready` 写回 SSBUF。本 block 的参与核到齐后，C 才调用 `percounter_start_arrive()` 计入跨 block 的同步组，并用 `percounter_start_ready()` 检查全组。A5 本批用 CntNotify，A6 用 GM 分区计数。它们的直接差异落在**提交后的放行**：末次提交到末次 ready 的差为 +0.807 µs，关键 lane 整段等待的差为 −0.218 µs，二者取的起止点不同。提交前同角色 V0 的 +0.541 µs 仍只定位到 C 打点至 V0 提交的窗口，两端同一份源码也可能因核角色、block 数和当时的候选状态走不同分支。[簇内就绪与提交](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1653-L1675) · [跨 block 到齐与检查](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1426-L1466)

<a id="t22-entry-roles"></a>

### 同一关键 block 的 C、V0 提交

**同一 block 内发生了什么。** V0 领取 MIX block 并发布任务记录。C 是 t22 的最低参与 lane，检查输入依赖，在写入共享的 `fanin_ready` 之前记录 `inputs_ready`。各 lane 选中该任务、满足顺序条件并准备好函数地址后，各自记录 `entry_commit`，随后写自己的 `enter_ready`。V0 还负责发布 MIX 顺序的下界。两个打点之间既可能跨核，又跨过候选选择和顺序检查；这批原版记录没有单列 V0 首次读到 `fanin_ready` 的时刻。[领取与发布](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1012-L1052) · [C 检查依赖](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L958-L1006) · [各核选择与提交](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1504-L1629)

| t22 输入就绪 → 提交，十轮均值（µs） | A5 · 每轮 24 块 1C2V | A6 · 每轮 48 块 1C1V | A6 − A5 |
| --- | ---: | ---: | ---: |
| 实际关键 lane | 0.692（V1） | 1.661（V0） | +0.969 |
| 各自关键 block 的 V0 | 1.120 | 1.661 | **+0.541** |
| 各自关键 block 的 C | 0.801 | 0.879 | +0.078 |
| 所有 block 的 V0 | 1.348 | 1.469 | **+0.121** |
| 所有 block 的 C | 0.916 | 0.916 | 0.000 |

**蓝区复核。** A5 240 个、A6 480 个 block 均按实际 worker 核对。每轮从 C 记录同一个 `inputs_ready` 起算，关键 block 的 V0 和 C 提交时间之差，A5 为 0.319 µs，A6 为 0.782 µs，扩大了 **0.463 µs**。这个相减消去了共同的起点，表明关键 block 内两个核的提交时刻拉得更开。按全部 block 计算，V0 相对 C 的平均差距扩大了 0.121 µs。十轮结果给出了总体均值，逐块分布和轮间波动仍未知。

两端关键 block 的 V0 原始窗口与已记录的 kernel 执行重叠均值均为 0.000 µs。L2 记录了 C 发布标志前的打点和 V0 提交前的打点，中间包含 C 发布、V0 轮询、顺序检查和提交准备。相同的 `lane_loop.h` 会根据 lane 角色、任务状态和顺序条件走不同分支。这批数据把排查范围缩小到了 V0 提交路径，具体哪一步拉长仍待验证。[V0 读取就绪标志](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L827-L847) · [V0 维护顺序与检查提交条件](../../../../src/a5/runtime/percounter/aicore/lane_loop.h#L1504-L1629)

[按角色核验的原始回填](a6-swa-performance-progress.zh-CN.md#t22-entry-roles) · [同步等待的原始回填](a6-swa-performance-progress.zh-CN.md#t22-release)

A5 新的同卡 L2 对照在原有 V0 提交记录中保留了首次观察到输入就绪的时刻。诊断版 240 个 block 的原始窗口平均为 1.327 µs，其中首次观察前 0.930 µs、观察后到提交 0.397 µs。本次原版全量均值为 1.312 µs。两组的关键 lane 分布有变化，A6 对照使用同样的两组采样。[本批配置、关键角色与 A6 回填](a6-swa-performance-progress.zh-CN.md#t22-observe)

## A6 实验版与集成版

同卡同输入、t25=54。实验版 `a1ee04044` 使用早期 PTO-ISA pin，集成版 `76c7c288b` 使用 `45435c062` 并重建 callable。两批反映整套构建的变化。

| 十轮均值（µs） | 实验版 | 集成版 |
| --- | ---: | ---: |
| AICore L0 | 262.692 | 239.870 |
| Device L0 | 356.976 | 305.495 |
| 自由分核模型 | 202.210 | 197.150 |
| 固定分核模型 | 204.390 | 198.730 |
| L2 首核至末核 | 265.417 | 246.625 |
| 关键链间隔之和 | 65.936 | 51.067 |
| t22 / t9 / t35 的派发前间隔 | 11.933 / 9.053 / 7.323 | 8.050 / 7.517 / 6.707 |

早期 t25 的 64/54 块四批配对实验，以及 t22、t25、t35 的 L4 分段采用当时的工具链和基线。[旧版 L0 与 L4 对照](https://github.com/HaoZhang1024/simpler/blob/99a827f41/tests/fdwic/a6_dsv41_scheduler/doc/a6-a5-comparison.zh-CN.md#整图时延与当前定位点) · [实验版调度下限回填](https://github.com/HaoZhang1024/simpler/blob/520732d11/tests/fdwic/a6_dsv41_scheduler/doc/a6-swa-performance-progress.zh-CN.md#a6-sync-bound-feedback)
