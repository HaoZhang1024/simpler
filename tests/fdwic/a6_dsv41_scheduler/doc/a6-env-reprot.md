# A6 本机环境采集与交接信息（2026-11-17）

本文件保留 2026-11-17 A6 端采集的环境、编译结果及当时的判断。提交版将用户名、环境名和机器专属路径替换为占位符，调整 Markdown 格式；版本、数值和结论保持原记录。

**这是历史交接报告。** 原报告中关于 die 数、输入包缺失、MIX 改法的判断已有后续核对，见 [环境核对与待补信息](a6-environment.zh-CN.md)。占位符用于描述原采集位置，不是已配置的环境变量；原始输出见 [证据](a6-evidence-2026-11-17)。

## 0. 结论摘要

- 本机确认为 **A6 真机**：`SoC_version=Ascend960DT_966B7`、`Short_SoC_version=Ascend960DT`，单卡。
- CANN 9.3.0 **支持 A6 编译**。A6 的 ccec 架构名是 **`dav-920r1-cube` / `dav-920r1-vec`**；`dav-9201-*` 会被拒绝。后者宏为 `__CCE_AICORE__ 920`、`__NPU_ARCH__ 9201`，正好命中 PTO-ISA 的 `PTO_NPU_ARCH_A6`。
- 用现有 CANN + 当前 PTO-ISA 直接编译 SWA 使用的 C++ 核：19 个（源码, core_type）组合中 **17 个通过，2 个失败**。失败均为 PTO-ISA 的 A6 硬件限制（Acc→Vec dual-destination），不是工具链问题。
- Simpler 当前**没有 a6 平台**（平台表、toolchain、`src/a6` 运行时、构建检测、预检脚本都缺），这是运行前必须补的部分；与 PyPTO／PTOAS 无关。
- 生产脚本 `tests/fdwic/dsv41_scheduler/production/*` 无 `pypto`／`ptoas` 依赖，构建走 C++ → ccec。但本机**缺 SWA bundle/plan**，且只有 1 卡，无法自行完成需要 2 卡的 full-forward 捕获。
- 本机缺 `ninja`、`npu-smi`、`task-submit`（用途见下）。
- **阻塞点都有对应解法，但没有“零改动”路径**：A6 平台/运行时移植、两个 DualModeSplit 核的软件拆分、SWA 快照复用是三项必须做的事；`block_num>54` 不是阻塞（多波次），缺 `ninja` 等是易解项。真正的未知风险是 A6 HBG 运行时上机 bring-up（AICPU/拓扑常量/时序），只能实测收敛。

## 1. 必填表

### 01 芯片与执行环境

| 项目 | 结果 |
| ---- | ---- |
| 芯片型号 | `Ascend960DT_966B7`（短名 `Ascend960DT`），**真机**，非虚拟化（`is_virtual: no`） |
| 设备数量 | 1（`/dev/davinci0`；`phy_chip_id=0`、`phy_die_id=0`、`ts_num=1`） |
| Host | `x86_64`，Ubuntu 20.04.6 LTS（`/etc/os-release`） |
| AICore | 54 AIC + 54 AIV（HAL 与运行时视图一致），8 AICPU；cube 1800 MHz；L2 128 MiB；L0C 256 KiB；UB 376 KiB |
| HBM | 175.88 GiB（驱动侧保留后略低于 192 GiB） |
| 任务申请方式 | 本机未找到 `task-submit`／`npu-smi`／本地调度器包装脚本；`command -v`、`/usr/local/bin`、`${ASCEND_DRIVER_PATH}/tools`、`$ASCEND_HOME_PATH/tools` 均无。当前按直接访问设备执行，正式单卡验证仍需确认当地设备预约方式 |

设备信息的权威查询方式（只读，无需编译核、无需跑计算）：

```bash
# 已构建在 ${QUERY_BUILD}/query（源码 tools/cann-examples/query）
${QUERY_BUILD}/query device 0
```

输出关键行（节选）：`soc_name: Ascend960DT_966B7`、`short_soc_version: Ascend960DT`、`detected_arch: (unknown)`（说明仓库还没有 a6 映射）、`cube_cores 54`、`vector_cores 54`、`aicpu_cores 8`、`hbm_total 175.88 GiB`。

### 02 CANN 工具链与平台配置

