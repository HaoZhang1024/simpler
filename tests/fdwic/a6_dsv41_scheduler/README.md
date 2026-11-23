# A6 percounter SWA

The SWA replay runs the production percounter scheduler on 54 AIC + 54 AIV.
Each cluster has one AIC and one AIV. The case freezes the 19 kernel registrations and their source dependencies from
the measured SWA replay in `kernels/` and the frozen input and reference tensors in `fixtures/`.

| Component | A6 contract |
| --- | --- |
| Replay | 16 compute tasks. t22 uses 48 C+V blocks with synchronized start. t28 uses 32 C+V blocks. |
| Resources | A 64-block vector task uses up to 54 AIVs in its first wave. The 54-block t25 comparison changes only the recorded block count. |
| Lifecycle | AICPU publishes READY in shared memory. AICore checks the per-worker shutdown gate. Dependency counters use the GM path. |
| SSBUF | Runtime uses bytes 1792–2047. The AIC and AIV callable context slots start at 1920 and 1984. Rebuild the runtime and callable together. |
| Profiling | L0 records whole-run timing. Native percounter L2 records each block's kernel start, return and scheduler finish. |

## Build and run

Use Linux, the A6 CANN environment, CCEC, a host C++ compiler, CMake, Ninja and a Python environment with the Simpler build dependencies. From the repository root, prepare PTO-ISA at the revision selected by this checkout.

```bash
git clone https://github.com/hw-native-sys/pto-isa.git build/pto-isa
git -C build/pto-isa checkout --detach "$(cat pto_isa.pin)"
```

With the allocated A6 card in `DEVICE`, run the integrated check. This builds
the runtime, query tool, runner and SWA kernels from this checkout into a new
output directory.

```bash
bash tests/fdwic/a6_dsv41_scheduler/test_a6_swa.sh "$DEVICE"
```

Check the device query, reference output validation and all ten measured rounds.
The default replay uses 64 t25 blocks and 570 executions. For the 54-block
comparison and the scheduling bound, run the following entry point. It builds a
matching callable, captures L0 and L2 and checks all 560 executions per L2 round.

```bash
DEVICE="$DEVICE" bash tests/fdwic/a6_dsv41_scheduler/analysis/run_swa_sync_bound.sh
```

Record the commit, device, CANN and compiler versions, output validation and
AICore/device timing from `test.log`. For the bound include `model/summary.json`
and `model/l0.csv` from the output directory printed at startup. Compare the same
block count, input and profiling level across revisions.

## 蓝区验证与黄区回填

代码基线为 `922b55003`。蓝区在 CANN 9.3.0 下构建了 A5 和 A6 的
percounter runtime、replay、runner 和 SWA callable。A6 的 64-block 与
54-block 版本分别生成 570 和 560 次执行。5 个 C++ 测试目标和 9 项 SWA 离线测试通过。
A5 栈对齐静态扫描完成 7/8 个编译单元，已扫描部分为 0 项发现。
剩余的 `kernel.cpp` 生成的设备 bitcode 在两种 LLVM 读取器中均解析失败。

| 平台与配置 | 预热 / 正式 | 参考输出 | AICore L0 均值 | Device L0 均值 |
| --- | --- | --- | --- | --- |
| 蓝区 A5 Ascend950DT_9582，32C+64V，t25=64 | 1 / 10 | PASS | 164.483 µs | 227.184 µs |
| 黄区 A6，54C+54V，t25=64 | 1 / 10 | 待填 | 待填 | 待填 |
| 黄区 A6，54C+54V，t25=54 | 1 / 10 | 待填 | 待填 | 待填 |

黄区先执行上面的 `test_a6_swa.sh`，将输出目录中 `test.log` 的校验结果和均值填入
t25=64 行。通过后执行 `analysis/run_swa_sync_bound.sh`，将 L0 结果填入 t25=54 行，
并在下表记录 L2 的 10 轮统计。当前迁移分支已经开跑的实验按原提交回填。

| 黄区运行信息 | 回填值 |
| --- | --- |
| 集成提交、SoC、CANN、CCEC 版本 | 待填 |
| t25=54 每轮 kernel 执行数、成功匹配轮数 | 待填，预期 560 次 × 10 轮 |
| `model/summary.json` 中的 `lower_bound_mean_us`、`feasible_mean_us`、`all_optimal` | 待填 |
| 中途失败时的阶段、命令和首条错误 | 按需填写 |
