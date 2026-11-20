# A6 percounter SWA 黄区执行交接单

**当前任务：用固定版本跑一次 A6 单卡 SWA L0 基线。** CntNotify 六组硬件同步测量已结项。黄区执行脚本、在内网保存产物；项目负责人负责对外反馈摘要。

## 已交付的 SWA 代码

| 代码 | 蓝区已经验证 | SWA 复测时覆盖 |
| ---- | ------------ | ------------ |
| [A6 平台](../../../../src/a6/platform/)和 [percounter 启停握手](../../../../src/a5/runtime/percounter/aicore/lane_loop.h)：接入 1 AIC + 1 AIV 的资源组，经 GM 发布启动、退出信号 | A6 runtime 与 dispatcher 已预编译；2 项 CPU 握手测试通过，覆盖前次启动信号残留、启动中止及超时 | SWA 在实际分配的 966B7 上启动，连续回放并正常退出 |
| [plan 转换](../prepare_plan.py)、[资源检查](../test_resources.py)和[固定输入检查](../test_fixture.py)：把 t22、t28 转成 1C1V，沿用原输入和参考输出 | 6 项资源测试、2 项输入测试通过。A6 plan 有 16 个计算任务、570 个执行实例；t22 至少需要 48 对核 | 由脚本转换同一份 plan，回放后对照参考输出 |
| [SWA 组包](../prepare.py)、[单卡入口](../test_a6_swa.sh)和[结果汇总](../run.py) | 预构建已生成 19 个 kernel、native-runner、replay、plan 和 callable。预构建目录缺少 Git 提交信息，最后一步写入 `build.json` 未完成 | 从固定 Git 提交生成 `case/build.json`，完成 1 轮预热和 10 轮 L0 正式测量 |

此前黄区现场版本的实测结果保存在[A6 原始报告](a6-result.md)。SWA 复测固定使用[代码提交 cf78bd31a](https://github.com/HaoZhang1024/simpler/commit/cf78bd31a28aedeed4a43592c43f9203b6ce4348)。

## 执行 SWA 单卡 L0

已有同一提交、同一输入、同一轮数的成功结果时，直接使用该次摘要。否则使用已加载现场 CANN 9.3.0 的 Linux shell，从用于 SWA 的 Simpler 仓库根目录执行。沿用现场的项目 `.venv`、CMake、Ninja，以及 `build/pto-isa` 下的 PTO-ISA checkout。

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

## 项目负责人反馈什么

| 项目 | 反馈摘要 | 内网记录位置 |
| --- | --- | --- |
| CntNotify（已完成） | 六组时延已有记录。手边有作业号或结果目录时，选填一个供追溯 | [CntNotify 并发时延](a6-swa-performance-progress.zh-CN.md#cntnotify-并发时延) |
| SWA L0 成功 | 设备号、实际提交、正式轮数、数值校验、AICore 和 Device 均值。终端末行或 `result/summary.json` 的均值单位为 ms | [SWA 单卡 L0 复测](a6-swa-performance-progress.zh-CN.md#swa-单卡-l0-复测) |
| SWA 构建或运行失败 | 失败步骤、首条具体报错（含错误码） | 同一 SWA 栏目 |

黄区在本次输出目录保留 `test.log`、`case/build.json` 和 `result/`。项目负责人在聊天中贴摘要即可，蓝区据此更新性能对比或修复代码。