| 项目 | 结果 |
| ---- | ---- |
| SDK 根目录 | `${ASCEND_HOME_PATH}`（`ASCEND_HOME_PATH` / `ASCEND_TOOLKIT_HOME` / `ASCEND_OPP_PATH` 均指向它） |
| 版本 | CN Toolkit/Ops `9.3.0`，`compiler/version.info` timestamp `20261103_000323501` |
| 环境初始化 | 该 SDK 的 `set_env.sh`（当前 shell 已加载）；用户的 `${A6_ENV_SCRIPT}` 负责 `conda activate <A6_CONDA_ENV>` + SDK 路径 |
| ccec | `$ASCEND_HOME_PATH/bin/ccec` → `tools/bisheng_compiler/bin/ccec`，clang `15.0.5`（构建时间 2026-11-02） |
| 链接器 | `tools/ccec_compiler/bin/ld.lld`，`LLD 15.0.5` |
| AICPU 交叉编译器 | `$ASCEND_HOME_PATH/tools/hcc/bin/aarch64-target-linux-gnu-g++`，`14.3.0`（Do-Compiler V100R001C30B0032） |
| 驱动 | `${ASCEND_DRIVER_PATH}`：`7.12.T0.0.B280`（timestamp `20261111_000323884`），`ascendhal 7.35.23`；`device/` 下为 `ascend960*` 镜像 |
| 匹配平台配置 | `$ASCEND_HOME_PATH/x86_64-linux/data/platform_config/Ascend960DT_966B7.ini`：`Short_SoC_version=Ascend960DT`、`CCEC_AIC_version=dav-920r1-cube`、`CCEC_VECTOR_version=dav-920r1-vec`、`core_type_list=CubeCore,VectorCore` |
| 其他 SDK | `${OTHER_SDK_ROOT}/8.2.RC1`、`${OTHER_SDK_ROOT}/cann`（旧，当前 PATH 未使用）；`${OTHER_SDK_ROOT}/latest` 指向 8.2.RC1 |

### 03 A6 编译与启动接口资料

- ccec 的 A6 架构 token（实测，见复现命令）：

```text
dav-920r1-cube  →  #define __CCE_AICORE__ 920   #define __NPU_ARCH__ 9201
dav-920r1-vec   →  #define __CCE_AICORE__ 920   #define __NPU_ARCH__ 9201
dav-9201-*      →  bisheng: error: Unsupported CCE architecture: dav-9201-*
```

- A6 宏在 PTO-ISA 中由 `__NPU_ARCH__ == 9201` 判定（见 04），因此**必须使用 `dav-920r1-*`**。
- A6 相关内核头：`$ASCEND_HOME_PATH/x86_64-linux/include`（含平台/内核接口）、`.../data/platform_config/Ascend960*.ini`（共 14 个 Ascend960 配置，其中 9 个 960DT）。
- A6 的 PTO 后端目录：`build/pto-isa/include/pto/npu/a6/`（`TLoad`、`TExtract`、`TSync`、`TQuant`、`TMatmul` 等）；**没有 `TMov.hpp`**，Acc→Vec 走 A5 实现并带 A6 静态断言（见下）。
- 启停/同步接口沿用 CANN 运行时与 Simpler 运行时层；本机尚无 Simpler 的 a6 运行时，需先适配（见第 5 节）。

### 04 PTO-ISA

| 项目 | 结果 |
| ---- | ---- |
| 路径 | `${SIMPLER_ROOT}/build/pto-isa`（由 `simpler_setup.pto_isa.ensure_pto_isa_root()` 管理，缺失时自动 clone） |
| 版本 | HEAD `83b1b2b52ded9ec5d91e02532a57cd95e497ba86`，与 `simpler/pto_isa.pin` 完全一致 |
| 工作树 | 干净（`git status --short` 无输出），无本地修改 |
| remote | `https://github.com/hw-native-sys/pto-isa.git`（HTTPS 克隆失败时有 GitCode mirror，见 `pto_isa.py`） |
| A6 架构映射 | `include/pto/common/arch_macro.hpp`：`__NPU_ARCH__ == 9201` → `PTO_NPU_ARCH_A6`，同时 `PTO_URMA_SUPPORTED`（复用 A5 通信后端） |
| A6 专用实现 | `include/pto/npu/a6/{header,TLoad,TExtract,TMatmul,TQuant,TSync,SyncAll,...}.hpp`；注释说明 A6（dav-9201）共享 A5 核 |
| A6 限制证据 | `include/pto/npu/a5/common.hpp:205`：`A6 (dav-9201) does not support dual-destination Acc->Vec moves (DualModeSplitM/DualModeSplitN); use SingleModeVec0 or a software split.`；`include/pto/npu/a5/TMov.hpp:204`：`A6 L0C2UB TMOV only supports AccToVecMode::SingleModeVec0.` |

