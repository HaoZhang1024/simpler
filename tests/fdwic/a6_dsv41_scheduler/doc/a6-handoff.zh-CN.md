# A6 percounter SWA 黄区执行交接单

**当前交付是把 A5 已测的 002 六组操作在 A6 上按原方法复测。** 蓝区核对结果后，黄区再执行 SWA 单卡复测。

**黄区结果填在哪里。** 使用内网页面《A6 percounter SWA 性能分析与每日进展》。首次转存全文，已有页面只追加新栏目。下表链接指向仓库模板，实测结果填在内网同名栏目。

| 测试任务 | 内网页面的填写位置 | 黄区填什么 |
| --- | --- | --- |
| 当前优先：CntNotify | 黄区结果回填 → [CntNotify 并发时延](a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延) | 本分支探针生成的 result.md、ranks.json、两份 CSV 和运行日志的内网位置，设备号、代码和 PTO-ISA 版本；失败时附返回码 |
| 随后：SWA 单卡复测 | 黄区结果回填 → [SWA 单卡 L0 复测](a6-swa-performance-progress.zh-CN.md#swa-单卡-l0-复测) | 设备、版本、轮数、校验状态和本轮输出目录 |

蓝区每次交付新测试时，先在目标文档预留一行或新建结果页，再在这张表中写明文档名、栏目和待填内容。

## 当前执行：用本分支探针在 A6 测六组同址访问

本轮探针固定在 Simpler 提交 `8090437706faeea0df8eb784e92c38dc6cb7efb2`。黄区使用已加载 CANN 9.3.0 的 Linux shell、Bash、Git、支持 C++17 的主机编译器和 Python 3.8 以上（标准库）。分配一张 966B7 卡，确认逻辑设备号。

**首次下载。** 在存放源码的位置执行以下命令。已有该提交的 checkout 可直接进入仓库根目录执行下一步。

```bash
git clone --filter=blob:none --single-branch --branch a6-swa-port --no-checkout \
  https://github.com/HaoZhang1024/simpler.git simpler-a6-same-address &&
cd simpler-a6-same-address &&
git switch --detach 8090437706faeea0df8eb784e92c38dc6cb7efb2
```

**执行。** 在上述仓库根目录执行。已有分配变量 `TASK_DEVICE` 时沿用该值，否则按提示输入设备号。脚本编译本分支的探针，从 `PTO_ISA_ROOT` 或 `build/pto-isa` 取与 A5 匹配的 PTO-ISA `6065c782e`；若版本不同，自动从 GitHub 下载固定提交。编译范围为本探针的设备库和 Host 程序。

```bash
DEVICE=${TASK_DEVICE:-}
if [ -z "$DEVICE" ]; then read -rp '已分配的 A6 逻辑设备号: ' DEVICE; fi
bash tests/fdwic/a6_dsv41_scheduler/probes/a6_same_address/run.sh "$DEVICE"
```

| 固定条件 | 本次执行 |
| --- | --- |
| 并发与起跑 | A6 为 48 AIC + 48 AIV；A5 对照为 32 AIC + 64 AIV。硬件 MIX SYNCALL 起跑，每核每轮对同一自然对齐 32 位字访问一次 |
| 读三组 | GM 普通读、GM atomicAdd(0) 并消费旧值、CntNotify SET 映射读。访问结果被消费后取结束时间 |
| 写三组 | GM 普通写 1、GM atomicExch(1)、CntNotify SET 写 1。写后执行 DSB_DDR 再取结束时间；交换写每轮恰有一个核返回旧值 0 |
| 校验与统计 | 每组预热 1 轮、正式 192 轮。读值和轮末状态逐轮校验。以本轮最早开始为零点按完成时间排序，输出第 1／48／96 名、P10/P90、起跑分散和相邻间隔 |

**回填。** 开头的 `A6 output:` 给出目录，成功时末行显示 `PASS: six validated scenarios`。把 `result.md` 的成表复制到内网[CntNotify 并发时延](a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延)，填写设备、作业号、输出目录（含 `gm.csv`、`cnt_notify.csv`、`ranks.json` 和日志）。若失败，填失败步骤和 `run.log` 位置，并保留已有数据。若尚未打印 `A6 output:`，回传终端报错。[A5 已归档的对照结果](https://github.com/mihudaner/simpler/tree/0d76a7d55/tests/fdwic/a6_dsv41_scheduler/results/002-hbg-same-address-access)

**GM 软件栅**是各核通过全局内存中的共享计数或标志集合：到达的核更新 GM，等待的核轮询 GM，条件满足后各自开始。先放行的核可能已经在计时，其他核还在轮询。上面的六组统一用硬件 MIX SYNCALL，同一次访问之后的 DSB 用于约束本核写完成。

## 后续 SWA 复测已交付的代码

| 代码 | 蓝区已经验证 | SWA 复测时覆盖 |
| ---- | ------------ | ------------ |
| [A6 平台](../../../../src/a6/platform/)和 [percounter 启停握手](../../../../src/a5/runtime/percounter/aicore/lane_loop.h)：接入 1 AIC + 1 AIV 的资源组，经 GM 发布启动、退出信号 | A6 runtime 与 dispatcher 已预编译；2 项 CPU 握手测试通过，覆盖前次启动信号残留、启动中止及超时 | SWA 在实际分配的 966B7 上启动，连续回放并正常退出 |
| [plan 转换](../prepare_plan.py)、[资源检查](../test_resources.py)和[固定输入检查](../test_fixture.py)：把 t22、t28 转成 1C1V，沿用原输入和参考输出 | 6 项资源测试、2 项输入测试通过。A6 plan 有 16 个计算任务、570 个执行实例；t22 至少需要 48 对核 | 由脚本转换同一份 plan，回放后对照参考输出 |
| [SWA 组包](../prepare.py)、[单卡入口](../test_a6_swa.sh)和[结果汇总](../run.py) | 预构建已生成 19 个 kernel、native-runner、replay、plan 和 callable。预构建目录缺少 Git 提交信息，最后一步写入 `build.json` 未完成 | 从固定 Git 提交生成 `case/build.json`，完成 1 轮预热和 10 轮 L0 正式测量 |

此前黄区现场版本的实测结果保存在[A6 原始报告](a6-result.md)。SWA 复测固定使用[代码提交 cf78bd31a](https://github.com/HaoZhang1024/simpler/commit/cf78bd31a28aedeed4a43592c43f9203b6ce4348)。

## CntNotify 结果确认后执行 SWA

使用已加载现场 CANN 9.3.0 的 Linux shell，从用于 SWA 的 Simpler 仓库根目录执行。沿用现场的项目 `.venv`、CMake、Ninja，以及 `build/pto-isa` 下的 PTO-ISA checkout。

```bash
(
  set -e
  git fetch https://github.com/HaoZhang1024/simpler.git refs/heads/a6-swa-port
  git switch --detach cf78bd31a28aedeed4a43592c43f9203b6ce4348
  source .venv/bin/activate
  test "$(git -C build/pto-isa rev-parse HEAD)" = "$(cat pto_isa.pin)" || {
    echo "PTO-ISA 版本与 pto_isa.pin 不一致"; exit 1
  }
  read -rp '本次分配的 A6 设备号: ' DEVICE
  bash tests/fdwic/a6_dsv41_scheduler/test_a6_swa.sh "$DEVICE"
)
```

脚本依次构建 A6 percounter、设备查询工具和 SWA 包，核对芯片型号后运行。开头的 `SWA output:` 给出本次目录。成功时终端最后的 `percounter` 行显示 `PASS`；`result/summary.json` 中 `status` 为 `passed`，该 runtime 的 `rounds` 为 10、`numerical_validation` 为 `true`。

| 执行结果 | 黄区回传 |
| -------- | -------- |
| SWA 成功 | 本次目录的 `test.log`、`case/build.json` 和整个 `result/`。其中 `result/summary.json` 已含逐轮 AICore、Device 时延（ms）和校验状态 |
| SWA 构建或运行失败 | 回传 `test.log` 及已生成的 `case/build.json`、`result/`。若还没打印 `SWA output:`，直接回传终端报错 |

收到这两份结果后，蓝区更新[A6 / A5 对比](a6-a5-comparison.zh-CN.md)。已有 t22、t25、t35 的 [L4 反馈](a6-l4-feedback.md)继续用于分析；本轮黄区执行到上表即完成。
