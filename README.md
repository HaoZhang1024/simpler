# A3 measurements for simpler PR 3172

The four builds use the same A3 device, input and non-scheduler binaries.
In the CSV tables A is the baseline, E adds the empty-early-queue check,
R adds the ready MIX dispatch change, and J includes both.
Time fields use microseconds. L0 Effective runs from the earlier of the
orchestration and scheduler starts to the later of their ends. L4 publication
and finish times start at orchestration submit end. Every MIX24 call checks
all 1,152 output values.

- `mix24.csv` contains 200 formal L0 and 12 formal L4 calls per build and SS setting. Subtract SS off from SS on within the same group and pair. `outer` counts productive old drain spans in that call. `outer_us` is the maximum over owners.
- `bench-groups.csv` contains the four groups for the isolated 4b pair (A4b/E) and three groups for the final dispatch and combined builds (A/R/J). A4b and A use identical baseline firmware. `bench-l0.csv.gz` contains the individual calls, including high values. The seven standard cases use 100 calls per group. Dense16 uses 1,000.
- `manifest.json` identifies the two Git baselines, four source variants, identical non-scheduler images, and the compiled MIX24 input. The dispatched AICPU SHA-256 changes in every arm.
- `validation.json` records the late-submit watchdog outcomes in the eight-cluster simulator and the delayed SS queue producer regression in the CPU fixture.

In the ordinary benchmark the earlier A4b/E pair is preserved within its original four-arm batch. For the final builds the three orders (ARJ, RJA, JAR) rotate by case. The MIX24
process orders are AEJR, ERAJ, RJEA, JARE for L0 and AEJR, RJEA for L4
(the second L4 order is the reverse of the first). Two warm-up pairs per
process are excluded. Every other measured call is retained.
