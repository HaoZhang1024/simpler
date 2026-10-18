# Kernel 模式 callable 缓存调用链

本文说明当前集成代码的 callable 准备、驻留、执行和释放流程。
公开接口以 [runtime_c_api.h](../../src/common/worker/runtime_c_api.h) 为准。

## 1. 支持范围与调用顺序

| 构件 | Kernel 模式状态 |
| ---- | --------------- |
| a2a3 / a5 onboard 的 tensormap_and_ringbuffer（TMR） | 支持 init、prepare 和异步 launch，能力查询返回 1 |
| host_build_graph（HBG） | H1-H3 内部能力已集成；H4 尚未提交，公开 init 返回 `UNSUPPORTED`，能力查询返回 0 |
| sim | 公开 kernel init 返回 `UNSUPPORTED` |

HBG 和 sim 的不支持判定发生在取得 kernel 身份之前。在这种未取得身份的 context 上，
结构合法的 prepare / launch 返回 `INVALID_STATE`。能力查询不替代 context 初始化或生命周期检查。

调用者先完成 ACL 初始化，并让当前线程持有所需设备。Kernel init 借用这个设备，
不调用选卡、设备重置或 ACL 初始化/终止接口。init 必须在 capture 之外完成，
它会同步 context 自己的 AICPU stream；prepare 和 launch 都不做 stream/device 同步，
因此 prepare 可以在 capture 内调用。
调用者负责串行执行同一 context 的 init、prepare、launch 和 finalize。
Kernel 当前不支持 PMU、参数 dump、scope stats 和 clock anchors；相应配置在认领 context
和设备入队之前返回 `UNSUPPORTED`。该拒绝路径不等同于 Program/Worker 的 PMU 故障处理。

```cpp
int simpler_kernel_mode_prepare_callable(
    DeviceContextHandle ctx, const void *callable,
    size_t callable_size, int32_t *out_callable_id);

int simpler_kernel_mode_launch(
    DeviceContextHandle ctx, int32_t callable_id, const void *args, void *caller_stream);
```

`callable` 是未修补设备地址的完整 `ChipCallable` 镜像，包括 header、orchestration SO
和子 `CoreCallable`。`callable_size` 必须等于实际大小。prepare 不接收 tensor 实参，
也不执行算子，也不接收 caller stream：注册发在 context 自己的 AICPU stream 上，
后续 launch 发在同一条流上，FIFO 已经承接注册顺序。

ID 由 simpler 铸造：成功时通过出参返回 `[0, MAX_REGISTERED_CALLABLE_IDS)` 内的
context-local `int32_t`，失败写 `-1`。当前上限为 8192。

```cpp
// 已完成 caller 的 ACL 初始化、选卡以及 simpler_kernel_mode_init。
int32_t callable_id = -1;
int rc = simpler_kernel_mode_prepare_callable(ctx, callable, size, &callable_id);
if (rc != 0) return rc;
// prepare 已同步 context 自己的 AICPU stream，rc 即注册结果；以下是调用者为 capture 做的 warmup 和同步。
rc = caller_warmup_and_synchronize(caller_stream); // 调用者自己的逻辑
if (rc != 0) return rc;
return simpler_kernel_mode_launch(ctx, callable_id, args, caller_stream);
```

注册是纯注册，不做去重也不提供 lookup：相同镜像注册两次得到两个不同且都有效的 ID、
两次上传和两份计费。成功驻留的 ID 在 close 前不删除、不换出、不复用，close 之后
整体失效。ID 不带 generation —— "同一 context 内不复用" 加上 "close 后整体失效"
加上 Worker 的 CLOSED 吸收态拒绝后续 launch，这三条一起取代了版本字段的作用。

init、prepare、launch、finalize 只读核对当前线程的设备身份，不替调用者选卡。
prepare / launch / finalize 查询设备失败时原样返回查询错误；设备不匹配时返回
`INVALID_STATE`。这些提前拒绝不改变驻留内容，也不把 context 标为 Poisoned；
调用者恢复正确设备后可以继续使用。

## 2. 缓存准入和上传

每个 `DeviceRunnerBase` 拥有一份
[KernelCallableCache](../../src/common/platform/include/host/kernel_callable_cache.h)。
`stage` 校验镜像大小、signature、名称、子项布局和子函数 ID（超出
`[0, KERNEL_MAX_FUNC_ID)` 或在同一镜像内重复即拒绝），拒绝存在未完成准备的
条目，再检查数量/字节预算，然后铸造下一个 ID。

