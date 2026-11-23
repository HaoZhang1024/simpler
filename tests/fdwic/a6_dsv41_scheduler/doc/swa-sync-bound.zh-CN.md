# A6 SWA 同步约束极限

按[现有同步约束模型](../../dsv41_scheduler/BOUND.md)计算 A6 SWA 的排程下界。核资源固定为
**54 C + 54 V**，用已验证的 **t25=54 块**回放，t22 仍为 **48 个同步 1C1V block**。
每轮有 16 个计算任务、560 个 kernel 执行实例。t25 的前 10 块各算两个 head，
另外 44 块各算一个，求解器按每块的实测时长排程。

同一 A6 卡、同一 plan、callable 和 runtime 构件各跑一次 L0、L2，每次预热 1 轮、正式
10 轮并比对参考输出。L0 提供整图 AICore wall。Percounter 从 L2 导出实际领取的
`block_idx`、子任务槽和 kernel 返回时刻。求解使用 kernel 开始到返回的区间，
完成发布屏障和调度逻辑在这段区间之外。L2 与传瑜原表的 HBG L1 采集条件有差异，
报告时注明输入为 **A6 Percounter L2**。

## 黄区命令

在分支仓库根目录执行。加载 A6 CANN 环境和项目 venv，使用已分配的 A6 设备。
`SWA_RUN` 指向包含 `query/query` 的原准备目录，`T25_RUN` 指向前次 A/B 试验生成的
`swa-t25-*` 目录，`T25_RUN/t25-54` 包含 `build.json`、`bundle/` 和 `host/`。
若需要重新生成该目录，按[现有 64/54 块用例说明](a6-swa-performance-progress.zh-CN.md#t25-的-64--54-block-对照)运行。

```bash
: "${DEVICE:?已分配的 A6 卡号}" "${SWA_RUN:?原 SWA 准备目录}" "${T25_RUN:?54 块 A/B 目录}"
SWA=tests/fdwic/a6_dsv41_scheduler
MODEL=tests/fdwic/dsv41_scheduler/production
CASE="$T25_RUN/t25-54"
mkdir -p build
OUT=$(mktemp -d "$PWD/build/swa-a6-bound-XXXXXX")
echo "SWA bound output: $OUT"
git rev-parse HEAD | tee "$OUT/git-head.txt"

python simpler_setup/build_runtimes.py --platforms a6 --runtime percounter \
  --lib-dir "$OUT/lib" --profiling-dfx 1 --profiling-orch 0 \
  --profiling-sched 0 --profiling-tensormap 0
pip install -r "$MODEL/requirements-bound.txt"

for level in 0 2; do
  python -I "$SWA/run.py" --platform a6 --runtime percounter \
    --device "$DEVICE" --a6-query "$SWA_RUN/query/query" \
    --runtime-lib "$OUT/lib/a6/onboard" --build-dir "$CASE" \
    --level "$level" --warmup 1 --rounds 10 --output "$OUT/L$level"
done

python "$SWA/analysis/swa_sync_bound.py" \
  "$CASE" "$OUT/L0" "$OUT/L2" "$OUT/model" --time-limit 30
```

两个采集命令均须通过输出校验。分析入口检查两次的设备和构件哈希一致，检查 L2
每轮记录中的 54 C / 54 V 和 560 个执行身份，核对计划的 kernel、块数和同步标志。
读取 `deps.json` 的完成依赖，包括分配和依赖节点。若观测到后继在依赖完成前已进入
kernel，会报告该轮超出任务完成模型的适用范围。

## 回填文件

| 文件 | 字段和用途 |
| --- | --- |
| `git-head.txt`、`model/summary.json` | Git 提交、设备、plan/callable/runner/runtime SHA-256、核容量、采集级别、每轮求解时限及结果。 |
| `model/l0.csv` | `round,aicore_wall_us`，10 轮 L0 原始值。 |
| `model/blocks.csv` | `round,source_task,task_id,block_idx,subtask_slot,core_type,worker,func_id,start_cycles,kernel_end_cycles,clock_hz,duration_ticks`。每轮 560 行，以 `(round,task_id,block_idx,subtask_slot)` 唯一标识执行。 |
| `model/tasks.csv`、`model/edges.csv` | 任务的块数与 `sync_start`，以及 task ID 的前驱、后继。零计算节点保留。 |

逐块区间由设备时钟计数换算，`duration_ticks` 按既有模型向下取整到 100 ns。
原始 `L2/percounter/rank0/run*/` 泳道、依赖和任务 ID 映射留在现场。回填
`summary.json` 和 L0 小表即可记录结果。需要在另一侧重建模型时，再回填压缩后的
`blocks.csv`、`tasks.csv`、`edges.csv`。

汇报格式如下。微秒值用三位小数，百分比用两位小数。

| A6 SWA 配置 | L0 AICore wall 均值（µs） | 模型下界均值（µs） | 模型可行排程均值（µs） | 多花时间（µs） | 比下界多（%） | 求解状态 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Percounter，t25=54，54C+54V | 待回填 | 待回填 | 待回填 | 待回填 | 待回填 | 待回填 |

`多花时间 = L0 均值 − 模型下界均值`，`比下界多 = (L0 均值 / 模型下界均值 − 1) × 100%`。
每轮结果保留原始 `status`、`lower_bound_us`、`feasible_us` 和 `optimal`。
有任一轮未证明最优时，下界及相对差标 `†`。模型令调度和通知成本为零，用观测到的
kernel 时长约束排程，并放宽具体物理核组位置。真实可节省的时间以之后的上卡实测为准。
