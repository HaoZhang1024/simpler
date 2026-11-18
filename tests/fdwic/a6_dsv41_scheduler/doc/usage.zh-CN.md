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

## A6 复现前的构建环境

**本页前面的运行命令目前仅适用于 A5；A6 使用文末的现场平台工作树和单卡入口。** A6 交付目标为 percounter，构建包含其需要的 HBG/common 共享源码。

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

只编译 fixture 选中的 19 个核，不安装 PyPTO／PTOAS，不需要设备，也不构建运行时。
每个核依次执行 ccec → ld.lld → `.text` 合法性检查；任何失败都会返回非零。
`summary.json` 保存逐核阶段、工具版本、目标参数及源码／机器码指纹；逐核 `.log` 和 `.commands.json` 保留详细诊断。
输出目录必须是新目录，防止旧二进制混入。

**这里复用的是现有核参数 ABI 头文件，不是 A5 运行时。A6 percounter 的平台启动、ABI 与上板正确性仍需单独验证。**
黄区已验证生产 percounter 的 MIX 场景；完整 SWA 回放按文末执行。

## A6 任务描述转换

以下命令在 A6 的 x86_64 Host 上用本机 `g++` 执行；不使用 AICPU 交叉编译器，不需要 CANN 或设备：

```bash
python tests/fdwic/a6_dsv41_scheduler/prepare_plan.py \
  --output tests/fdwic/a6_dsv41_scheduler/build/a6-plan
```

脚本先编译两个 Host 小工具，解包原始 fixture，核对 2735 条记录的语义指纹；通过后生成 `plan-a6-rank0.bin`。
仅 t22 改为 48 个 1C1V block，t28 改为 32 个 1C1V block；保留全部输入、标量和依赖，原始 plan 留在 `bundle/`。
任何非预期变化都会报错。转换后的计划必须配合同分支 A6 核使用，不能交给 A5 运行时。

