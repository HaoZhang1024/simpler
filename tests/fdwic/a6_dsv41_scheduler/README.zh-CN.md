# A6 单卡 SWA · percounter

目标是缩小 DSV4.1 SWA 在 A6 和 A5 上的时延差距。现有单卡 L0 基线中，A6 AICore wall 为 265.768 µs，A5 为 185.173 µs，相差 80.595 µs。[基线与测量条件](doc/a6-a5-comparison.zh-CN.md)

## 黄区从这里开始

| 顺序 | 执行什么 | 完成后填哪里 |
| --- | --- | --- |
| **1 · 当前** | 按[黄区执行交接单](doc/a6-handoff.zh-CN.md)收齐正在跑的 CntNotify 实验数据 | 内网《A6 percounter SWA 性能分析与每日进展》→ [CntNotify 并发时延](doc/a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延) |
| **2 · CntNotify 确认后** | 按[同一张交接单的 SWA 命令](doc/a6-handoff.zh-CN.md#cntnotify-结果确认后执行-swa)跑固定版本，每卡 1 轮预热、10 轮正式回放 | 同一内网页面 → [SWA 单卡 L0 复测](doc/a6-swa-performance-progress.zh-CN.md#swa-单卡-l0-复测) |

[性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md)是黄区内网页面的转存原文。黄区登记实际作业和原始文件位置，蓝区补齐统计、结论和下一步。
# A6 percounter 的 GM 与 CntNotify 并发测试

黄区先回答两个问题：同一批 AICore 同时访问一个 32-bit 字时，第一、居中、最后一个参与者各在什么时候完成？SWA 的 t22 有 48 个同步 block，若这批访问发生在它的到达计数上，最后一个参与者是否推迟了 kernel 启动？先在已跑通 SWA 的工作树做独立探针，取得数据后再决定是否改 runtime。

| 顺序 | 黄区执行                                                     | 交付                                                |
| ---- | ------------------------------------------------------------ | --------------------------------------------------- |
| 1    | 在分配到的 A6 上确认时钟、参与核和 CntNotify 的 SET/read 能力 | 设备查询、映射与读回记录、空操作记录                |
| 2    | 固定 48C+48V，同址读和写各测三条路径，每轮每核一次           | 原始 CSV、按完成名次的统计表和读写两张图            |
| 3    | 对照 t22 的到达与放行，再看 t25/t35 是否出现同类等待         | 同轮 L4 事件；有可替换路径时再反馈单项改动的 L0 A/B |

## 1. 先确认测的是哪条指令

用现场通过的 MIX 1C1V 启动入口，增加独立的 probe kernel 和 Host 结果缓冲区。由黄区接入 A6 的 SDK、计时器和同步接口。蓝区交付的是采样约定和可直接运行的统计脚本。目标、实际设备号、CANN/编译器、优化选项、启动 block 数、每个参与者的 die/core type/worker、设备时钟来源和频率写入同一份运行记录。

- **GM。** 分配一个自然对齐、独占 cache line 的 32-bit 字。结果区、同步标志和测试字分别分配。确认 AIC 和 AIV 二进制中的访存宽度、返回值依赖和 DSB 指令。保存相应反汇编片段。
- **CntNotify。** 参照传瑜的 Host 实现，在当前设备 context 调用 `aclrtCntNotifyCreate`、`aclrtCntNotifyGetId`、`rtGetDevResAddress`。A5 使用 STARS CNT_NOTIFY_RECORD / CP1；按 A6 SDK 核对资源类型、访问主体、32-bit SET/read 映射和同步语义。资源保持到最后一次读回，再释放映射和 handle。先由 C 写入本轮标记、V 读回，再交换 C/V 角色，并验证下一轮复位。反馈申请数、有效映射数、实走硬件路径的次数或 SDK 返回码。若只取得 GM 路径，先交 GM 两组。INC 另需 A6 SDK 或平台实现确认别名与累加语义；A5 的 SET+8 属于 A5 实现。[SET/read 参考实现](https://github.com/hw-native-sys/simpler/pull/3145) · [资源复用与 INC 验证](https://github.com/hw-native-sys/simpler/pull/3152)
- **计时。** 使用覆盖两种核、两颗 die 的同源单调计数器，记录实测或平台给出的 tick Hz 与跨核对时依据。先跑相同起跑协议的空操作，记录读钟开销和每轮最早至最晚开始的分散度。若只有每核独立时钟，可以先交各核 `end_tick-start_tick`；跨核完成名次须等到时钟对齐后再算。

## 2. 固定并发，按每轮完成名次统计

截图参考配置是 32C+64V，共 96 核。A6 有 54 对 1C1V，第一组取 **48C+48V**，并记录两颗 die 的实际核数。这样能对齐总并发度，也能覆盖 t22 的参与规模；两台设备的 C/V 比例仍有差异。补测 **54C+54V** 可观察 A6 满配。若跨 die 对尾部影响明显，再固定相同参与数，例如同 die 的 24 对与两颗 die 各 12 对，保持其余条件一致。

| 路径               | 读一轮                               | 写一轮                                                       | 检查点                                                       |
| ------------------ | ------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| GM ld/st           | 32-bit `ld_dev` 读同址标记           | 32-bit `st_dev` 同值同址，每核一次 DSB                       | 各读者值正确；写轮结束读回本轮标记                           |
| GM atomic          | returning atomic add(0)，消费返回值  | 选定一个 32-bit 原子操作，例如 returning add(1)，每核一次 DSB | add(1) 从零起跑，最终值 N，返回旧值覆盖 0…N−1；记录具体 opcode 和返回值消费 |
| CntNotify SET/read | 32-bit `ld_dev` 读同一 SET/read 映射 | `st_dev` 写同一 SET 映射、同一标记，每核一次 DSB             | 确认命中映射；读值、轮末状态与本轮标记一致                   |

截图只标了 GM atomic 路径，未给出其写指令。拿到原 probe 时对齐 opcode、返回值使用和 fence；采用上表 add(1) 时单列该语义。SET 同值写只能检验最终状态，每个核是否参与由独立记录与核数核对。另测 non-returning add(1) 的发出窗口，再测 add(1)+DSB，并在轮末检查总数；分别记为 issue 和 fenced。生产计数为 64-bit 的位置另做同宽 GM 对照。[分支的 GM 原语](../../../../src/a5/runtime/percounter/runtime/scheduler/gm.h)

```text
Host 准备地址、轮次标记和每核独立记录槽
  → 各核驻留，确认本轮初值、所有上一轮访问已完成
  → 全体同步起跑（截图用硬件 SyncAll；A6 记录实际指令、参与域）
  → 各核读 t0 → 对同一地址执行一次操作 → 各核读 t1
      读：确保读值已返回且被消费，再取 t1
      写：同口径组把 DSB 放在 t1 前；issue 组单独标记
  → 窗口外将 t0、t1、读值或返回值写到本核独立槽
  → 全体会合，校验本轮结果，再复位并进入下一轮
```

每个组合先预热（记录次数），再保留 **192 个完整正式轮次**。同址访问前准备好地址和写值。跨 die 起跑需要覆盖所有实际驻留核；若平台仅支持 die 内屏障，先按单 die 出表，另列跨 die 的起跑实现及实测分散。为每轮保存开始分散、每核自身操作时长以及最晚完成者的 die/核型。时间戳放在寄存器中，结果写回移到窗口外。DSB 结束定义写方的计时终点；验证异核实际观察时间时另设读者记录首次看到新标记的时间。

**统计口径。** 对第 r 轮取 `t0_min = min(start_tick)`。本轮所有参与者按 `end_tick` 递增，第 k 个点为 `(end_tick[k] - t0_min) / tick_hz` 秒。跨 192 轮对相同 k 求 mean、P10、P90，分位数按线性插值。横轴为固定并发下的完成名次。平均相邻完成间隔为 `(mean[N] - mean[1]) / (N - 1)`；单核操作时长另由本核 t1−t0 计算。

每个设备、拓扑、操作、地址布局、返回值与 fence 组合各写一份 CSV，仅纳入已校验的正式轮次。表头为 `round,die,core_type,worker,start_tick,end_tick`，核型取 `AIC` 或 `AIV`，worker 填实际核号。可以追加返回值、预期值、轮末读回等列。失败或超时的原始批次单独留存并报告。以下脚本检查轮数、每轮核数、重复记录和参与者集合，从仓库根目录执行。

```bash
SWA=tests/fdwic/a6_dsv41_scheduler
python "$SWA/register_ranks.py" "$RAW" --workers 96 --rounds 192 \
  --tick-hz "${TICK_HZ:?device timer frequency}" > ranks.csv
```

绘图时每个读写面板各叠三条 `mean_us` 曲线，以 `p10_us` 至 `p90_us` 填充阴影，单位 µs。报告名次 1、N/2、N 及平均相邻完成间隔。下表是截图 **96 核**的读图校对值，前三列单位 µs，末列 ns；可用来核对单位与计算口径。

| 操作     | 路径      | 第 1  | 第 48 | 第 96  | 相邻均值 |
| -------- | --------- | ----- | ----- | ------ | -------- |
| 读       | GM ld/st  | 0.082 | 0.803 | 1.530  | 15.2     |
| 读       | GM atomic | 0.234 | 8.305 | 16.946 | 175.9    |
| 读       | CntNotify | 0.143 | 0.627 | 1.203  | 11.2     |
| 写 + DSB | GM ld/st  | 0.075 | 4.579 | 9.231  | 96.4     |
| 写 + DSB | GM atomic | 0.237 | 8.310 | 16.956 | 176.0    |
| 写 + DSB | CntNotify | 0.218 | 0.747 | 1.463  | 13.1     |

**A6 实测（完成项，2026-11-20）**：与上表同口径的 A6 秩表（16 预热 + 192 正式轮，`register_ranks.py --tick-hz 1000000000`）。96 核 = 48 AIC + 48 AIV（t48），108 核 = 54 AIC + 54 AIV（t54）；前三列单位 µs，末列 ns（=（第 N − 第 1）/（N−1））。CntNotify INC 一路使用经验别名 **set_va+0x20**（A6 SDK 拒绝 ADD 资源映射：`rtGetDevResAddress(resType=6)` → rc 507899 全参数组合均拒，`rtGetCntNotifyAddress(NOTIFY_CNT_ADD_SLICE)` → rc 107000 不支持；op99 扫描：N 写 1 → SET 视图精确读 N（208/208 轮），SET 写 0 复位，+0x4..+0x3c 其余偏移读 0xDEADDEAD 无效果，A5 的 +8 在 A6 无效）——**该偏移待平台侧确认后即为 CntNotify ADD 资源正式口径**。

A6 · 96 核（48C+48V）：

| 操作           | 路径                         | 第 1  | 第 48 | 第 96 | 相邻均值 |
| -------------- | ---------------------------- | ----- | ----- | ----- | -------- |
| 读             | GM ld/st（op01）             | 0.715 | 2.992 | 3.614 | 30.5     |
| 读             | GM atomic（op04）            | 0.251 | 1.061 | 1.358 | 11.7     |
| 读             | CntNotify SET（op13）        | 0.247 | 1.463 | 2.240 | 21.0     |
| 写 + DSB       | GM ld/st（op02）             | 0.197 | 2.533 | 5.079 | 51.4     |
| 写 + DSB       | GM atomic（op07）            | 0.157 | 1.731 | 5.130 | 52.3     |
| 写 + DSB       | CntNotify SET（op14）        | 0.298 | 1.146 | 4.591 | 45.2     |
| 写 + DSB       | CntNotify INC（op17，+0x20） | 0.277 | 0.811 | 1.360 | 11.4     |
| 写（无 fence） | GM ld/st（op03）             | 0.015 | 0.409 | 0.679 | 7.0      |
| 写（无 fence） | GM atomic issue（op06）      | 0.018 | 0.410 | 0.681 | 7.0      |
| 写（无 fence） | CntNotify INC（op16，+0x20） | 0.004 | 0.292 | 0.521 | 5.4      |

A6 · 108 核（54C+54V）：

| 操作           | 路径                         | 第 1  | 第 54 | 第 108 | 相邻均值 |
| -------------- | ---------------------------- | ----- | ----- | ------ | -------- |
| 读             | GM ld/st（op01）             | 0.595 | 3.724 | 4.366  | 35.2     |
| 读             | GM atomic（op04）            | 0.251 | 1.161 | 1.539  | 12.0     |
| 读             | CntNotify SET（op13）        | 0.244 | 1.599 | 2.492  | 21.0     |
| 写 + DSB       | GM ld/st（op02）             | 0.196 | 2.716 | 5.822  | 52.6     |
| 写 + DSB       | GM atomic（op07）            | 0.157 | 2.161 | 6.021  | 54.8     |
| 写 + DSB       | CntNotify SET（op14）        | 0.299 | 1.333 | 5.464  | 48.3     |
| 写 + DSB       | CntNotify INC（op17，+0x20） | 0.277 | 0.880 | 1.500  | 11.4     |
| 写（无 fence） | GM ld/st（op03）             | 0.015 | 0.437 | 0.741  | 6.8      |
| 写（无 fence） | GM atomic issue（op06）      | 0.018 | 0.439 | 0.743  | 6.8      |
| 写（无 fence） | CntNotify INC（op16，+0x20） | 0.004 | 0.293 | 0.548  | 5.1      |

读图要点：**CntNotify INC 是全部路径中最快的同址多写者操作**——无 fence 尾延迟 0.521/0.548 µs（96/108 核），比最快 GM 路径（op04 returning atomic 读 1.358/1.539、op05 returning 加 0.984/1.071）快约 1.9-2.8×；INC+DSB 尾延迟 1.360/1.500 µs，比 GM atomic+DSB（5.130/6.021）与 GM store+DSB（5.079/5.822）快约 3.7-4.0×。相邻间隔：无 fence INC 5.1-5.4 ns（GM 同类 6.8-7.0），INC+DSB 11.4 ns（GM atomic+DSB 52.3-54.8、store+DSB 51.4-52.6）。

口径备注：① op00-15 为 2026-11-19 21:48 会话（原编排），op16/17 为 2026-11-20 00:48 会话（MIX-SPMD 编排）；crosscheck（op00/op13 t48 新编排）与 21:48 原版分布一致——op00 0.002/0.279/0.513 vs 0.014/0.404/0.674，op13 0.417/1.306/2.105 vs 0.247/1.463/2.240。② op16 issue-window 满计数 192/192（t4/t48/t54 全部轮次轮末读回 == N）；op17 严格校验 aux==N 192/192 全过（96/108 写者硬件累加零丢失）。③ 读 GM ld/st（op01，ld_dev 旁路读）首名 0.715 µs 显著高于 A5 的 0.082，为 A6 实测原值，供核对口径。④ 原始 CSV/ranks.csv/run record 在仓库 `tests/st/a5/host_build_graph/register_bench/results/a6/`（op16/17 × t4/t48/t54 + crosscheck/）。⑤ **与 002 用例（同目录 `probes/same_address`，48C+48V 同规模、硬件 SYNCALL 对齐、计时窗口零背景流量）的干净基线对照**：002 第 96 名——GM ld 读 0.503、GM atomic 读 0.990、CntNotify SET 读 1.225、GM st+DSB 1.786、GM atomic 写（atomicExch）0.993、SET 写+DSB 1.328 µs。本表 GM/SET 各行测于 GM 软件栅障环境（arrive 计数 + dcci 轮询），含 +0.4~3.3 µs 环境增量（noop 尾部 0.513 µs 即起跑离散下界），**非孤立硬件成本**；交叉验证：本表 op05（atomicAdd(1) 取返回、无 DSB）0.984 ≈ 002 GM atomic 读 0.990，op17（INC+DSB，寄存器路径不经 GM）1.360 ≈ 002 SET+DSB 1.328——无轮询污染时两边收敛，两组数据互补不矛盾。002 的 GM atomic 写为 atomicExch(1)，生产 HBG 完成计数指令为 atomicAdd(1) 取返回（本表 op07 5.130 µs），引用时注意区分；002 未覆盖 INC/ADD 路径（其文档标注 ADD 补测 deferred）。⑥ **+0x20 的 A5 先例**：A5 侧 ADD 直接映射同样被驱动拒（rc 507899，2026-11-17 调查记录 `docs/investigations/2026-11-a5-hbg-cnt-notify-add-deferred.md`），A5 生产 HBG 经授权使用 SET 映射 32 字节槽 **+0x08** 的 INC 别名（命令语义：写 1 加 1，写 2/3 亦只加 1）——A6 的 +0x20 与其同族（同槽不同偏移），并非孤立经验值；A6 未验证写 2 是否只加 1，建议平台组确认 +0x20 偏移时一并明确该命令语义。


## 3. 用 SWA 判断值不值得改

黄区 §7.10 已补采同级 L4。t22 的 AIC kernel 均值从 A5 的 13.46 增到 A6 的 22.27 µs，AIV 从 13.00 增到 23.02 µs；另报 t22 前的阶段间隙增加约 11.1 µs。先将后者的起止事件与任务表中的“最晚可见计算前驱结束 → 首 dispatch”对齐。寄存器方案首先解释启动前的等待；kernel 内的增量应逐 func 核对开始/结束事件、实际入参和 kernel 工作量。此次 A5 L4 有 32C+64V 实际执行，A6 为 54C+54V。两端整图 kernel 跨度为 321.00 和 453.49 µs，L0 的改善量取配对实测。[黄区新增的 L4 结果 §7.10](a6-result.md)

**优先看 t22 的 48 次到达。** 当前 `lane_loop.h` 中，MIX 各 lane 经 SSBUF 发布 `enter_ready`，`percounter_tokens_ready` 检查同组。组内指定 lane 调 `percounter_gm_fetch_add_issue(sync_arrivals[sync_index].next, 1)` 标记本 block 到达；参与者再用 `percounter_gm_read` 观察计数等于 block 数。48 对核有 **48 次逻辑加一**，轮询次数取实测。单独做“48 个指定写者累加 + 各参与者等阈值”的小实验，用通过验证的 INC/read 与原 GM 对照，保持 SSBUF 会合与数据可见性屏障一致。重复 SET(1) 无法表示 48 次到达。[当前调度代码](../../../../src/a5/runtime/percounter/aicore/lane_loop.h) · [陈鹏的 percounter 同步路径实验](https://github.com/hw-native-sys/simpler/pull/3180)

- **L4 定位。** 先复用已有正式轮，沿 t22 给出最后前驱结束、最后 block 到达、首次观察到阈值、首 dispatch、首 kernel start、末 kernel end。每一对端点标注对应 lane；缺少内部事件就写“未观测”。需要补点时单独跑诊断轮。t25/t35 均有 64 个普通 Vector block，分别给出最后结束核的复用顺序和前后 block 间隙，再看 `percounter_claim_block` 取票是否出现在这一段。A6 头尾另按 `aicpu_ready` 发布→核观察及 `exit_request` 发布→核退出测量，两者均有自己的发布者、地址分布和观测端点。[三项任务的 A5 实测与 A6 提取命令](swa-l4-comparison.zh-CN.md)
- **判定候选是否命中。** 记录硬件映射数、实际选中 INC 的 cohort、GM 回退数、最后到达与首 dispatch 的差值。读写寄存器可能缩短会合；需要返回唯一旧票号的 claim 仍须保证唯一分配。陈鹏的静态分配针对同步宽度恰好等于 owner 数，t22 的 48 与 A6 的 54 对并不相等。传瑜的 HBG 验证逐项检查硬件映射和实际执行，并把 Host bind 单独计时，两种方法都可复用。[percounter 实验](https://github.com/hw-native-sys/simpler/pull/3180) · [HBG 映射及 trace 验证](https://github.com/hw-native-sys/simpler/pull/3157)
- **L0 验收益。** 有可用候选时，A 为当前 GM，B 仅更改已定位的一条路径。同一张卡、同一 plan/输入/工具链和 570 个执行实例，关诊断，先做 A/A，再按 A-B-B-A 交替。每批 1 次预热 + 10 个正式样本，每批独立输出目录。反馈各批 AICore wall、Device、输出校验和 B−A 配对差，结合 A/A 波动判断；涉及资源申请时另报首次/复用 bind。陈鹏 #3180 的 A5 SWA 为 165.847→166.647 µs（+0.48%，组合改动），这是另一组基线。硬件完成名次曲线和 L4 区间只能定位要验证的路径。[SWA 运行入口](usage.zh-CN.md#黄区接续测试) · [配对和 A/A 方法](https://github.com/hw-native-sys/simpler/pull/3151)

首批反馈可直接按以下顺序填写：① 设备、核表、时钟、屏障范围与空操作开始分散；② SET/read、INC 的能力和读回，实际 opcode；③ 每个组合的 192 轮原始 CSV、ranks.csv、图和首/中/尾表；④ t22 两个最晚事件的 worker、时间戳，及与 A5 同口径的差值；⑤ 是否进入单路径 L0 A/B，给出触发依据或缺少的观测。随附黄区实际 probe 源码或 diff、构建/启动命令和二进制版本，方便下一轮复跑。
## 按问题查资料

| 想了解什么 | 去哪里看 |
| --- | --- |
| 两端设备、时延和原始测量分别是什么？ | [A6 / A5 对比表](doc/a6-a5-comparison.zh-CN.md) · [A6 现场原始报告](doc/a6-result.md) · [A5 实测记录](doc/a5-results-2026-11-17.zh-CN.md)。A6 报告引用的历史补丁见[当时的目录](https://github.com/HaoZhang1024/simpler/tree/b36fdcca5/tests/fdwic/a6_dsv41_scheduler/doc) |
| GM 与 CntNotify 的时延怎样测？ | [参与核、读写指令、计时和排名方法](doc/a6-register-benchmark.zh-CN.md) |
| 哪几段 SWA 慢，泳道上看到了什么？ | [t22、t25、t35 的对照方法](doc/swa-l4-comparison.zh-CN.md) · [A6 同轮事件与数据](doc/a6-l4-feedback.md) |
| SWA 怎么组包、更换 runtime 后要重编什么？ | [执行原理](doc/execution.zh-CN.md) · [构建与复测用法](doc/usage.zh-CN.md) |

## 代码与数据

| 位置 | 用途 |
| ---- | ---- |
| [prepare.py](prepare.py) | 解包输入，编译 SWA 核与原生工具，组装运行包 |
| [compile_kernels.py](compile_kernels.py) | 独立检查 A6 的 19 个核：编译、链接、提取机器码；不启动设备 |
| [prepare_plan.py](prepare_plan.py)、[adapt_plan.cpp](adapt_plan.cpp) | 校验原 plan 的 Host 解码结果，只转换两处 MIX 任务描述 |
| [check_resources.cpp](check_resources.cpp)、[test_resources.py](test_resources.py) | 按给定 C/V 逻辑拓扑检查实际 SWA plan 的任务资源需求；纯 CPU 预检与集成测试 |
| [run.py](run.py) | 申请单卡，运行 HBG／percounter，校验并统计 |
| [test_fixture.py](test_fixture.py) | 离线检查输入包与参考覆盖 |
| [fixtures/](fixtures/) | 固定输入、plan、参考与来源清单 |
| [results/2026-11-17-a5/](results/2026-11-17-a5/) | A5 逐轮数据、日志和校验和清单 |
| [A5 percounter L4 泳道](results/2026-11-19-a5-percounter-l4/README.md) | 完整 Perfetto trace、逐核预览、578 个 kernel 区间及黄区任务编号对照 |
| [results/2026-11-17-a6-offline/](results/2026-11-17-a6-offline/) | A6 编译前后、A5 机器码不变、plan 转换的离线证据；不含设备结果 |

文档集中在 `doc/`；构建产物写入 `build/`，新的测试输出由 `--output` 指定。