### 05 Host 构建环境

| 项目 | 结果 |
| ---- | ---- |
| Python | conda `<A6_CONDA_ENV>`：3.11.14（torch 2.10.0+cpu，torch_npu 2.10.0.post1.dev20260930，ptyhon `simpler` 为 editable 安装指向本仓）；base 为 3.14.8（无 torch） |
| 项目 venv | 无 `.venv*` |
| C++ | `/usr/bin/g++` 9.4.0（Ubuntu 20.04） |
| CMake | `/usr/bin/cmake` 3.16.3 |
| Ninja | **未找到**（`command -v ninja` 为空；`build.sh` 默认 `-G Ninja`，需安装或改生成器） |
| CC/CXX | 均未设置 |
| 可用工作目录 | `${A6_WORKDIR}`（空间充足：`/` 98G，已用 77G，剩余 16G） |

## 2. 仓库状态

- Simpler：`${SIMPLER_ROOT}`，分支 `a6-migrate-case`，HEAD `4b2d9ca4b501c57abeea4a9dc86e0f6d08bedab4`，工作树干净。
- PTO-ISA：见 04。
- 按交接说明，本机当前不能 pull；如需更新代码，需人工同步。

## 3. A6 编译验证（用 SWA 真实核，非模拟）

验证目的：确认“工具链 + PTO-ISA 是否能编译 SWA 现有 C++ 核”，与 Simpler 平台适配无关。

方法：按 `tests/fdwic/dsv41_scheduler/production/build_sources.py` 的 include 组合（PTO-ISA、Simpler incore/runtime 头、CANN 头、vendor 目录），把 arch 换成 `dav-920r1-{vec,cube}`，逐个编译 `workloads/pypto_lib_latest/swa/tasks.tsv` 用到的（源码, core_type）。

结果：**19 个组合，17 PASS / 2 FAIL**。

通过：

```text
decode_sp_zero_padding(aiv)  _gather_sparse_vf_rows_aiv  _hc_collapse(aiv)
_hc_linear(aic)              _hc_post(aiv)               hc_rms(aiv)
_hc_sinkhorn(aiv)            norm_rope_publish(aiv)      _o_proj_a_aiv
_o_proj_b(aic)               _proj_kv(aic)               _proj_q_a(aic)
_proj_q_b_aic                _proj_q_b_aiv               qkv_quant(aiv)
q_norm_quant(aiv)            _quant_o_vf(aiv)
```

失败与根因：

| 计算核 | 源码位置 | 根因 |
| ------ | -------- | ---- |
| `_gather_sparse_vf_rows_aic` | `vendor/external/sparse_gather_vf.cpp:363`（`GetDualDstCtl<..., DualModeSplitM, ...>`）、`:483`（`TINSERT<..., DualModeSplitM>`） | PTO-ISA `a5/common.hpp:205` static_assert：A6 不支持 dual-destination Acc→Vec |
| `_o_proj_a_aic` | `vendor/external/o_proj_a.cpp:47`：`TMOV<Raw<MT>, AC<256, MT>, AccToVecMode::DualModeSplitN>` | PTO-ISA `a5/TMov.hpp:204` static_assert：A6 L0C2UB 只支持 `SingleModeVec0` |

复现命令（只写 `/tmp`，不改仓库）：

