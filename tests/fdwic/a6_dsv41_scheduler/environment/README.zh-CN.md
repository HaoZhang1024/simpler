# A6 最小信息采集表

目标固定为：**在 `tests/fdwic/a6_dsv41_scheduler/` 实现脱离 PyPTO／PTOAS 的 SWA 单卡用例，使用已有 C++ 核，走 HBG 建图与 AICore 调度，并校验输出。**

已确定：A6 机器直接拉取当前 `a6-migrate-case` 分支；Simpler 源码及 SWA 业务代码以本分支为准，输入快照和参考数据由原机器准备。**不要求 A6 端已有适配好的 HBG、运行时二进制或成功用例，适配与跑通就是后续要完成的工作。**

## 给 A6 机器上的 agent

> 请只采集这台机器的硬件、SDK、PTO-ISA 和构建环境信息，填写下表。读取工具版本、SDK 配置／文档／示例源码即可，暂不安装依赖、修改代码、编译或跑设备测试。找不到的填“未找到”并注明查过的位置；不需要为了填表先跑通任何用例。交回信息后，由另一台机器完成本分支适配，再通知你拉取更新并验证。

采集日期：`待填写`。表中实际路径用于这次交接；不要把含用户名的机器路径提交到公共仓库。

## 必填表

每行都要有结果，可以填“未找到”。详细命令、日志放附件，表里只留结论和附件位置。

| 编号 | 要确认的信息 | 填写结果 | 证据／怎么查 |
| ---- | ------------ | -------- | ------------ |
| 01 | **芯片与执行环境**：实际芯片型号，真机／模拟器，Host 架构和系统版本；单卡任务通过什么命令申请、启动 | 待填写 | `uname -m`、`/etc/os-release`、`npu-smi info`；现有 `task-submit` 或当地调度器的使用方式。芯片型号以实际查询为准 |
| 02 | **CANN 工具链与平台配置**：SDK 根目录、版本、环境初始化命令；ccec、链接器、AICPU 交叉编译器的实际路径／版本；驱动版本 | 待填写 | 环境脚本、工具的 `--version`；附匹配芯片的 `platform_config/*.ini`（包含可查询的核数量、内存容量等配置）。有多个 SDK 时明确选中哪个 |
| 03 | **A6 编译与启动接口资料**：SDK 中 Cube／Vector 的目标参数、编译／链接参数；核加载、启动及同步接口的相关头文件／文档／示例位置 | 待填写 | 从 SDK 自带文档、示例或构建配置摘出相关内容并附来源文件。不要猜 `--cce-aicore-arch`，也不要求成功日志；接口差异由我们分析 |
| 04 | **PTO-ISA**：源码目录、可获取的仓库地址、分支／完整 SHA、未提交改动；A6 架构宏映射所在文件 | 待填写 | Git 信息和 `PTO_NPU_ARCH_A6`／`__NPU_ARCH__` 相关片段；若机器上的版本有额外 A6 修改，附相关补丁。没有安装就注明，不要求先运行 MXFP8／MIX 测试 |
| 05 | **Host 构建环境**：Python、C++ 编译器、CMake／Ninja 的路径和版本；项目 `.venv` 是否已有；可用工作目录 | 待填写 | 下面的只读命令。只记录现状，不创建环境或安装软件；若环境设置了 `CC`／`CXX`，一并记录 |

**03 要的是 SDK 提供的参数和接口资料，不是让 A6 端编写适配方案或证明运行成功。** 仅有文件路径而原机器无法读取时，请附相关小文件／片段，便于我们分析。

## 只读采集命令

逐组执行并保存原始输出；失败时保留报错和退出码。命令用于查证上表，不要求所有机器都有相同目录。工具未找到时不自动安装，SDK 和源码目录从已有环境／工作目录确定，不扫描整台机器。

基础环境：

```bash
uname -m
cat /etc/os-release
command -v python3 g++ cmake ninja npu-smi task-submit
python3 --version
g++ --version
cmake --version
ninja --version
printf 'ASCEND_HOME_PATH=%s\nCC=%s\nCXX=%s\n' "${ASCEND_HOME_PATH:-}" "${CC:-}" "${CXX:-}"
npu-smi info
```

若 `npu-smi` 因权限失败且本机有 `task-submit`，可用 `task-submit --run 'npu-smi info'` 重查；不要据此填“无设备”。本次不启动计算，后续单卡验证也要遵守本机设备申请方式。

在**已确认的** SDK 内查工具位置；若 `ASCEND_HOME_PATH` 未设置，先从现有环境脚本确定路径，不能直接套用其他机器的值：

```bash
if [ -n "${ASCEND_HOME_PATH:-}" ] && [ -d "$ASCEND_HOME_PATH" ]; then
    rg --files -L "$ASCEND_HOME_PATH" |
        rg '(^|/)(ccec|ld\.lld|aarch64[^/]*g\+\+|version[^/]*|ascend[^/]*install\.info)$|/platform_config/[^/]+\.ini$'
fi
```

对找到的编译器分别执行 `"实际工具路径" --version`，记录路径和输出。芯片配置只附与 01 中型号匹配的文件；03 的参数从 SDK 配置／文档／示例中读取即可。

在 PTO-ISA 源码目录执行；不是 Git 仓库时，记录发布包名称／版本及相关文件。Simpler 已确定使用当前分支，不需要另外寻找其他版本：

```bash
pwd
git rev-parse HEAD
git branch --show-current
git status --short
git diff HEAD --stat
```

在 PTO-ISA 根目录查架构映射：

```bash
rg -n -C 5 'PTO_NPU_ARCH_A6' include/pto/common
```

## 交回什么，下一步由谁做

交回 **填写后的本文 + 表中引用的少量附件**：工具／版本查询输出、匹配芯片的 SDK 配置、A6 编译与启动接口的相关文档／头文件／示例片段，以及 PTO-ISA 版本信息。仓库地址去掉凭据，不导出完整环境变量。

若 PTO-ISA 有仅在本机存在的修改，附可获取的分支或相关补丁，未提交部分可用 `git diff HEAD -- <相关路径>` 导出，必要的新源码另附。没有就写“无”。无需发送整个仓库、SDK 或模型。

```text
A6 端填写环境表、提供接口资料
    ↓
我们在当前分支适配工具链和必要运行时逻辑
在 a6_dsv41_scheduler/ 提供 SWA 构建、组包、运行与校验入口
准备输入快照和参考数据，全流程不调用 PyPTO／PTOAS
    ↓
A6 端拉取更新，按给定命令编译和单卡验证，返回日志／校验结果
    ↓
我们根据实际反馈继续修正，直到用例跑通
```
