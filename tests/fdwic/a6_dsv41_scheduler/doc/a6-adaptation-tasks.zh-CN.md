# A6 SWA 后续适配任务

[返回索引](../README.zh-CN.md) · [现有迁移分析](a6-migration.zh-CN.md) · [现场接口问题](a6-environment.zh-CN.md)

## 基础与目标

以同事分支 2026-11-17 的交接提交 `6715d0b0221dcd5c00c0d10d27d07b19e4a3e013` 为基础，复用独立 SWA、固定夹具、两个 MIX 核适配和 A5 结果。原方案的首个里程碑仍是 A6 单卡 HBG；后续完成生产 percounter 的同用例功能验证，性能调优另行开展。

已归档证据：A5 HBG/percounter 各 11 轮校验通过；A6 目标的 19 个 kernel 注册通过本地编译、链接与机器码提取；原 plan 的 2735 条记录在本地解码一致，转换后 SWA 为 16 个任务、570 个物理执行实例。上述 A6 证据为离线检查，设备验证由黄区执行。

## 实施总表

| 步骤 | 交付内容 | 前置条件 | 分工 | 验收 |
| --- | --- | --- | --- | --- |
| 1. 构建与接口准备 | A6 平台入口、构建清单、Q1–Q5 接口依据、目标 Host 的 plan 检查 | 固定源码、PTO-ISA、夹具和现场 SDK | 蓝区做代码；黄区补接口资料及现场检查 | 工具链与目标身份明确，plan 语义一致，平台常量有来源 |
| 2. 最小平台与 HBG | Host/AICPU/AICore/dispatcher 成套构建及启动链 | 步骤 1 的核映射、寄存器、SSBUF 和启动依据 | 蓝区实现；黄区执行基础用例 | AIV、AIC、依赖链、MIX/同步任务和重复启停通过 |
| 3. 完整 SWA | A6 组包、两个 MIX 核功能检查、单卡运行与原参考比较 | HBG 可执行；目标 kernel 和转换 plan 可用 | 蓝区接入口；黄区验证 | 16 个任务完整执行，输出通过，正常退出；留存实际执行记录 |
| 4. percounter | A6 资源排列、SSBUF、领取/完成协议和运行入口 | 共享平台已验证；SWA 输入与参考固定 | 蓝区实现；黄区同输入对照 | 与 HBG 输出一致，MIX、sync_start、多波次与重复运行通过 |
| 5. 交付与回归 | 可重复的环境检查、定向构建、运行命令及结果包 | 对应运行时功能通过 | 蓝区整理入口；黄区从新构建目录复现 | 版本、构建、输出、退出状态可追溯；A5 受影响路径回归通过 |

```text
固定源码与夹具
  ├─ 黄区：返回 Q1–Q4 平台接口依据 ──→ 平台启动与 HBG 基础验证
  ├─ 蓝区：补齐构建入口 ──────────────↗             │
  ├─ 黄区：Host plan 核验、目标 kernel 编译 ─────────┤
  └─ 蓝区：准备 MIX 功能检查与组包入口 ─────────────┤
                                                   ↓
                                             A6 HBG 完整 SWA
                                                   ↓
                                             A6 percounter SWA
                                                   ↓
                                             固定交付与回归

Q5 计时依据 → 超时单位核验与后续性能统计
```

## 1. 构建与接口准备

### 蓝区任务

- 核对 `simpler_setup/platform_info.py` 的 `PLATFORM_MAP`、`ARCHS` 和 runtime discovery，形成 A6 的正式平台入口。
- 沿 `simpler_setup/toolchain.py`、`build_runtimes.py`、`runtime_builder.py`、`kernel_compiler.py` 接通完整构建路径。已有 A6 CCEC 目标为 `dav-920r1-cube/vec`；还需分别选择 x86_64 Host 编译器和 aarch64 AICPU 交叉工具链，并审查 runtime builder 的架构分支及 workspace 设置。
- 列出生产 HBG、dispatcher、必要平台库、native-runner、replay 和 SWA 19 个注册的构建目标。按实际发现机制选择 A6 平台目录与共享源码引用，集中保存硬件差异。
- 为缓存记录目标平台、源码、编译器、编译参数和 PTO-ISA 身份。将 runtime、Host 工具、kernel、plan 和 callable 组包分别作为可重建单元。