```bash
C=$ASCEND_HOME_PATH/bin/ccec
S=${SIMPLER_ROOT}
D=$S/tests/fdwic/dsv41_scheduler/kernels/pypto_lib_latest
P=$S/build/pto-isa
I=""
for d in $P/include $P/include/pto $S/simpler_setup/incore \
         $S/src/common/platform/include $S/src/a5/runtime \
         $S/src/a5/runtime/host_build_graph/runtime $S/src/a5/runtime/host_build_graph/common \
         $S/src/common/task_interface $S/src/common $S/src/a5/platform/include $S/src/common/host_build_graph \
         $D/vendor $D/vendor/aic $D/vendor/aiv $D/vendor/external \
         $ASCEND_HOME_PATH/include $ASCEND_HOME_PATH/x86_64-linux/include \
         $ASCEND_HOME_PATH/asc/include $ASCEND_HOME_PATH/asc/include/interface $ASCEND_HOME_PATH/asc/include/basic_api \
         $ASCEND_HOME_PATH/x86_64-linux/asc/include $ASCEND_HOME_PATH/x86_64-linux/asc/include/interface \
         $ASCEND_HOME_PATH/x86_64-linux/asc/include/basic_api \
         $ASCEND_HOME_PATH/x86_64-linux/ascendc/include $ASCEND_HOME_PATH/x86_64-linux/ascendc/include/basic_api \
         $ASCEND_HOME_PATH/x86_64-linux/asc/impl/basic_api; do I="$I -I$d"; done

$C -c -O3 -x cce -std=c++17 --cce-aicore-only --cce-aicore-arch=dav-920r1-vec \
   -mllvm -cce-aicore-stack-size=0x8000 -mllvm -cce-aicore-function-stack-size=0x8000 \
   -mllvm -cce-aicore-record-overflow=false -mllvm -cce-aicore-addr-transform \
   -mllvm -cce-aicore-dcci-insert-for-scalar=false -DMEMORY_BASE $I \
   $D/vendor/external/hc_collapse.cpp -o ${A6_COMPILE_LOG_DIR}/hc_collapse.o
# AIC 核把 --cce-aicore-arch 换成 dav-920r1-cube
```

注意：上面用的是 `src/a5/runtime` 头（A6 还没有 `src/a6`），仅用于证明**核源码可编译**；正式构建必须换成 A6 运行时头，否则不能说明运行兼容。

A5 专属的两个编译 flag 在 A6 上已实测，结论是**都保留**：

- `-fno-jump-tables`：**必须保留**，且原因与芯片无关。Simpler 的 callable 是 text-only 格式：`simpler_setup/elf_parser.py` 只取 `.text` 并在 `kernel_entry` 起跳，明确拒绝 `.text` 外的已分配 `.rodata`（含已重定位的 jump table）。实测同一 switch 代码：加该 flag 时无 `.rodata`；不加时生成 `.rodata` 中的 `switch.table.k`，会被加载器拒绝。
- `-mllvm -cce-vf-aa-between-iters=true`：ccec（clang 15.0.5）在 `dav-920r1-*` 下接受该选项；对 `hc_collapse`、`qkv_quant`、`hc_post`、`hc_rms` 四个 SWA AIV 核，加/不加该 flag 生成的 `.text` 字节完全一致（no-op）。A5 上它是为约束 BiSheng VF fusion 的正确性而 pin 的，A6 用同一编译器，保留即可。
- 剩余“需实测”的只有**运行时行为/性能**（例如 A6 上波次数量、VF fusion 后的数值与耗时），这些无法由头文件或编译结果推断，只能等 a6 运行时适配完成上机验证。

## 4. 其他对 SWA 迁移重要的实测约束

- **block 数不是阻塞点，但拓扑常量要适配**：SWA 的 AIC 最大 `block_num=32`；AIV 有 3 个任务为 `decode_sp_zero_padding=80`、`_quant_o_vf=64`、`_hc_post=64`。A5 的编译期上限是 `MAX_BLOCKDIM=36`、每 block 1 AIC + 2 AIV（即 36 AIC / 72 AIV），80 已经超过 A5 的 72 AIV，说明基线本来就是多波次（HBG 文档：`Dynamic ownership, multiple waves`，保留原 block 数）。A6 实测 54 AIC / 54 AIV，多波次仍然成立，只是波次更多、耗时会变；需要按 A6 拓扑改 `PLATFORM_MAX_*`（A5 硬编码 36/1+2），并确认 A6 的 AIC:AIV 集群映射（query 报 54/54、2 dies）。
- **单卡 vs 准备全流程**：SWA 切片本身是 `ranks=1`、无 `COMM`、无通信上下文，**单卡可跑**（`topology.py` 要求 `rank0.txt` 声明 1 rank + snapshot）；两卡只出现在 `production/prepare.py` 的全量 forward（EP2）和 MoE 用例。本机只有 1 张卡，因此**本机无法自行生成 SWA bundle（plan/输入快照/参考输出）**，需要复用其他机器已准备的快照，或按 CSA fixture 方式另行冻结数据。
- 本机未见 `a6sim`，只有 a6 真机路径。
- `query` 输出里 `detected_arch: (unknown)`，说明 `tools/cann-examples/query` 的 arch 映射也要补 a6（否则预检提示不准）。
- A6 平台配置的 `AIC_version=AIC-C-310`，与 A5 同属 AIC-C-310 系列（A6 ISA 为 920），与 PTO-ISA“A6 共享 A5 核”的说明一致，可作为运行时移植依据。

