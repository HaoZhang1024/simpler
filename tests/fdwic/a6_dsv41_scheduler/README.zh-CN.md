# A6 单卡 SWA · percounter

**当前阶段：分析 A6 与 A5 的时延差距。** A6 本次 AICore wall 均值 267.511 µs，比 A5 多 82.338 µs；Device 均值 360.831 µs，比 A5 多 64.133 µs。整图测量和 CntNotify 微基准均已完成。

**[唯一进度与反馈入口：A6 SWA 性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md#当前状态与反馈位置)**。本轮只测 t25 的 64 / 54 block 对照。蓝区已核对工作量、生成两份 plan，并提供黄区直接执行的脚本。命令和回填行都在进展表。

| 要找什么 | 位置 |
| --- | --- |
| A5/A6 的硬件条件和整图时延 | [对比表](doc/a6-a5-comparison.zh-CN.md) · [A5 实测](doc/a5-results-2026-11-17.zh-CN.md) · [A6 现场报告](doc/a6-result.md) |
| t22、t25、t35 慢在哪里 | [两端 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [A5 泳道与提取结果](results/2026-11-19-a5-percounter-l4/) · [A6 逐核事件与提取结果](results/2026-11-19-a6-percounter-l4/) |
| 用已有泳道复算 | [提取脚本](analysis/compare_l4.py) · [命令与输入格式](doc/swa-l4-comparison.zh-CN.md#用已有泳道复算) |
| 查 CntNotify 同址实验 | [测量方法](probes/README.zh-CN.md) · [正式实验代码](probes/a6_same_address/) |
| 构建和运行 SWA | [运行说明](doc/usage.zh-CN.md) · [任务图与执行原理](doc/execution.zh-CN.md) · [A6 环境](doc/a6-environment.zh-CN.md) |
