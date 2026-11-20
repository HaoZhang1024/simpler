# A6 单卡 SWA · percounter

**当前阶段：分析 A6 与 A5 的时延差距。** A6 本次 AICore wall 均值 267.511 µs，比 A5 多 82.338 µs；Device 均值 360.831 µs，比 A5 多 64.133 µs。整图测量和 CntNotify 微基准均已完成。

**[唯一进度与反馈入口：A6 SWA 性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md#当前状态与反馈位置)**。当前由蓝区用已有 L4 分析 t35、t25 尾块复用和 t22 启动等待。黄区本轮没有待跑、待传项。后续任务在同一张表登记要填的内容。

| 查阅 | 资料 |
| --- | --- |
| 硬件、整图基线与原始证据 | [A6/A5 对比](doc/a6-a5-comparison.zh-CN.md) · [A6 现场原始报告](doc/a6-result.md) · [A5 实测](doc/a5-results-2026-11-17.zh-CN.md) |
| t22、t25、t35 的逐核时间线 | [两端 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [A6 事件与同核复用](doc/a6-l4-feedback.md) |
| 复现历史实验 | [SWA 构建与运行](doc/usage.zh-CN.md) · [任务图与执行原理](doc/execution.zh-CN.md) · [同址测试方法](doc/a6-register-benchmark.zh-CN.md) |