### 黄区任务

- 按既有 Q1–Q5 返回核编号、寄存器窗口、SSBUF、联合启动样例与计时接口的依据；优先查找已有 A6 Simpler 平台实现。
- 确认现场源码同步方式。现有报告记录当时暂不能 pull，可先验证 GitHub 下载或采用固定版本离线包。
- 使用项目环境补齐 CMake、Ninja 和 Python 构建依赖；保留现场 CANN/驱动版本。
- 在 x86_64 Host 运行 `prepare_plan.py`，核对 2735 条原记录、两处转换和 570 个实例；用现场 SDK 执行 `compile_kernels.py --platform a6`，保存逐核编译、链接与提取结果。

产物为平台接口答复、目标 Host plan 检查报告、19 个注册的现场构建报告和依赖清单。

## 2. 最小平台与 HBG

| 代码位置 | 适配任务 | 主要验收 |
| --- | --- | --- |
| `src/a5/platform/onboard/host/host_regs.cpp` 对应的平台能力 | 建立驱动资源 ID、物理核、逻辑 C/V 对和寄存器窗口的对应关系 | 可用核及屏蔽核处理正确，映射与现场资料一致 |
| `src/a5/platform/include/common/platform_config.h` 对应的平台配置 | 根据 A6 依据定义容量、lane 数、寄存器与 SSBUF 参数 | 配置、数组容量和索引边界相互一致 |
| 平台 Host/AICPU/AICore 入口与 dispatcher | 接通加载、READY/执行/完成/EXIT，核验参数 ABI 和内存可见性 | 普通 AIV、AIC 正常执行，连续调用和重新创建 Worker 正常 |
| HBG `scheduler_cluster_mix.h`、`scheduler_cluster_signal.h` | 核对 1C1V 的参与者、通知、完成与 SSBUF 布局 | C/V 都完成后再发布任务完成，下一轮状态正确 |
| 架构预检与设备选择入口 | 识别现场 Ascend960DT，支持黄区约定的单卡占用方式 | 运行记录包含实际设备和平台，超时失败能退出并留日志 |

基础用例从现有 HBG `vector_example`、`sync_start_capacity`、`spmd_sync_start_mix_aiv` 等测试提取相应验证场景。验收包括：AIV 链、AIC 写回、跨任务依赖、1C1V MIX、sync_start、逻辑 block 超过物理核数的多波次执行，以及重复运行后的状态复位。

## 3. 完整 SWA 与 MIX 功能

- `prepare.py`：当前 `--platform` 仅接受 A5，扩展到 A6 后调用已验证的 kernel 编译与 plan 转换，并按目标架构生成 assembly 与 callable。保留原始 fixture。
- `production/CMakeLists.txt`：梳理 A5 HBG include 和平台目录选择，确保 native-runner、replay、record-tool 与目标运行时使用同版本接口。
- `run.py`、`production/run.sh`：参数化平台、运行库目录和预检，接入黄区设备使用方式；计时、超时、异常退出使用对应平台规则。
- `sparse_gather_vf.cpp`：验证两个 1C1V block 分别覆盖前后半 head；检查 token/partial 槽位、重复 KV gather、UB 使用和事件同步。
- `o_proj_a.cpp`：验证单 V 消费与内部列循环，核对量化、输出偏移及 READY/RELEASE/STORE_DONE 完成顺序。
- 补充建议：为两组 MIX 核准备能区分前后半 head/列的非零小样本，帮助发现漏算、重复写回或偏移错误；完整 SWA 继续使用现有固定夹具和 30 个可写 Device buffer 检查。

