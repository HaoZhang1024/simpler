# SWA 使用方法：构建、运行与调优复测

[返回索引](../README.zh-CN.md)

## 首次运行 A5

在仓库根目录加载对应 CANN 环境、激活项目 `.venv`，执行：

```bash
# 构建与本分支匹配的运行时；关闭额外调度／编排打点。
python simpler_setup/build_runtimes.py --platforms a5 \
  --runtime host_build_graph --runtime percounter \
  --profiling-dfx 1 --profiling-orch 0 --profiling-sched 0 --profiling-tensormap 0

# 解开固定输入，编译 SWA 的 19 个核及原生回放工具。
python -I tests/fdwic/a6_dsv41_scheduler/prepare.py build \
  --platform a5 --pto-isa build/pto-isa --jobs 4

# 自动经 task-submit 申请 1 卡，顺序测 HBG 和 percounter。
python -I tests/fdwic/a6_dsv41_scheduler/run.py \
  --output outputs/swa-a5-r001
```

**默认口径：每种调度 1 次预热、10 次 L0 正式测量，逐轮校验。** 编译在申请设备前完成，两种调度使用同一张卡。

| 需求 | 参数／操作 |
| ---- | ---------- |
| 只测一种调度 | 给 `run.py` 加 `--runtime host_build_graph` 或 `--runtime percounter` |
| 指定运行时库 | `--runtime-lib` 指向已编译运行时的 `a5/onboard` 目录 |
| 重新构建用例 | 给 build 和 run 指定同一个新的 `--build-dir`；默认目录为用例目录 `build/a5/` |
| 再测一轮 | 使用新的 `--output`；脚本拒绝覆盖已有结果 |
| 查看结果 | 输出目录的 `summary.json`；各调度子目录保留原生结果、console 和 Host 端点日志 |
| 离线检查输入包 | `python -I tests/fdwic/a6_dsv41_scheduler/test_fixture.py`，不占设备 |

`prepare.py export` 供维护者从已有 SWA 快照更新夹具，正常构建无需执行；参数见 `prepare.py export --help`。当前脚本只接受 `--platform a5`。

## 修改后要重做哪些步骤

**只改调度算法且 ABI、算子、输入契约不变时，重编 runtime，再用同一个 SWA 包复测。** 不需要重新生成模型代码或跑完整 forward。

| 改动 | 需要重做 | 可以保留 |
| ---- | -------- | -------- |
| 调度算法 | 重编匹配的运行时，重新测量和校验 | 输入、参考、核与任务图 |
| Tensor／调用 ABI | 重编受影响的 runner、适配器、核，并重建不兼容的 plan／包 | 经核对仍兼容的输入与计算逻辑 |
| 算子逻辑、shape、任务图 | 更新相应源码、清单、输入和参考，再编译组包 | 未受影响的材料 |
| A5 迁到 A6 | 适配平台与工具链、检查核及 plan，重编目标包 | 可兼容复用的 C++、输入和参考 |

典型调优顺序：**同一用例测基线 → 修改调度器 → 重编 runtime → 同一包复测 → 比较耗时并检查输出。** 切换 Git 分支不会自动更新磁盘上的运行库。详细泳道应另采，不混入 L0 性能样本。

## A6 复现前的构建环境

**本页前面的运行命令目前仅适用于 A5；A6 平台适配和正式命令尚未完成。** 首轮 A6 只构建／运行 HBG，不默认连跑 percounter。

远端报告的系统 CMake 为 3.16.3。原生工具的 [CMakeLists.txt](../../dsv41_scheduler/production/CMakeLists.txt) 声明最低 3.20；现有 [AICore 运行时构建](../../../../src/a5/platform/onboard/aicore/CMakeLists.txt) 还实际使用了 Makefile 生成器的 `DEPFILE` 支持，要求 CMake 3.20。因此沿用这条构建路径时，不能只调低版本声明。

建议在项目 `.venv` 提供 `cmake>=3.20` 和当前入口使用的 Ninja，不升级系统 CMake，也不改用户全局环境；复现时记录 `command -v cmake ninja` 和各自版本。3.20 是当前构建链要求，不是 A6 芯片本身的硬要求。若选择其他生成器或兼容旧版本，需要验证依赖追踪和重编行为。

Host 的 x86_64 C++ 工具、AICPU 的 aarch64 交叉编译器、AICore 的 `dav-920r1-*` ccec 目标分别配置。没有 task-submit 的 A6 机器按实际设备占用方式提供执行入口，不能直接复用本页的 A5 队列命令。环境依据与剩余资料见 [环境核对](a6-environment.zh-CN.md)。

## A6 计算核编译检查

在仓库根目录、已加载 CANN 环境的项目 venv 中执行：

```bash
python tests/fdwic/a6_dsv41_scheduler/compile_kernels.py \
  --pto-isa build/pto-isa \
  --output tests/fdwic/a6_dsv41_scheduler/build/a6-kernels
```

只编译夹具选中的 19 个核，不安装 PyPTO／PTOAS，不需要设备，也不构建运行时。
每个核依次执行 ccec → ld.lld → `.text` 合法性检查；任何失败都会返回非零。
`summary.json` 保存逐核阶段、工具版本、目标参数及源码／机器码指纹；逐核 `.log` 和 `.commands.json` 保留详细诊断。
输出目录必须是新目录，防止旧二进制混入。

**这里复用的是现有核参数 ABI 头文件，不是 A5 运行时。A6 HBG 的平台启动、ABI 与上板正确性仍需单独验证。**
`prepare.py build` 和 `run.py` 当前仍只提供已验证的 A5 运行入口。