## 5. Simpler 侧需要适配的位置（给做适配的机器）

按“能在 a6 上建 HBG 图 + 调度 + 校验”的最小改动面：

1. `simpler_setup/platform_info.py`：`PLATFORM_MAP`、`ARCHS`、`parse_platform`／`to_platform` 增加 `a6`（是否需要 `a6sim` 另定）。
2. `simpler_setup/toolchain.py`：`CCECToolchain.get_compile_flags` 增加 a6 → `dav-920r1-cube/vec`。A5 的两个 flag 已在 A6 上验过（见第 3 节末尾）：**两个都保留**，`-fno-jump-tables` 是 text-only 加载格式的硬要求，`-cce-vf-aa-between-iters=true` 对 SWA 核是 no-op 且被 ccec 接受。
3. `src/a6/`：目前只有 `src/a2a3`、`src/a5`、`src/wse`。A6 的 platform/runtime 未落地；PTO-ISA 注释称 A6 复用 A5 核与通信后端，可作为移植起点。
4. `simpler_setup/build_runtimes.py`：`detect_buildable_platforms` 只返回 a2a3/a5（+sim），需加 a6。
5. `.claude/skills/onboard-arch-precheck/check.sh`：只接受 a2a3/a5，A6 会被判 mismatch/unknown；需先补 a6 识别（`Short_SoC_version=Ascend960DT`）。
6. `tests/fdwic/dsv41_scheduler/` 内硬编码：`production/build_sources.py:43,74,180`（`KernelCompiler("a5")`、`"platform": "a5"`）、`tmr_prepare.py`、`prepare.py`、`run.sh:39`（`check.sh a5`）。
7. `simpler_setup` 的预编译资产 `simpler_setup/_assets/build/lib/a5/...`：运行时 `.so` 只有 a2a3/a5，需要 a6 资产或从源码重建。
8. `tools/cann-examples/query`：arch 映射增加 Ascend960DT → a6。

## 6. SWA 材料与缺失项（本机）

已有：

- 任务/边：`workloads/pypto_lib_latest/swa/tasks.tsv`（16 tasks、578 executions）、`swa/edges.tsv`（17 edges、45 incoming）；总表 `workloads/pypto_lib_latest/source.json`。
- 已保存 C++ 核：`kernels/pypto_lib_latest/vendor/**`（`manifest.json`：82 kernels，含 `func_id/name/source/core_type/signature/source_sha256`）。
- 原始 Host 编排源码：`workloads/pypto_lib_latest/vendor/orchestration.cpp.gz`（6272 行，`aicpu_orchestration_entry`，100 个外部 tensor、13 个 scalar、动态 `get_tensor_data`）。
- 全量初始数据：`workloads/pypto_lib_latest/inputs/{metadata.json,rank0.txt,rank1.txt,vendor/data/*.bin}`（2 rank，100 参数，含 `initializer_mode` 与 SHA256）。

缺失（本机）：

- `tests/fdwic/dsv41_scheduler/build/`（未构建，无 `build/portable/host/native-runner`）。
- `outputs/`、SWA bundle（`callable.bin`、`plan-rank0.bin`、`slice.txt`、rank0.txt 快照、reference 输出）。
- 因此本机无法直接 `run.sh` 跑 SWA；这不是 pypto 依赖问题，而是“B/C 产物未生成”。

## 7. 是否必须依赖 PyPTO／PTOAS

- `tests/fdwic/dsv41_scheduler/production/*.py` 与 `export_workloads.py` 中**没有** `import pypto` / `from pypto` / `ptoas` 调用；构建路径是 C++ → ccec，运行是 native-runner + replay。
- 环境里装了 `pypto 0.3.0`、`ptoas 0.72`，但按上述代码不参与本流程。
- 结论：**可以在不调用 PyPTO／PTOAS 的前提下构建和运行**；真正的前置条件是（a）A6 平台/运行时适配，（b）SWA 的 plan 与输入/参考快照（C 步骤）已就绪。

## 8. 建议的下一步

1. 先补 Simpler 的 a6 平台与运行时（第 5 节），用 `dav-920r1-*` 作为编译架构；本机的 17 个可编译核已证明工具链可用。
2. 决策两个 AIC 核的 `DualModeSplit`：改 `SingleModeVec0` + 软件拆分，或提供 A6 等价实现；这是 SWA 能否“原样”迁移的唯一代码级硬限制。
3. 保留 3 个 AIV 任务的原始 `block_num`（80/64/64），按多波次运行；在 A6 上记录实际波次与耗时，作为性能口径差异单独说明。
4. SWA 的 plan/输入快照：复用其他机器的 2 卡捕获，或按 `examples/a5/host_build_graph/deepseek_v4_pro_csa` 的冻结 fixture 方式在本机重建数据。
5. 本机补 `ninja`（或改 `build.sh` 的 CMake 生成器），并确认单卡设备申请方式（当前无 `task-submit`/`npu-smi`）。