| 情况 | 行为 |
| ---- | ---- |
| 新注册，当前有块装得下 | 铸造下一个 ID，在该块内追加，修补私有副本并上传 |
| 新注册，没有块装得下 | 再申请一块（见下），装不下则拒绝 |
| 数量或字节预算超限 | 拒绝候选，出参写 `-1`，保留已有 ready 条目 |
| 存在未 ready 的条目 | 拒绝后续 stage，防止暴露未完成准备的资源 |

代码预算为 2 GiB；每次注册按 `align_up(callable_size, 64)` 计费，包含整个
`ChipCallable`——预算按注册次数消耗，不按不同镜像数消耗。

设备内存按块申请、按需增长，不在首次注册就占满预算：

```text
blocks_（每块的底层分配由 MemoryAllocator 持有）
├── block[0]：max(charged, 2 MiB)
├── block[1]：同上，前序块都装不下时才申请
└── ...                                   Σ block.capacity ≤ 2 GiB
    └── device_address = block.address + block.used
```

单个注册大于 2 MiB 时该块按 `charged` 精确申请，已有块的剩余空间仍可被后续小镜像
用掉。块的剩余量（slack）计入 `allocated_bytes()`，所以它对着 2 GiB 预算计费，而
`resident_bytes()` 只算实际收费的镜像字节。已发布的 `device_address` 在增长时不移动。

数量上限和字节预算哪个先到，取决于镜像大小 —— 分界点正好在 256 KiB：2 GiB / 8192
= 256 KiB。小于它数量先到（`sizeof(ChipCallable)` 是 9376 字节，8192 个只占
73.5 MiB），大于它字节先到（1 MiB 量级的镜像 2048 个就用满预算）。两个上限都会返回
各自的错误码（`CALLABLE_COUNT_EXCEEDED` / `CALLABLE_BYTES_EXCEEDED`）。

上传只修补临时 `scratch` 中的子 `CoreCallable::resolved_addr_`，调用者镜像保持不变。
缓存上传通过 `Ops.copy → capture_memcpy_h2d` 同步复制：先用
`aclmdlRICaptureThreadExchangeMode` 把本线程的 capture 模式临时切到
`ACL_MODEL_RI_CAPTURE_MODE_RELAXED`，再调用同步 `aclrtMemcpy`，随后恢复原模式；
拷贝失败也照样恢复，切换或恢复失败按错误返回。这条拷贝立即执行、不进 graph，
它的设备分配一直活到 close，所以临时 `scratch` 可以在返回后释放。
Runtime、`KernelArgs` 和 AICore 寄存器地址表的上传走同一个函数。
随后的设备注册是异步下发，prepare 不等它完成。

Host 条目保存驻留信息、镜像副本、计费字节数和 `ready`。
`resident_count()` 只统计 ready 项，`resident_bytes()` 包括未 commit 的计费占用。
`host_bytes()` 是代码内容的计量，不是这些容器和镜像副本的实际进程内存总量。

## 3. Runtime 注册和准备完成的顺序

stage 成功后，`record_callable_on_runner` 生成 orchestration 信息和
子 `func_id → 设备代码地址` 映射。Kernel 路径从缓存取得已上传地址，不重复上传代码；
program 模式继续使用原有上传与引用计数路径。

TMR 的 `prepare_kernel_callable` 首次配置固定 runtime 区域、准备 `PersistentKernelArgs`，
随后冻结配置。每个 callable 在此分配 Host dispatch packet 缓冲区，launch 只重写内容。

prepare 不再为单个 callable 下发任何 AICPU 任务：设备从**第一个点名该 callable 的 launch 包**
得知它的存在——包里带着同一段镜像地址与长度，dispatch 据此建立驻留，编排 SO 则由该 callable
第一次 launch 的轮次 leader 装载（`prepare_kernel_round`）；
其前的 `prepare_kernel_coordination` 在同一条流上发射 `simpler_aicpu_prepare_tmr_context`
交接 context 描述符。每次 launch 也把 AICPU 任务发在同一条流上，FIFO 因此保证两者都
排在每次 launch 之前，不需要事件，prepare 也不接触 caller stream。prepare 不同步任何
stream，也不做 device synchronize：返回 0 表示镜像已上传、注册任务已被接受下发，
不表示设备已经 dlopen 成功。编排 SO 无法装载这类失败，在该 callable 第一次 launch 时才暴露。
program 模式仍走带同步的 `register_callable_on_device`，它的注册失败仍是注册调用自己的状态。

