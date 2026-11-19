# A6 percounter SWA 交付与性能验证待办

2026-11-19，按分支 `a6-swa-port@3c731ee31` 核对。黄区已用现场工作树跑通完整 SWA。黄区已完成干净目录验收。当前优先使用已有 A5/A6 L4 对齐 t22、t25、t35；源码交付与同版 L0 属于后续事项。见[A5 实测与黄区反馈表](swa-l4-comparison.zh-CN.md)。构建及运行命令见[使用方法](usage.zh-CN.md#黄区接续测试)。

## 已完成与基线

- [x] Host 资源排序支持 1C2V、1C1V。14 项资源排序测试通过；真实 plan 的 6 项离线检查覆盖 t22 的 47/48 对资源边界。
- [x] 黄区完成 19 个 SWA kernel 的编译、plan 转换和单卡 percounter 回放。A6 plan 含 16 个计算任务、570 个执行实例；固定输入的输出检查通过。
- [x] 黄区 MIX 的 chain16/burst16 × mask3/5 共 4 项通过。另 9 类中 8 类通过；TwoVectorSync 要求同一 block 的两个 Vector 同时驻留，按 1C1V 平台条件排除。GraphSpmd 的 C/V kernel 使用平台槽位步长，已覆盖 54 组及 partial_sync_2。逐类结果见[现场报告第 4 节](a6-result.md)。

| 平台与实测来源 | AICore L0 均值 | Device 均值 |
| -------------- | -------------- | ----------- |
| A5，11 月 17 日，runtime `26b0511f3`，独立用例工作树基于 `4b2d9ca4b` | 185.173 µs | 296.698 µs |
| A6，黄区工作树基于 `b921a01b`，含 SWA 入口 `e8fad256d` 与现场修改 | 265.768 µs | 357.712 µs |

两者均为 1 次预热、10 次正式计量。A6 相对历史 A5 的 AICore 窗口长 80.595 µs，Device 长 61.014 µs。AICore 窗口包含核计算、调度和依赖等待。先用第 4 步比较已有 L4；第 3 步用于确认同版生产耗时。[A5 原始样本](../results/2026-11-17-a5/samples.csv) · [A5 基线版本说明](a5-results-2026-11-17.zh-CN.md)

## 分步任务

| 顺序 | 执行位置 | 交付物 | 依赖 |
| ---- | -------- | ------ | ---- |
| 1. 固定上板源码 | 蓝区整理，黄区核对 | 可从干净目录重建的源码提交，与现场版本对应 | 可立即核对已有文件；平台目录需现场清单 |
| 2. 核对 ABI、退出和诊断改动 | 蓝区审代码，黄区构建与上板 | 三端布局对照、生命周期结果、去探针后的功能结果 | ABI 可在现场工作树先做；回归使用固定版本 |
| 3. 建立同版性能基线 | A5 与 A6 各自设备环境 | 两份完整样本、构建与加载库记录 | 步骤 1、2 的交付版本 |
| 4. 定位耗时差 | 两侧采诊断，蓝区分析 | 按任务拆分的耗时、首个值得修改的函数或 kernel | 已有 A5/A6 L4 和各自同轮编号表 |

### 1. 让 Git 源码对应黄区通过的工作树

- [ ] **蓝区：整理已有文件。** [a6-diff1](a6-diff1) 是累计补丁，涵盖平台注册、scheduler 容量、GM 放行和退出、SSBUF、Host/设备侧 submit 槽位归一化及 ST。以它作为已有文件的来源，保留 Git 中更新后的现场报告。以下检查已在 `3c731ee31` 通过，覆盖 29 个文件中的 28 个；整份检查在已更新的报告处冲突。

```bash
git apply --check --exclude=tests/fdwic/a6_dsv41_scheduler/doc/a6-result.md \
  tests/fdwic/a6_dsv41_scheduler/doc/a6-diff1
```

- [ ] **黄区：核对新增平台文件。** 返回通过 SWA 时的 `src/a6/` 相对路径、文件类型、符号链接目标及文件指纹。蓝区用 [a6va5-diff](a6va5-diff) 对照 8 个平台文件，包括 54 组 1C1V、2 KiB SSBUF、核到寄存器窗口的映射、Cube/Vector 编译目标。末尾 11 个 sim 文件和 1 份文档是 A6 目录的省略清单，整理时保留 A5 原目录。
- [x] **黄区：干净目录验收已完成。** 10 轮功能校验通过，AICore 267.034 µs、Device 362.065 µs；保留[现场记录 §7.4](a6-result.md)。

### 2. 关闭剩余正确性问题

- [ ] **三端 ABI。** Host、AICPU、AICore 分别用实际 include 和编译参数核对 SchedulerTaskMetadata.kernel_ids、ChipTaskStorage 的 payload、PercounterControl、AicoreTeardownControl.exit_request 的槽数、大小、对齐和关键偏移，按字段返回三列结果。
- [ ] **放行、退出和复用。** 核对 lane_loop.h 的 aicpu_ready、metadata_ready、exit_request 与 AICPU 的 publish_partition、release_partition 顺序。覆盖发布前取消、发布后首任务前取消、正常退出后再次调用和 Worker 重建，保存每轮请求、回执、退出状态及是否触发 watchdog。共享代码在 A5 同样回归。
- [ ] **设备侧 submit。** 现场 ST 已覆盖 Host orchestrator 的 mask5 折叠。若走 AICPU orchestrator 的入口可用，分别验证 mask5 的 AIV kernel 进入 V0，以及 mask6/7 返回 INVALID_ARGS；记录实际执行入口。A5 验证 AIC+AIV1 仍使用原槽位。
- [ ] **清理诊断。** 逐处审查 platform_regs.cpp 的 D0 回读、region_plan.h 的审计日志和 lane_loop.h 的 watchdog detail 写入；保留 GM 放行、退出协议及正常错误报告。检查 src 中 A6-VERIFY 已清除，重跑 MIX 4 项和完整 SWA。两个改写的 MIX kernel 另补非零输入，核对分片和写回范围。

### 3. 取得同版 A5/A6 样本

- [ ] 两端从同一 Simpler 提交重建，固定 fixture、PTO-ISA 和统计脚本；记录设备型号、工具链和运行库指纹。A5 使用 578 实例原 plan，A6 使用经过核对的 570 实例转换 plan。
- [ ] 各跑 1 次预热、10 次 L0 正式测量，保存全部样本、每轮输出校验、AICore L0 与 Device wall。先将新 A5 与 185.173 µs 的历史 A5 对照，再计算同版 A6/A5 差值。历史均值用于比较，功能通过以输出校验和正常退出为准。

### 4. 用任务记录解释差值（当前优先）

- [x] 蓝区从 A5 L4 提取三任务的计算前驱、dispatch、逐核起止、函数时长及核复用分布。
- [ ] 黄区在已有 A6 L4 上运行同一脚本，按[对照表与反馈要求](swa-l4-comparison.zh-CN.md)返回 JSON 和事件节选。
- [ ] 蓝区逐项比较 A6/A5 的前驱间隙、核内时间、启动分散和关键后继，区分可观测差异和待验证原因。
