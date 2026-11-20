# A6 percounter SWA 黄区执行交接单

**当前交付是把 A5 已测的 002 六组操作在 A6 上按原方法复测。** 蓝区核对结果后，黄区再执行 SWA 单卡复测。

**黄区结果填在哪里。** 使用内网页面《A6 percounter SWA 性能分析与每日进展》。首次转存全文，已有页面只追加新栏目。下表链接指向仓库模板，实测结果填在内网同名栏目。

| 测试任务 | 内网页面的填写位置 | 黄区填什么 |
| --- | --- | --- |
| 当前优先：CntNotify | 黄区结果回填 → [CntNotify 并发时延](a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延) | 002 的 ranks.json、两份 CSV 和运行日志的内网位置，设备号、代码和 PTO-ISA 版本；失败时附返回码 |
| 随后：SWA 单卡复测 | 黄区结果回填 → [SWA 单卡 L0 复测](a6-swa-performance-progress.zh-CN.md#swa-单卡-l0-复测) | 设备、版本、轮数、校验状态和本轮输出目录 |

蓝区每次交付新测试时，先在目标文档预留一行或新建结果页，再在这张表中写明文档名、栏目和待填内容。

## 当前执行：在 A6 复现 A5 的 002

先找黄区报告引用的那次 **002** 作业。若能对应到原版 `probes/same_address`、PTO-ISA `6065c782e`、48C+48V、1 轮预热 + 192 轮正式以及六组读写校验，直接登记该作业的 `ranks.json`、GM/CntNotify CSV 和日志。原始 CSV 齐全时可用同版 `ranks.py` 重新汇总。现场的 op00–17 软件栅障实验另作补充。

缺少可核对的原版结果时，在已加载 A6 CANN、配有 Python 3.10+、Git 和主机 C++ 编译器的 Linux shell，从 Simpler 根目录执行下面一段。输入已经独占的逻辑设备号。命令下载同事的固定版本与对应 PTO-ISA，在本次输出目录独立编译原探针。

```bash
(
  set -euo pipefail
  read -rp '已分配的 A6 逻辑设备号: ' device
  [[ "$device" =~ ^[0-9]+$ ]]
  mkdir -p build
  out=$(mktemp -d "$PWD/build/002-a6-XXXXXXXX")
  echo "002 output: $out"
  exec > >(tee "$out/run.log") 2>&1
  fetch_version() {
    git init -q "$1"
    git -C "$1" fetch -q --depth 1 "$2" "$3"
    git -C "$1" checkout -q --detach FETCH_HEAD
    git -C "$1" rev-parse HEAD
  }
  fetch_version "$out/src" https://github.com/mihudaner/simpler.git 0d76a7d55bcf8976a25777a5dc2ce9b5cbed2eeb
  fetch_version "$out/isa" https://github.com/hw-native-sys/pto-isa.git "$(cat "$out/src/pto_isa.pin")"
  p="$out/src/tests/fdwic/a6_dsv41_scheduler/probes/same_address"
  bash "$p/build.sh" a6 "$out/isa" "$out/bin"
  "$out/bin/probe" "$device" 48 gm "$out/gm.csv" 2>&1 | tee "$out/gm.log"
  "$out/bin/probe" "$device" 48 cnt_notify "$out/cnt_notify.csv" 2>&1 | tee "$out/cnt_notify.log"
  python3 "$p/ranks.py" "$out/gm.csv" "$out/cnt_notify.csv" --blocks 48 --vectors 48 \
    --clock-hz 1000000000 --output "$out/ranks.json"
)
```

六组是 GM 普通读／写、GM atomic 加零读／交换写、CntNotify SET/read 读／写。全部使用硬件 MIX SYNCALL 起跑；每个写操作在结束取时前执行 DSB。A5 启动 32C+64V，A6 启动 48C+48V，两端均为 96 个参与核。成功时登记含六组的 `ranks.json` 和日志；失败时登记已生成文件和首条报错。蓝区负责与 A5 逐组比对。[原始 A5 数据与方法](https://github.com/mihudaner/simpler/tree/0d76a7d55/tests/fdwic/a6_dsv41_scheduler/results/002-hbg-same-address-access)

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
