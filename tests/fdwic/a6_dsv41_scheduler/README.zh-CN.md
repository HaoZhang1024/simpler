# A6 单卡 SWA · percounter

| 从这里看 | 内容 |
| --- | --- |
| [A6 与 A5 差异](doc/a6-a5-comparison.zh-CN.md) | 环境与核配置、寄存器和 GM 实测、整图时延、t22 / t25 / t35 当前定位 |
| [A6 percounter SWA 性能分析与每日进展](doc/a6-swa-performance-progress.zh-CN.md) | 实验命令、A5 基线、A6 逐批回填、泳道端点和每日结论 |

黄区有两项独立实验。查 t25 慢在哪条操作，用 64 块的 [FP8 分段命令](doc/a6-swa-performance-progress.zh-CN.md#a6-fp8-output)，填 [FP8 结果](doc/a6-swa-performance-progress.zh-CN.md#a6-fp8-output-feedback)。查当前 54 块方案整图还有多少排程空间，用 [L0 / L2 命令](doc/a6-swa-performance-progress.zh-CN.md#a6-sync-bound)，填 [整图下界结果](doc/a6-swa-performance-progress.zh-CN.md#a6-sync-bound-feedback)。

## 用例与构建

输入、参考输出和原始 plan 随 [SWA 数据包](fixtures/) 交付。回放恢复 task 8～35 的 Tensor 视图、别名、依赖和 launch 参数，执行其中 16 个计算任务。构建使用 Simpler、与 `pto_isa.pin` 匹配的 `build/pto-isa` 和目标平台 CANN；直接编译 19 个设备 C++ kernel 和原生回放工具。[准备入口](prepare.py) · [运行入口](run.py) · [生产 runner 和 replay](../dsv41_scheduler/production/)

从仓库根目录加载对应平台的 CANN 和项目 venv。**首次准备 A6 的 64 块基线**用下列命令。脚本新建输出目录、编译 runtime 和用例、核对所分配的卡，再执行 1 次预热和 10 个 L0 正式轮。已准备好的 54 块实验直接使用上面的交接入口。

```bash
bash tests/fdwic/a6_dsv41_scheduler/test_a6_swa.sh "${DEVICE:?已分配的 A6 卡号}"
```

**重建 A5 percounter 基线**用下列命令。后续只改调度器时，重编 runtime 后复用已准备的用例，运行结果写入新目录。

```bash
SWA=tests/fdwic/a6_dsv41_scheduler
python simpler_setup/build_runtimes.py --platforms a5 --runtime percounter \
  --profiling-dfx 1 --profiling-orch 0 --profiling-sched 0 --profiling-tensormap 0
python -I "$SWA/prepare.py" build --platform a5 --pto-isa build/pto-isa --jobs 4
python -I "$SWA/run.py" --platform a5 --runtime percounter --output "outputs/swa-a5-$(date +%s)"
```

离线排查可单独编译 [A6 kernel](compile_kernels.py)、[转换 plan](prepare_plan.py) 或[验证 1C1V 资源](test_resources.py)。[原始构建命令与依赖明细](https://github.com/HaoZhang1024/simpler/blob/37b531376ec4434833d28c8c05a51f1b7adbe796/tests/fdwic/a6_dsv41_scheduler/doc/usage.zh-CN.md)