**A6 端现在可以先执行这两条离线命令。** 返回两个 `summary.json`；失败时加上相应 `.log`。
核编译成功和 Host 解码成功之后，仍需接入 A6 公共平台与 percounter 才能生成可执行运行包。
所缺平台资料列在 [运行时还缺什么](a6-migration.zh-CN.md#运行时还缺什么)，不需要对方先跑通模型。

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

在已经跑通 MIX 4/4 的黄区工作树中保留现场平台修改，并接入本次 SWA 入口改动。以最后通过的 MIX 构建作为对照。记录 Simpler 版本、未提交 diff 和新增 src/a6 文件清单；若交接两份归档，核对解包后 runtime 链接指向和实际加载库。本分支已附[已有文件 diff](a6-diff)，包含 16 个文件的改动；新增 src/a6 目录另行交付。已通过 4/4 的工作树保留原修改，只引入本轮 SWA 入口提交。新 checkout 可先用 git apply --check 核对补丁，并配套恢复同版 src/a6 目录（含符号链接）。

### 1. 构建与回放

使用该工作树已通过 MIX 的 CANN、项目 venv 和 percounter runtime。以下命令从 Simpler 根目录执行。DEVICE 填现场分配的设备号，QUERY 指向现场已构建的 tools/cann-examples/query 可执行文件，LIB 指向包含 percounter 子目录的 onboard 库目录。

```bash
SWA=tests/fdwic/a6_dsv41_scheduler
BUILD=$(mktemp -d "$SWA/build-r001-XXXXXX")
python -I "$SWA/prepare.py" build --platform a6 --pto-isa build/pto-isa --build-dir "$BUILD" --jobs 4
python -I "$SWA/run.py" --platform a6 --device "${DEVICE:?assigned A6 device}" \
  --a6-query "${QUERY:?path to query executable}" --runtime-lib "${LIB:?A6 onboard library directory}" \
  --build-dir "$BUILD" --output "$BUILD/function" --warmup 1 --rounds 1
```

prepare 先验证原始记录，再把已转换的 plan 写到 runner 实际读取的 bundle/plan-rank0.bin。核、replay adapter 与 callable 使用该工作树的平台和工具链重建。检查 build.json 的 platform=a6、tasks=16、executions=570，plan-conversion/summary.json 中 t22 为 48 个 1C1V block。run 先在指定设备执行 query device 并核对型号，再用 percounter 运行。反馈 build.json、每轮 console、result.json、总 summary 与退出状态。存在超时时沿用现场 ST 作业的限时与回收方式。

### 2. 回归与待证接口

- 场景测试沿用 4 个 MIX 通过时的 pytest 平台和设备参数。先对 tests/st/a5/percounter/acquire/test_acquire.py 做 --collect-only，逐类记录 collected、selected、passed、skipped 及原因。SpmdAic 先行，再测 MixedWaves、ReleasesSpmd、Predicate；按每个 case 的实际 task mask 登记支持范围。
- Graph、GraphPure、GraphSpmd、GraphPredicate 分开跑。若普通 submit 的 mask5 通过而 Graph body 失败，对照 graph_template.h 中 body 解码的 kernel_id、active_mask 与发布到设备的函数槽。TwoVectorSync 的原用例要求同一 block 上两个 AIV 同时驻留，列为硬件语义不适用；补验 mask6/7 经提交接口返回 INVALID_ARGS。区分平台列表遗漏、真实失败、预期排除。
- Q6 用现场三套编译器和实际平台 include 检查同一份布局断言。逐端记录 SchedulerTaskMetadata.kernel_ids、ChipTaskStorage 的 payload、PercounterControl、AicoreTeardownControl.exit_request 的大小、对齐与偏移。A6 有两个执行 lane；序列化槽位按实际结构取值。黄区报告中的 AIV 窗口 +0x100000 仍标为推断。
- 观察 t22 是否有 48 个完整 1C1V block 同时获准执行。用单独诊断轮核对 16 个任务、570 个参与实例，记录 30 个可写 buffer 的比较结果；现有 fixture 的零权重覆盖另用两个改写 MIX 核的非零输入核对分片与写回。先确认退出和重复调用，再用新输出目录采 10 轮 L0 并保留样本。
- release 改读 GM 后，用 A5 回归正常运行、提前退出和重复启动，核对 publish/release、metadata_ready、exit_request 与轮次。去除 A6-VERIFY 后重跑原 MIX 4 项和 SWA；记录探针清理前后构建版本。设备链 orchestrator 单独标注编译或上板覆盖。

首轮反馈填写“工作树版本及现场补丁 / 命令与退出码 / 首个失败函数、task、block、lane / 预期和实际值 / 证据片段”。若设备回放已经完成而 timing 汇总失败，分别记录 golden、退出和计时结果。


### 与现场 diff 核对的两项差异

1. 探测工具 aicore_reg_mapping.h 的 InitA6() 只建立 54 个表项，按 res_id 0..53 映射，注释写明 AIV 的 +0x100000 为推断。报告描述的是每 die 35 个候选窗口、缺陷跳号。请分别返回实际平台映射函数与该工具的版本、物理 ID 到 res_id 的换算及已观测的表项。先用已有握手和映射日志核对。当前工具不能作为 70 窗口或所有物理 ID 的验证依据。
2. lane_loop.h 的第一段等待已观察 aicpu_ready，diff 中第二段 release-wait 再检查同一个值，正常发布后会直接通过。实际放行点由 release_partition 提前到 publish_partition，且两段等待仍读 DATA_MAIN_BASE 的 EXIT。请在发布前取消、发布后首任务前取消、正常完成后复用三种时序下记录各 lane 的 ready、metadata_ready、exit_request、退出和回收状态，区分主动退出与 watchdog 超时。A5 也执行这段代码，应复验原 release 顺序依赖。清理探针时保留 GM 功能修改，按 hunk 审阅。
