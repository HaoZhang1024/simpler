# A6 单卡 SWA · percounter

目标是缩小 DSV4.1 SWA 在 A6 和 A5 上的时延差距。现有单卡 L0 基线中，A6 AICore wall 为 265.768 µs，A5 为 185.173 µs，相差 80.595 µs。[基线与测量条件](doc/a6-a5-comparison.zh-CN.md)

## 黄区从这里开始

| 顺序 | 执行什么 | 完成后填哪里 |
| --- | --- | --- |
| **1 · 当前** | 按[黄区执行交接单](doc/a6-handoff.zh-CN.md)收齐正在跑的 CntNotify 实验数据 | 内网《A6 percounter SWA 性能分析与每日进展》→ [CntNotify 并发时延](doc/a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延) |
| **2 · CntNotify 确认后** | 按[同一张交接单的 SWA 命令](doc/a6-handoff.zh-CN.md#cntnotify-结果确认后执行-swa)跑固定版本，每卡 1 轮预热、10 轮正式回放 | 同一内网页面 → [SWA 单卡 L0 复测](doc/a6-swa-performance-progress.zh-CN.md#swa-单卡-l0-复测) |

[性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md)是黄区内网页面的转存原文。黄区登记实际作业和原始文件位置，蓝区补齐统计、结论和下一步。

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
