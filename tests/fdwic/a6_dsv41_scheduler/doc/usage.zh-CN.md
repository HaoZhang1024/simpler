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

`prepare.py export` 供维护者从已有 SWA 快照更新 fixture，正常构建无需执行；参数见 `prepare.py export --help`。A6 构建入口见下文。

## 修改后要重做哪些步骤

**只改调度算法且 ABI、算子、输入契约不变时，重编 runtime，再用同一个 SWA 包复测。** 不需要重新生成模型代码或跑完整 forward。

| 改动 | 需要重做 | 可以保留 |
| ---- | -------- | -------- |
| 调度算法 | 重编匹配的运行时，重新测量和校验 | 输入、参考、核与任务图 |
| Tensor／调用 ABI | 重编受影响的 runner、适配器、核，并重建不兼容的 plan／包 | 经核对仍兼容的输入与计算逻辑 |
| 算子逻辑、shape、任务图 | 更新相应源码、清单、输入和参考，再编译组包 | 未受影响的材料 |
| A5 迁到 A6 | 适配平台与工具链、检查核及 plan，重编目标包 | 可兼容复用的 C++、输入和参考 |

典型调优顺序：**同一用例测基线 → 修改调度器 → 重编 runtime → 同一包复测 → 比较耗时并检查输出。** 切换 Git 分支不会自动更新磁盘上的运行库。详细泳道应另采，不混入 L0 性能样本。

## A6 计算核编译检查

在仓库根目录、已加载 CANN 环境的项目 venv 中执行：

```bash
python tests/fdwic/a6_dsv41_scheduler/compile_kernels.py \
  --pto-isa build/pto-isa \
  --output tests/fdwic/a6_dsv41_scheduler/build/a6-kernels
```

只编译 fixture 选中的 19 个核，不安装 PyPTO／PTOAS，不需要设备，也不构建运行时。
每个核依次执行 ccec → ld.lld → `.text` 合法性检查；任何失败都会返回非零。
`summary.json` 保存逐核阶段、工具版本、目标参数及源码／机器码指纹；逐核 `.log` 和 `.commands.json` 保留详细诊断。
输出目录必须是新目录，防止旧二进制混入。

## A6 任务描述转换

以下命令在 A6 的 x86_64 Host 上用本机 `g++` 执行；不使用 AICPU 交叉编译器，不需要 CANN 或设备：

```bash
python tests/fdwic/a6_dsv41_scheduler/prepare_plan.py \
  --output tests/fdwic/a6_dsv41_scheduler/build/a6-plan
```

脚本先编译两个 Host 小工具，解包原始 fixture，核对 2735 条记录的语义指纹；通过后生成 `plan-a6-rank0.bin`。
仅 t22 改为 48 个 1C1V block，t28 改为 32 个 1C1V block；保留全部输入、标量和依赖，原始 plan 留在 `bundle/`。
任何非预期变化都会报错。转换后的计划必须配合同分支 A6 核使用，不能交给 A5 运行时。

## SWA 逻辑资源预检

完成上述 plan 转换后，用 Host 编译器构建小工具。它读取实际 plan，逐任务检查 kernel mask、普通任务多波次和 sync_start 容量；依赖 Simpler 源码与 C++17 编译器。

```bash
SWA_DIR=tests/fdwic/a6_dsv41_scheduler
mkdir -p "$SWA_DIR/build/resource-check"
g++ -std=c++17 -O2 \
  -Itests/fdwic/dsv41_scheduler/production \
  -Isrc/common -Isrc/common/task_interface \
  -Isrc/a5/runtime/percounter/host \
  "$SWA_DIR/check_resources.cpp" \
  -o "$SWA_DIR/build/resource-check/check-resources"

# 54 是候选逻辑配对数；现场执行时填入公共平台确认的可用 C/V 配对数。
"$SWA_DIR/build/resource-check/check-resources" \
  "$SWA_DIR/build/a6-plan/plan-a6-rank0.bin" 54 1 \
  > "$SWA_DIR/build/resource-check/summary.json"
```

末尾两个参数依次为可用逻辑配对数、每组 AIV 数。通过时退出码为 0，JSON 包含任务数、执行实例数、最少配对数，以及逐任务 mask、sync_start 和 `isolated_waves`。失败时退出非零，stderr 给出任务编号和原因，stdout 留空。

当前转换后 SWA 的预期结果为 16 个任务、570 个实例、最少 48 组资源。47 组时应报告 t22 同步启动容量不足；原始 A5 plan 用 1C1V 检查时应报告 t22 的 mask 7 与拓扑不符。原始 A5 plan 使用 36 组、每组 2 AIV 可作对照。

`isolated_waves` 是单个任务独占给定逻辑资源时的波次数。整图依赖、设备配对映射、内存可见性与数值正确性由运行时和上板测试验证。

离线集成测试复用当前 fixture 和已有 plan 转换工具，自动编译两个 Host 小工具：

```bash
python tests/fdwic/a6_dsv41_scheduler/test_resources.py -v
```

默认使用 `g++`；环境变量 `CXX` 可指定 Host 编译器可执行文件路径。测试覆盖转换后 plan、原始 A5 plan、47／48 组边界、非法参数以及缺失／截断文件。

## 黄区接续测试

本轮执行顺序、固定版本、运行命令和回填位置见[黄区执行交接单](a6-handoff.zh-CN.md)。