context 随后转为 `ReadyEnqueued`，缓存通过 `commit(callable_id)` 发布 ready 条目。
ready 表示注册已下发并由同一条 AICPU stream 承接顺序。
调用者仍须在自己 warmup 并同步时检查异步准备结果。

HBG 内部准备包含资源计划、freeze 和 execution-slot 注册；公开 HBG init 已提前拒绝，
不能通过公开 prepare 绕过 H4 缺失的限制。详见
[HBG 资源契约](../host-build-graph-kernel-contract.md)和
[HBG 槽位准入](../host-build-graph-kernel-slot.md)。

## 4. Launch 和设备端检查

当前 TMR 的 Host 链路为：

```text
simpler_kernel_mode_launch(ctx, callable_id, args, caller_stream)
  ├─ 校验参数、kernel 身份和 context 状态
  ├─ 取得提交锁，核对设备及 context 的执行占用权
  ├─ cache.resolve(callable_id, residency)
  ├─ 将 tensor 元数据、设备地址和 scalar 编入已分配的 dispatch packet
  └─ launch_bound_kernel：caller → 专用 AICPU → 隐藏 AICore，再逐跳汇合回 caller
```

`args` 指向真实 `ChipStorageTaskArgs`，tensor 必须声明为设备地址空间。Host 只读取元数据，
不解引用或上传 tensor 内容。每次 launch 编码当前实参；CANN 接管调用包快照后，
调用者可复用 Host 参数对象，tensor 和 context 资源仍须保持到设备工作完成。

binder 使用三条 stream 和五个 event，链式串联 caller ⇄ AICPU ⇄ AICore：caller 与
AICore 之间没有直接 event 边，capture 分两跳传播。Host 提交顺序上仍是先 AICore 再
AICPU，避免启动相互等待。
launch 不分配设备内存、不创建 stream/event、不同步、不查询 capture 状态。
返回 0 表示提交成功，最终数值和异步错误须由调用者同步后检查。

设备包是 [SimplerKernelDispatchArgs](../../src/common/task_interface/kernel_dispatch_args.h)
加 runtime payload。前缀包含包长、本次 callable 的设备镜像地址与长度、context 的
`KernelArgs` 地址和 context generation、SM/arena 范围及 `SimplerKernelInvocationHeader`。
镜像地址由 binder 从本 context 已提交的驻留信息填入，不来自调用方镜像；该分配在每个
引用它的图销毁前不释放。公共 invocation header 固定为 32 字节，不带 callable generation
字段；`host_copy_tensor_count` 仅为保持 wire 布局而保留，所有 runtime 都要求它为零；
所有 runtime 也要求显式 `reserved_` 为零。HBG Host 构图需要的值须通过非 Tensor 参数传入，
不会编码尾随的 host-only Tensor 副本。

设备入口先检查公共 framing 和镜像跨度（非零、对齐、不小于 `sizeof(ChipCallable)`、
不溢出），再由 TMR consumer 建立缓存可见性并校验绑定、大小、参数数量和
signature，解码到本次调用的私有参数，进入真实 executor。
两个入口将不同形式的参数适配为 `ExecutionInputs`，随后共同调用 `AicpuExecutor::execute()`，
内部的 `init()`、`run()`、初始化计数、就绪发布、逐 scheduler 退核和完成协调只有一套。Kernel admission leader 额外完成
callable 驻留、orch SO 加载和参数绑定，再调用公共 `prepare_execution()`；program 的初始化
leader 调用同一个准备函数。`KernelRoundGate` 只负责准入、线程筛选、最终结果和全部线程退场，
不再维护初始化屏障或完成回调。

准入按 launch index 的连续已发布前缀检查 CPU 报告；请求的角色全部精确匹配后即可放行，
不必等待剩余线程。尚未发布的低 index slot 仍须等待，避免错过更早的同 CPU 报告。
若精确匹配不足，则等全部线程报告后按原有顺序 fallback。晚到线程作为 filtered participant
继续参与最终结果和退场，全部 launched 线程退出前不能复用本轮状态。
A2/A3 host 查询 `OCCUPY` 与 `PHY_DIE_ID`，用 `die_id * 8 + local_cpu_id` 生成与设备
`sched_getcpu()` 一致的 CPU 编号；例如 die 1 的 `0xfc` 对应 CPU 10–15，四线程选择 12–15。

