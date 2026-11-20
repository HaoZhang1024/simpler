# A6 单卡 SWA · percounter

**当前阶段：分析 A6 与 A5 的时延差距。** A6 本次 AICore wall 均值 267.511 µs，比 A5 多 82.338 µs；Device 均值 360.831 µs，比 A5 多 64.133 µs。整图测量和 CntNotify 微基准均已完成。

**[唯一进度与反馈入口：A6 SWA 性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md#当前状态与反馈位置)**。t25 的 54 块方案在 A6 同卡 L0 上平均节省 4.870 µs AICore 时间。A/B 各三轮 L4 已归档，以 t22 结束为起点，到整图最后一个 kernel 仍提前 9.730 µs。[t25 结果复核](doc/a6-swa-performance-progress.zh-CN.md#t25-结果复核)

| 要找什么 | 位置 |
| --- | --- |
| A5/A6 的硬件条件和整图时延 | [对比表](doc/a6-a5-comparison.zh-CN.md) · [A5 实测](doc/a5-results-2026-11-17.zh-CN.md) · [A6 现场报告](doc/a6-result.md) |
| t22、t25、t35 慢在哪里 | [两端 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [A5 泳道与提取结果](results/2026-11-19-a5-percounter-l4/) · [A6 逐核事件与提取结果](results/2026-11-19-a6-percounter-l4/) |
| 用已有泳道复算 | [提取脚本](analysis/compare_l4.py) · [命令与输入格式](doc/swa-l4-comparison.zh-CN.md#用已有泳道复算) |
| 查 CntNotify 同址实验 | [测量方法](probes/README.zh-CN.md) · [正式实验代码](probes/a6_same_address/) |
| 构建和运行 SWA | [运行说明](doc/usage.zh-CN.md) · [任务图与执行原理](doc/execution.zh-CN.md) · [A6 环境](doc/a6-environment.zh-CN.md) |