原 plan 的 578→570 变化来自 t22 的 72→96 与 t28 的 96→64。验收既检查实例数，也检查每部分计算和写回范围。保留实际任务、block、lane 完成记录，诊断运行与正常验收运行分别记录。

## 4. percounter 适配

HBG 跑通后复用其已验证的平台启动、Host 编排和 AICPU 生命周期，再接通 percounter 独立的任务映像与 lane loop。

| 代码位置 | 已确认的适配点 | 验收重点 |
| --- | --- | --- |
| `src/a5/runtime/percounter/build_config.py` | 当前声明架构独占，引用同架构 HBG 与 common 源码 | A6 选择正确源码及 include 顺序，生成独立运行库 |
| `host/resource_order.h` | worker 编号及资源恢复使用 `cluster * 3`、`worker / 3`、`worker % 3`，并遍历 3 lane | 1C1V 下资源分配、恢复、任务排序及数组容量一致 |
| `runtime/scheduler/ssbuf.h` | 当前使用偏移 2 KiB、大小 1 KiB 的 A5 cluster 区域 | A6 共享范围、容量、访问屏障和发布顺序有依据 |
| `aicore/lane_loop.h`、`runtime/scheduler/wire_types.h` | 领取、参数发布、参与 mask、组内会合、完成及代际复用 | 每个 block 正好执行一次，全部参与者完成后才释放依赖 |
| `runtime/scheduler/gm.h`、`async_completion.h` | GM 原子、完成计数和可见性 | 生产者完成与消费者就绪顺序正确，重复运行无遗留计数 |
| `host/image/image_pack.h`、`runtime/task_image_layout.h`、`aicpu/graph_prepare.h` | Host 打包、AICPU 物化和 AICore 读取的数据契约 | 同一任务各端解码一致，保留标量、Tensor 和同步属性 |

验收先覆盖普通依赖链、MIX、sync_start 和多波次，再用完整 SWA 与 HBG 同输入对照。现有 acquire/cohort 测试可复用其语义；A6 用例按实际资源容量设置参数。

2026-11-17 查询到主仓相关开放 PR：[#3151](https://github.com/hw-native-sys/simpler/pull/3151) 修改完成观察，[#3149](https://github.com/hw-native-sys/simpler/pull/3149) 修改参数预打包和 SSBUF，[#3108](https://github.com/hw-native-sys/simpler/pull/3108) 修改 MIX 准备重叠，另有原始 percounter PR [#2814](https://github.com/hw-native-sys/simpler/pull/2814)。开始 percounter 实现前重新核对状态和实际差异，选定一次集成基线；设备对照使用同一版本。

## 5. 交付与增量构建

| 修改内容 | 需要重建或重做 |
| --- | --- |
| 单个 SWA kernel 或其本地头文件 | 受影响的 AIC/AIV 编译目标，随后重新组装 callable |
| plan 适配规则 | plan 转换与语义检查，随后重新组包 |
| Host replay 或 Tensor/参数 ABI | Host 工具及依赖组件，重新核验 plan 并组包 |
| HBG/percounter 调度或平台接口 | 受影响运行时组件、dispatcher 及共享依赖，重新执行对应基础检查 |
| 输入或参考 | 更新数据清单与覆盖检查，重新做完整输出校验 |
| 编译器、PTO-ISA 或平台版本 | 按身份失效相关缓存，重新验证目标组件 |

主仓交付建议分为：SWA 独立用例、A6 平台与基础 HBG、A6 SWA 功能、A6 percounter。每项提交包含对应验证证据；实际边界以可独立构建和审阅为准。黄区每次同步一个确定的源码与数据版本，保留命令、环境、构建日志、输出校验和退出状态。

当前可直接推进构建入口梳理、目标 Host ABI 检查和 MIX 验证准备。平台映射与 SSBUF 的具体实现依赖 Q1–Q4；计时换算依赖 Q5。功能通过后再安排 A5/A6 及 HBG/percounter 性能对比。