TMR 默认多线程启动时，公共准备完成后，orchestrator 开始建图。
Kernel 与 program 共用 `handshake_owned_clusters()` 和 `assign_own_clusters()`：每个 scheduler
轮询自己负责的 cluster，批量发布 task 指针和打开寄存器窗口，再初始化所属核的 tracker、
payload 和 context。物理核 ID 由设备核身份指令产生，唯一性与 program 一样由平台保证；
两种入口使用相同的 64 字节身份报告布局。Program 使用 Runtime 内嵌的报告，kernel 使用
context 持有的独立报告区。Kernel 的清零由设备 prelude 在取得持久租约后完成，
不再排入无条件的 Host 清零 DMA。每次实际执行（包括同一捕获图的 replay）产生新的非零
身份，AICore 在发布报告前读取该身份，scheduler 在写 task 和开窗前校验 report_epoch。
租约存储独立于清零区；重入或失败永久锁存故障，后继入口在写共享状态前拒绝执行。
图内 epilogue 只有在 AICPU/AICore 都完成后才释放成功租约。实际 epilogue 包只带 context
身份，其逐次执行安全性依赖图节点单次执行及 completion 顺序：上一轮尚未释放时，下一轮
不能成功准入；失败后不能重新准入。不能将组件的显式 epoch 拒绝测试等同于生产 epilogue
自带独立 nonce，也不承诺驱动在 completion 后任意重放旧节点时仍安全。
两种入口都由 AICore 读取自己的 DATA_MAIN_BASE 判断开窗，不使用额外的 GM OPEN 通知。
正常任务循环和退出逻辑共用；A2/A3 与 A5 的 Kernel 均广播 EXIT、收集本次 GM ACK，
再完成关窗、readback/drain 和 post-close release；A5 保留自己的寄存器映射接口。
release gate 在对应窗口初始化发布前清零，早到的退出请求通过 READY/REQUESTED 保留。
OPENING 与 CANCELLED 使用排他 CAS：取消先赢时禁止写 task 和开窗；初始化者先认领
OPENING 时必须完成实际 OPEN 和 READY，再接管早到 REQUESTED 的退休，不能同时发布
未开窗取消。未开窗取消只写 AICPU 所属控制行，不能覆盖 AICore 专属的 ACK 行。
Kernel 的外层入口在准入前只读取 envelope、不可变 descriptor 和独立租约的缓存行；
整片数据缓存初始化在准入后执行。context generation 标识准备生命周期，replay epoch
标识该生命周期内的一次实际执行，不能互相替代。失败后保留租约和资源，不能复位复用。

未启用泳道图、PMU 或参数 dump 时，各 scheduler 完成本地初始化、等待 orchestrator 发布
runtime reset 完成后即可派发，不等待其他 scheduler。这个选择按每轮的实际采集开关判断，
不要求重新编译为非 DFX 版本。启用上述采集时保留初始化屏障，由 scheduler 角色 0 完成
公共 profiling 初始化。串行配置保留统一 post-init 和建图前的初始化屏障。

初始化或运行失败时，公共执行器发布失败，释放 CPU 等待者并汇总原始错误。
已开窗核使用公共退出手段；未开窗核由排他取消认领发布 pre-window cancel，等待开窗的
核心观察到该词才能返回，不假装它完成了当前请求 ACK。已认领 OPENING 的核心仍需退休。
在途 scheduler 在每轮调度前消费持久 replay 故障，并发布共享首错供生产者观察；生产者在
首次 submit/dummy/alloc/scope 或 is_fatal 回调处读取共享错误，再由自身线程锁存 fatal。
并发故障的观察是协作式的，已经开始的 R1 操作或退休收尾可以完成；这不授权 R2/R3 准入。
最终状态在所有 AICPU 参与者汇合后写入 context 的诊断区。失败轮次保留 Runtime、参数和
报告存储并拒绝再次调用，恢复由调用方负责；ACL_STOP_ON_FAILURE 不证明正在执行的
AICore 已经停止。Host 在部分入队失败时保留原错误并 poison context，不发布假完成 event。
仅在 AICore 已提交、AicoreDone event 入队失败且 AICPU 尚未尝试提交的确定分支，
额外排入开窗前 GM 取消；若 AICPU 已尝试提交而接受状态不明，则不发布该取消。
取消入队本身不证明已执行或已停止，调用方确认设备静止前不得释放相关资源。
启用采集时，orchestrator 建图后的核分配统计等待公共初始化完成，避免读取未建立的 tracker。