## 9. 阻塞点分级与解决路径

| 编号 | 事项 | 是否阻塞 | 解决路径 | 剩余风险 / 代价 |
| ---- | ---- | -------- | -------- | --------------- |
| P1 | Simpler 无 a6 平台与运行时（`platform_info`、`toolchain`、`src/a6`、`build_runtimes`、预检、`_assets`） | **硬阻塞**（不解决无法建图/启动） | 按第 5 节补平台名与 `dav-920r1-*`；`src/a6` 以 `src/a5` 为起点（A6 的 `AIC_version=AIC-C-310`、PTO-ISA 说明 A6 复用 A5 核与通信后端）；按 A6 的 54 AIC / 54 AIV / 8 AICPU 改 `PLATFORM_MAX_*`，不要沿用 A5 的 36/1+2 | 工作量主要在 AICPU/HBG 上机 bring-up；属工程可解，无架构性未知 |
| P2 | `_gather_sparse_vf_rows_aic`、`_o_proj_a_aic` 使用 Acc→Vec `DualModeSplitM/N` | **硬阻塞**（这 2 个 AIC 任务无法按原码编译） | 改软件拆分：用 `SingleModeVec0` 分成两半（或 `TEXTRACT` 路径）；PTO-ISA 在 `a6/TDeInterleave.hpp`、`TInterleave.hpp` 已有“把 dual-output 指令拆成 per-half 调用”的先例可参照 | 需改核 + 重验数值；这两个任务由一次 dual move 变两次 move，会影响其耗时，性能对比要单独记录口径 |
| P3 | 本机无 SWA bundle/plan/输入快照/参考输出 | **阻塞执行**（不阻塞编译） | 优先级：① 复用已准备机器的 SWA bundle；② 在 2 卡机器重跑 `prepare.py` 生成；③ 参考 `examples/a5/host_build_graph/deepseek_v4_pro_csa` 冻结 fixture 重建（数据量大、需推导切片 ABI，成本最高） | 本机单卡无法做 2 rank full-forward；若选 ③ 需确认切片边界中间张量来源 |
| P4 | 本机缺 `ninja`、`npu-smi`、`task-submit` | 非设计阻塞 | 安装 ninja 或把 `build.sh` 改为 Makefiles 生成器；设备信息用 `tools/cann-examples/query`；单卡设备申请方式需向当地确认 | 易解，但验证前必须落实设备预约方式 |
| P5 | AIV `block_num` 80/64/64 > A6 的 54 AIV | **不阻塞** | HBG 已支持多波次（`Dynamic ownership, multiple waves`），保留原 block 数即可；A5 72 AIV 时 80 已在多波次运行 | A6 波次更多、该任务耗时变长；需按 A6 拓扑改常量并确认 AIC:AIV 映射 |
| P6 | `query` 报 `detected_arch: (unknown)`、预检脚本只认 a2a3/a5 | 非运行阻塞 | 补 arch 映射和 `check.sh` 的 Ascend960DT 识别 | 只影响预检体验，可与 P1 一起做 |

## 10. 证据与附件位置

- 原始输出汇总：`environment/evidence-20261117.txt`（设备查询、CANN/驱动版本、架构宏、平台配置、仓库版本、工具版本、缺失工具）。
- 设备查询：`${QUERY_BUILD}/query`（由 `tools/cann-examples/query` 构建），`${QUERY_BUILD}/query device 0` 输出。
- A6 编译验证日志与目标文件：`${A6_COMPILE_LOG_DIR}/`（`build.sh`、`*.log`、`*.o`）。
- CANN/驱动版本：`$ASCEND_HOME_PATH/compiler/version.info`、`$ASCEND_HOME_PATH/opp/version.info`、`${ASCEND_DRIVER_PATH}/version.info`。
- 平台配置：`$ASCEND_HOME_PATH/x86_64-linux/data/platform_config/Ascend960DT_966B7.ini`。
- PTO-ISA：`${SIMPLER_ROOT}/build/pto-isa`（HEAD 与 `pto_isa.pin` 一致）。
