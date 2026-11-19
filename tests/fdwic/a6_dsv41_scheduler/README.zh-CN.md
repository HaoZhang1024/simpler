# SWA 独立用例

**A5 的独立 SWA 已跑通；已有 C++ 和输入足以完成构建、执行与校验，全流程不调用 PyPTO／PTOAS。黄区已跑通 A6 单卡 percounter SWA；下一步固定源码并复测同版 A5/A6。**

| 问题 | 当前结论 |
| ---- | -------- |
| 测什么 | DSV4.1 的 SWA 注意力子层，含 mHC、量化、Q/KV 投影、缓存更新、Attention 和输出投影 |
| 规模 | 19 个核、16 个计算任务；A5 为 578 个执行实例，A6 转换为 570 个；独立切片单卡运行 |
| A5 结果 | HBG／percounter 均逐轮校验通过；L0 AICore 均值分别为 0.267843／0.185173 ms |
| 已完成的提取 | 只编 SWA 所需核，随目录保存固定输入和参考，复用生产 runner 与原 PR 统计器 |
| A6 状态 | 两个 MIX 核已改为 1C1V，19／19 通过本地编译／链接／机器码提取；plan 转换通过离线检查。黄区报告完整 SWA 正式 10 轮通过，AICore L0 均值 265.768 µs、Device 均值 357.712 µs，见[现场结果](doc/a6-result.md)与[下一轮命令](doc/usage.zh-CN.md#黄区接续测试) |
| 依赖边界 | 仍需 CANN、PTO-ISA 和匹配的 Simpler；解除的是 PyPTO／PTOAS 的代码生成依赖 |

SWA 包含 MIX／sync_start 协同，但本切片没有跨卡通信和 deferred 等待。因此它适合验证计算与调度，双卡 MoE／defer_wait 需要后续独立验证。

## 文档索引

| 要看什么 | 文档 | 内容 |
| -------- | ---- | ---- |
| 怎么构建、运行和复测 | [使用方法](doc/usage.zh-CN.md) | 命令、参数、输出位置、修改后需要重编什么 |
| 为什么不依赖 PyPTO／PTOAS | [执行原理](doc/execution.zh-CN.md) | 已有材料、真实执行路径、依赖边界、全新算子的生成流程 |
| A6 要改哪里、如何验证 | [迁移分析](doc/a6-migration.zh-CN.md) | percounter 范围、共享依赖、MIX 核与 ABI、实施顺序、已确认范围、待查问题、验收要求 |
| 后续适配如何推进 | [具体任务](doc/a6-adaptation-tasks.zh-CN.md) | 两份 diff 的集成范围、三端 ABI、启退回归、同版 L0 与任务耗时分析 |
| 交给 A6 端查什么 | [环境核对与补充查证任务](doc/a6-environment.zh-CN.md#5-黄区-agent-测试与反馈计划) | 离线复现、worker 映射实测、Q1–Q7、单 MIX 与 SWA 验收、反馈模板 |
| A5 跑出了什么结果 | [2026-11-17 复测报告](doc/a5-results-2026-11-17.zh-CN.md) | 性能与波动、校验范围、版本、失败记录、复现与证据 |

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
| [results/2026-11-17-a6-offline/](results/2026-11-17-a6-offline/) | A6 编译前后、A5 机器码不变、plan 转换的离线证据；不含设备结果 |

文档集中在 `doc/`；构建产物写入 `build/`，新的测试输出由 `--output` 指定。