真实 packet/native dispatch 和直接 provider 共用同一等待策略。缺 native 参与者、slot、
admission 及短初始化阶段使用现有 scheduler timeout 的共享预算，未配置时为 20 秒；
核心启动报告等待也必须使用共享启动预算，不能按核重新计时或只依赖 profiling barrier。
全员 Joined 后的 Final 不施加固定 20 秒整图上限，避免误杀持续进展的长图；持久故障仍
解除等待。超时保持失败租约、参数和资源，不能发布成功 completion 或把 gate 重置 Idle。
核心 post-close 必须等真实 release；物理 MMIO 阻塞和总 op 仍受 caller/CANN 的超时合同约束。
Kernel 借用设备，只解析 scheduler/stream 配置；op-execute watchdog 由设备调用方设置。

Context descriptor 版本为 3，仍占 192 字节：admission_address 位于偏移 168，
两个保留字段位于偏移 176。身份报告、最终状态和独立的持久租约各占 64 字节。
A2/A3 与 A5 均使用当前退出请求 ACK，并在关窗/readback/drain 后发布返回许可。
Host、AICPU、AICore 必须使用同一 runtime revision；不支持复用版本 1 或版本 2 的 descriptor。

HBG 已有内部 packet/restore consumer，公共 kernel launch owner 尚未接线。

部分已提交工作的失败会使 context 进入 Poisoned。若外围包在建立可信绑定前被拒绝，
设备入口不会解引用任意 `binding_address` 尝试取消 AICore。常规错误输入在 Host 提交前
就被拒绝；损坏设备包的恢复不等同于已完成端到端支持。

## 5. 回滚、释放和验证范围

stage 的分配或复制失败撤销候选，已分配的固定 arena 可保留供重试。
Host runtime 记录失败会回滚未发布条目。注册开始后发生错误时，context 保留相关地址并
进入 Poisoned，调用者须建立静止状态后显式关闭。kernel 模式拒绝通过 program 注册/注销
接口绕过这些规则。

close 前，调用者停止提交、等待 eager/replay 完成并销毁引用资源的 graph。
`finalize_device` 只释放 context 资源，不释放 caller tensor，不重置设备，不终止 ACL。
设备查询拒绝或清理失败后可以重试；清理失败保留剩余资源和执行占用权。
同一加载的 host runtime SO 限制一个设备/runtime 身份下的 live kernel context；
不同 host SO 副本或进程间的执行隔离仍需调用者协调。

相关验证包括：

- [缓存单元测试](../../tests/ut/cpp/common/test_kernel_callable_cache.cpp)：铸 ID、容量、上传失败和回滚。
- [Dispatch packet 测试](../../tests/ut/cpp/common/test_kernel_dispatch_packet.cpp)：真实解码、重复编码、地址和 scalar 隔离。
- [设备入口测试](../../tests/ut/cpp/common/test_kernel_dispatch.cpp)：公共包校验和驻留身份拒绝。
- [HBG 内部测试](../../tests/ut/cpp/common/test_hbg_host_graph_build.cpp)：构图、资源容量、包和槽位准入。
- [C ABI 测试](../../tests/ut/py/test_kernel_mode_c_api.py)：真实准备/关闭、TMR eager 数值、参数快照和设备查询恢复。

a2a3 eager 数值路径已有真机通过记录。A5 的实现与测试入口均存在，但测试定义不等于真机验收。
内部 HBG 单元测试以及 eager 成功也不代表完整 ACLGraph capture/replay 已完成验收；
各次执行结果以本轮验证日志为准。

## 退出与非法 replay 交错的验证

清零前准入、每次 replay 身份、R1 故障后 R2/R3 的共享状态保护、当前 ACK、
三条历史退役入口及 PMU 故障边界的实验与证明，见
[Kernel replay admission and retirement validation](../kernel-replay-admission-validation.md)。
文中分别列出 CPU 反例、实际设备注入、原始证据身份及仍依赖调用者的完成/停止合同。
