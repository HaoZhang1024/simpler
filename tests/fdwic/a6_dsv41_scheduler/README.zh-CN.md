# SWA 独立用例

**A5 的独立 SWA 已跑通；已有 C++ 和输入足以完成构建、执行与校验，全流程不调用 PyPTO／PTOAS。A6 环境信息已收到，首轮只跑通 HBG；percounter 与性能后续再考虑。**

| 问题 | 当前结论 |
| ---- | -------- |
| 测什么 | DSV4.1 的 SWA 注意力子层，含 mHC、量化、Q/KV 投影、缓存更新、Attention 和输出投影 |
| 规模 | 19 个核、16 个计算任务、578 个执行实例；独立切片单卡运行 |
| A5 结果 | HBG／percounter 均逐轮校验通过；L0 AICore 均值分别为 0.267843／0.185173 ms |
| 已完成的提取 | 只编 SWA 所需核，随目录保存固定输入和参考，复用生产 runner 与原 PR 统计器 |
| A6 状态 | 环境已核对；远端报告 17／19 个核编译通过，两个 MIX 核与平台运行时待适配；尚无 SWA 上板结果 |
| 依赖边界 | 仍需 CANN、PTO-ISA 和匹配的 Simpler；解除的是 PyPTO／PTOAS 的代码生成依赖 |

SWA 包含 MIX／sync_start 协同，但本切片没有跨卡通信和 deferred 等待。因此它适合验证计算与调度，双卡 MoE／defer_wait 需要后续独立验证。

## 文档索引

| 要看什么 | 文档 | 内容 |
| -------- | ---- | ---- |
| 怎么构建、运行和复测 | [使用方法](doc/usage.zh-CN.md) | 命令、参数、输出位置、修改后需要重编什么 |
| 为什么不依赖 PyPTO／PTOAS | [执行原理](doc/execution.zh-CN.md) | 已有材料、真实执行路径、依赖边界、全新算子的生成流程 |
| A6 要改哪里、如何验证 | [迁移分析](doc/a6-migration.zh-CN.md) | HBG 范围、MIX 核与 ABI、实施顺序、已确认范围、待查问题、验收要求 |
| A6 已知什么、还缺什么 | [环境核对](doc/a6-environment.zh-CN.md) | 真实环境、编译结果边界、报告修正、待补资料与交接方式 |
| A5 跑出了什么结果 | [2026-11-17 复测报告](doc/a5-results-2026-11-17.zh-CN.md) | 性能与波动、校验范围、版本、失败记录、复现与证据 |

## 代码与数据

| 位置 | 用途 |
| ---- | ---- |
| [prepare.py](prepare.py) | 解包输入，编译 SWA 核与原生工具，组装运行包 |
| [run.py](run.py) | 申请单卡，运行 HBG／percounter，校验并统计 |
| [test_fixture.py](test_fixture.py) | 离线检查输入包与参考覆盖 |
| [fixtures/](fixtures/) | 固定输入、plan、参考与来源清单 |
| [results/2026-11-17-a5/](results/2026-11-17-a5/) | A5 逐轮数据、日志和校验和清单 |

文档集中在 `doc/`；构建产物写入 `build/`，新的测试输出由 `--output` 指定。
