# A6 单卡 SWA · percounter

**当前阶段是定位 A6 单块执行与同核调度的差距。** t25 调整为 54 块后，A6 同卡 L0 AICore 平均节省 4.870 µs；实验方案相对历史 A5 基线，AICore 仍多 77.032 µs、Device 多 58.830 µs。[t25 结果复核](doc/a6-swa-performance-progress.zh-CN.md#t25-结果复核)

**黄区三轮 L4 已回填。** t25 在 A6 每核执行第一块时就比 A5 多约 4.5 µs。t35 还有一次同核接块，前块结束到下一块开始的中位数为 12.7–13.0 µs。下一步蓝区先拆 t25 的 kernel 时间，再用 t35 验证取票和参数准备的开销。黄区本轮采集已完成。[六行原始结果和复核](doc/a6-swa-performance-progress.zh-CN.md#两端首块与同核接块)

| 要找什么 | 位置 |
| --- | --- |
| A5/A6 的硬件条件和整图时延 | [对比表](doc/a6-a5-comparison.zh-CN.md) · [A5 实测](doc/a5-results-2026-11-17.zh-CN.md) · [A6 现场报告](doc/a6-result.md) |
| t22、t25、t35 慢在哪里 | [两端 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [A5 泳道与提取结果](results/2026-11-19-a5-percounter-l4/) · [A6 逐核事件与提取结果](results/2026-11-19-a6-percounter-l4/) |
| 用已有泳道复算 | [提取脚本](analysis/compare_l4.py) · [命令与输入格式](doc/swa-l4-comparison.zh-CN.md#用已有泳道复算) |
| 查 CntNotify 同址实验 | [测量方法](probes/README.zh-CN.md) · [正式实验代码](probes/a6_same_address/) |
| 构建和运行 SWA | [运行说明](doc/usage.zh-CN.md) · [任务图与执行原理](doc/execution.zh-CN.md) · [A6 环境](doc/a6-environment.zh-CN.md) |
