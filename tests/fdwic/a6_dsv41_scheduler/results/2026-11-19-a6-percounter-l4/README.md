# A6 L4 三任务对照反馈（t22/t25/t35，2026-11-19）

按 [L4 对照方法](../../doc/a6-swa-performance-progress.zh-CN.md#l4-endpoints) 要求，用蓝区 `compare_l4.py`（git 39271d675 版，未改动）在黄区已有 A6 L4 正式轮上执行。

## ① 运行条件

- 数据：`/npu/z00880344/swa-a6-swimlane-l4/percounter/rank0/run1`（2026-11-19 10:12 采集；run0 为预热，run1 为正式轮，trace 仅含正式轮 epoch=2）
- `chip_swimlane_level=4` ✓；总区间 570 ✓；输出校验 PASS（采录时 SWA e2e golden 通过）
- capture：108 流，committed 267737 / dropped 0 / truncated 0
- 时钟：1 GHz（metadata clock_freq_hz=1e9），108 核（54 AIC + 54 AIV）
- runtime：percounter 现场工作树（基线 b921a01b + SWA 入口 e8fad256d + port 补丁 = a6-port-tracked.patch md5 1295923e…；A6-VERIFY 诊断探针仅位于初始化/错误路径，对调度与 kernel 热路径无影响）
- trace：采集时已用同轮 deps 转换的 Worker View Perfetto JSON；同轮 `source-task-map.txt`（src 8..35 → replay 0..27）与 A5 归档同格式
- 预热差异保留：A5 单轮无预热 vs A6 run0 预热 + run1 正式
- 整图 kernel 窗口：A6 453.489 µs（A5 321.00，两端各自零点）

## ② 对照表回填

| 源任务 | A6 区间/活跃核；每核执行次数分布 | 最晚计算前驱；前驱结束→首 dispatch    | 首 dispatch→首 kernel；启动分散 | kernel 跨度；与 A5 跨度差    | 各 func 的 n/中位/最大；同核复用间隔                         |
| ------ | -------------------------------- | ------------------------------------- | ------------------------------- | ---------------------------- | ------------------------------------------------------------ |
| t22    | 96 / 96；{1×96}（全核单次）      | t18（另有无 kernel 前驱 t21）；38.986 | 1.074；15.572                   | 36.213；+14.290（A5 21.923） | C(func18) 48 / 20.854 / 30.971；V(func19) 48 / 22.911 / 24.521；无复用（null） |
| t25    | 64 / 54；{1×44, 2×10}            | t22（另有 t23/t24 无 kernel）；7.097  | 1.782；31.220                   | 42.285；+23.182（A5 19.103） | func20 64 / 11.031 / 11.352；复用间隔中位 13.916             |
| t35    | 64 / 54；{1×44, 2×10}            | t29（最晚计算前驱）；4.185                  | 1.685；24.013                   | 33.093；+20.249（A5 12.844） | func27 64 / 9.075 / 9.740；复用间隔中位 13.632；末 kernel end 453.489 = 整图窗口末端 |

A5 对照（蓝区文档值）：t22 27.813 / 1.193 / 21.923 / 10.625；t25 4.324 / 1.325 / 19.103 / 12.703；t35 3.276 / 1.292 / 12.844 / 6.721。

## ③ 最小证据（时间均为本轮零点相对值，µs）

**t22（前驱→放行链，worker 30 = t18 末块 AIC，worker 57 = t22 首 dispatch AIV）**：

- 最后计算前驱 kernel 结束：t18 末块 worker 30（func13）end **171.077**
- 完成发布：worker 30 `percounter_async_seal` 171.116（+0.436）→ `percounter_complete_mix` 172.509（+1.375）→ fanin 计数 `atomic_fetch_add_issue` **173.387**（kernel end 后 +2.31）
- 无 kernel 前驱 t21 的完成时刻：**未观测**（核内记录无该事件）
- 依赖满足（64 次到达 + t21 达阈值）单一事件：**未观测**；最接近观测点 = 首dispatch核 57 的成功 `percounter_entry` 206.726（+2.529）。此前该核经历 3 个轮询 step：177.380（+12.856）、190.549（+9.525）、200.402（+37.675，本步内放行）。这三个数是调度 step 的开始时间；每个 step 内还会做其他工作
- 首 dispatch：worker 57 `percounter_run_prepared` **210.056**（dispatch-time 210.063）→ 首 kernel start **211.137**（func19/V）
- 最早/最晚 C：core 0 @211.942 / core 36 @226.709；最早/最晚 V：core 57 @211.137 / core 73 @224.551
- 末 kernel end 247.350

**t25（最后结束核 worker 84，AIV，两次执行）**：

- exec#1：dispatch 260.488 / kstart 262.495 / kend 273.487，aicore_tasks seq=5
- 复用窗口 273.487→287.449（13.96）：`async_seal` 273.527 → `publish_completion` 274.922 + `atomic_fetch_add_issue` 274.940→ 下一 step 276.486：`percounter_claim` 277.093（+2.900，取票 seq 5→6）+ 票号原子操作 ×3 → `resolve` 282.225 → `prepare_subtask` 284.293 → `run_prepared` 286.977（claim 开始至 run_prepared 开始 9.884 µs）
- exec#2：dispatch 286.984 / kstart 287.449 / kend **298.514**（任务最后结束），seq=6
- 两执行间该核 0 个其他任务 kernel（无穿插）；复用核共 10 个（54→64 差额）

**t35（最后结束核 worker 69，AIV，两次执行）**：

- exec#1：dispatch 419.635 / kstart 421.131 / kend 430.208，seq=8
- 复用窗口 430.208→444.409（14.20）：`async_seal` 430.251 → `publish_completion` 431.514 + issue 431.530 → step 433.260：`claim` 433.874（+3.488，seq 8→9）→ `resolve` 439.356 → `prepare_subtask` 441.431 → `run_prepared` 443.961
- exec#2：dispatch 443.968 / kstart 444.409 / kend **453.489 = 整图 kernel 窗口末端**（t35 仍决定整图结束，与 A5 角色相同），seq=9
- 无穿插

## ④ 三个任务的结论

- **t22**：t18 末 kernel 结束到 t22 首 dispatch 为 38.986 µs，比 A5 多 11.173 µs。173.387 µs 是 t18 发出完成计数更新的时刻；到 t22 首 dispatch 的 36.676 µs 仍包含多项工作。t21 完成和 t22 自身的第 48 次到达均待定位。进入 kernel 后，C/V 执行时长中位数分别比 A5 多 8.051/10.215 µs。
- **t25**：首 dispatch 为 254.447 µs，首 kernel start 为 256.229 µs。10 个复用核的两块间隔中位数为 13.916 µs。最后结束的 worker 84 两块间隔为 13.962 µs，其中 claim 自身跨度为 2.900 µs。
- **t35**：10 个复用核的两块间隔中位数为 13.632 µs。最后结束的 worker 69 两块间隔为 14.201 µs，第二块结束于 453.489 µs，也是本轮整图最后一个 kernel 的结束时刻。

## ⑤ 后续分析

CntNotify 硬件同步六组对照已结项。整图 L0 已有两批摘要。蓝区使用已有[三任务汇总 JSON](task-comparison.json)研究 t22 的到达与放行、t35 和 t25 的尾块复用，再按需要准备下一次诊断入口。
