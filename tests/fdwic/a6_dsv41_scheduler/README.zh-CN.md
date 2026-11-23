# A6 单卡 SWA · percounter

**A6 t25 八批量化拆分已完成，24 个正式轮全部通过。** 首块诊断差距 3.7250 µs，其中增加 72 个有效行带来的差距为 3.5195 µs。蓝区下一步优先拆完整量化中生成 FP8 输出的路径。[两端实测与判读](doc/a6-swa-performance-progress.zh-CN.md#a6-quant-split-feedback)

同为 64 块时，A6 首块量化比 A5 多 3.548 µs。日常运行沿用 54 块 replay，A6 同卡 L0 AICore 平均节省 4.870 µs。54 块的逐块采集已结束，补采三轮的末块均为双 head 块。[量化分段](doc/a6-swa-performance-progress.zh-CN.md#1a-t25-首块分段) · [54 块结果](doc/a6-swa-performance-progress.zh-CN.md#54-块按-block_idx-分组)

| 要找什么 | 位置 |
| --- | --- |
| A5/A6 的硬件条件和整图时延 | [对比表](doc/a6-a5-comparison.zh-CN.md) · [A5 实测](doc/a5-results-2026-11-17.zh-CN.md) · [A6 现场报告](doc/a6-result.md) |
| t22、t25、t35 慢在哪里 | [两端 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [A5 泳道与提取结果](results/2026-11-19-a5-percounter-l4/) · [A6 逐核事件与提取结果](results/2026-11-19-a6-percounter-l4/) |
| 用已有泳道复算 | [提取脚本](analysis/compare_l4.py) · [命令与输入格式](doc/swa-l4-comparison.zh-CN.md#用已有泳道复算) |
| 计算 A6 SWA 同步约束极限 | [黄区采集命令与回填格式](doc/swa-sync-bound.zh-CN.md) · [求解入口](analysis/swa_sync_bound.py) |
| 查 CntNotify 同址实验 | [测量方法](probes/README.zh-CN.md) · [正式实验代码](probes/a6_same_address/) |
| 构建和运行 SWA | [运行说明](doc/usage.zh-CN.md) · [任务图与执行原理](doc/execution.zh-CN.md) · [A6 环境](doc/a6-environment.zh-CN.md) |
