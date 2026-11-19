# A6 / A5 单卡 percounter SWA 对比

| 项目 | A6 | A5 |
| ---- | -- | -- |
| 设备 / Host | Ascend960DT_966B7 / x86_64 | Ascend950DT_9581 / aarch64 |
| 每组计算核 | 1 AIC + 1 AIV | 1 AIC + 2 AIV |
| 平台配置上限 | 54 组，54 AIC + 54 AIV | 36 组，36 AIC + 72 AIV |
| 本轮 L4 实际执行的核 | 54 AIC + 54 AIV | 32 AIC + 64 AIV |
| 每组 SSBUF / 运行时预留 | 2 KiB / 256 B | 3 KiB / 1024 B |
| 启动与退出信号 | GM 上的 aicpu_ready / exit_request | DATA_MAIN_BASE（0xD0） |
| profiling 计时器 | 1 GHz（L4 metadata） | 1 GHz（平台配置） |
| AICore 编译目标 | dav-920r1-cube / vec | dav-c310-cube / vec |
| CANN / ccec | 9.3.0 / clang 15.0.5 | 安装标签 9.3.0，compiler 组件 9.2.0 / clang 15.0.5 |
| PTO-ISA | 83b1b2b5 | 83b1b2b5 |
| 计算任务 / 执行实例 | 16 / 570 | 16 / 578 |

| 时延（µs） | A6 | A5 | A6 − A5 |
| ---------- | -- | -- | ------- |
| L0 AICore wall 均值 | 265.768 | 185.173 | +80.595 |
| L0 Device 均值 | 357.712 | 296.698 | +61.014 |
| L4 整图 kernel 跨度 | 453.489 | 320.997 | +132.492 |
| L4 t22 kernel 跨度 | 36.213 | 21.923 | +14.290 |
| L4 t25 kernel 跨度 | 42.285 | 19.103 | +23.182 |
| L4 t35 kernel 跨度 | 33.093 | 12.844 | +20.249 |

L0 各预热 1 轮、正式 10 轮。A6 使用黄区移植版本，A5 runtime 为 26b0511f3。L4 各取 1 个正式轮次；跨度从首个 kernel 开始算到最后一个 kernel 结束。[A6 现场记录](a6-result.md) · [A5 实测记录](a5-results-2026-11-17.zh-CN.md) · [A6 L4 数据](a6-l4-task-comparison.json) · [A5 L4 数据](../results/2026-11-19-a5-percounter-l4/task-comparison.json)
