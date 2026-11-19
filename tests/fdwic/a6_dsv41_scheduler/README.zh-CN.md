# SWA 独立用例

独立运行 DSV4.1 的 SWA 子层。蓝区维护 Simpler 平台、percounter 和测试代码；黄区在分配到的 A6 上构建、执行并反馈结果。

| 入口 | 用途 |
| ---- | ---- |
| [A6 / A5 对比](doc/a6-a5-comparison.zh-CN.md) | 硬件、工具链、SWA 实测时延 |
| [本轮黄区交接单](doc/usage.zh-CN.md#黄区接续测试) | 交付版本、已验证的代码、正在跑的 CntNotify 实验、SWA 单卡命令及回传文件 |
| [执行原理](doc/execution.zh-CN.md) | 19 个已有 kernel、任务图和固定输入；A6 的两处 MIX 变更 |
| [三任务 L4 对照](doc/swa-l4-comparison.zh-CN.md) · [黄区测试清单](doc/a6-l4-feedback.md) | t22 的计数等待、t25/t35 的核复用 |
| [GM 与 CntNotify 测量](doc/a6-register-benchmark.zh-CN.md) | 当前实验的计时和结果格式 |
| [A6 现场原始报告](doc/a6-result.md) · [A5 实测记录](doc/a5-results-2026-11-17.zh-CN.md) | 两侧原始测量；A6 报告中的历史补丁可在[当时的目录](https://github.com/HaoZhang1024/simpler/tree/b36fdcca5/tests/fdwic/a6_dsv41_scheduler/doc)查阅 |

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
