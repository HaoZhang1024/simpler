# Native retirement safety and fault validation (#1710)

This change extends the PMU cleanup fix in PR #2600. It makes Native
retirement acknowledge the current launch, preserves early retirement
requests, bounds retirement with one absolute deadline, and performs PMU
cleanup only after the corresponding core has acknowledged its final
Handshake access. It does not enable the experimental captured Kernel replay
implementation.

## Scope and acceptance boundaries

The starting revision is `52c4d3d0077e5de9263f275b1116ddcca040a227`.
Its parent is `e994e106d8020c049dc419a67498db37bc6fcd3d`.
The original seven-file PMU resource cleanup remains in that history.

In this tree, `simpler_kernel_mode_supported()` returns zero and
`simpler_kernel_mode_launch()` returns `PTO_RUNTIME_ERR_INVALID_STATE` after
argument validation, before enqueueing a launch. Kernel initialization can
still allocate resources and partially bring up TMR; unsupported launch does
not mean initialization is allocation-free. The experimental Kernel tree at
`17e342455` is a different source identity. Its replay results are not Native
acceptance evidence for this PR.

| Safety requirement | Evidence and remaining boundary |
| ------------------ | ------------------------------- |
| Separate normally submitted rounds | Existing Native execution permits, current run descriptors and whole-operator synchronization remain in effect. |
| Reject concurrent Host submission | Existing submission and context guards remain in effect. They do not inspect externally replayed captured graphs. |
| Reject overlap before shared-state clearing | This PR does not enable Kernel launch or port the experimental admission-before-clear protocol. Forced captured replay and early-clear counterexamples remain an acceptance requirement for that future feature. |
| Match exit acknowledgement to this launch | Every modified AICore producer clears COND before publishing the current report epoch; its only terminal EXITED publication follows the last Handshake access. Native consumers already match the current report epoch. |
| Preserve exit requested before initialization completes | READY/REQUESTED handoff defers retirement until valid metadata and PMU initialization are published. A5 resident discovery now retains accepted current reports even when a peer times out. |
| Finish the AICPU close window before AICore returns | The acknowledged target runs PMU restoration, platform close/readback and the existing completion barrier before its return gate opens. Unit tests cover this order and silent peers. |
| Stop submission after partial Host enqueue failure | Existing poison/retention behavior remains. This is not autonomous cancellation of an unpaired device task. |
| Propagate device failure to the caller | Hardware fault runs return errors. This does not prove detection of every illegal external replay or attribution to its captured round. |
| Prevent later work from modifying failed state | Same-context R2/R3 **new submissions** are rejected after R1 fails. Already-queued or forcibly executed Kernel R2/R3 and arbitrary GM canary preservation are not established here. |
| Bound an unresponsive-core exit | All tested retirement owners share one absolute deadline. This does not bound every initialization barrier or prove that a timed-out core has stopped. |
| Retain resources until execution is known to have stopped | Fault tests retain failed owners and allocations; they do not close or reuse the failed context. Existing recovery requirements remain. |
| Demonstrate failure without contamination | Fault tests establish no ACK, no close, no PMU restore and no Core-buffer flush on silent targets, plus rejection of later fresh submissions. They are not a proof about forced captured successors. |

## Protocol argument

The per-core publication and retirement order is:

```text
COND := IDLE -> store barrier -> current report epoch
    -> current-launch execution
    -> final Handshake access -> store barrier -> COND := EXITED
    -> AICPU observes EXITED
    -> PMU restore + same-register readback (only if PMU initialized)
    -> platform close + readback + completion barrier
    -> release this core's return gate
```

Publishing a new report without clearing a retained EXITED value admitted a
stale acknowledgement. The AICore regression tests run the real producer and
fail the old implementation at that publication boundary. They cover both
AIC and AIV on A2/A3. The equivalent producer ordering is applied to A5 TMR,
legacy HBG and resident HBG.

The initializer sets READY only after publishing the core metadata and
completing profiling initialization, or after joined discovery failure has
identified the valid subset. An early requester sets REQUESTED without
reading unpublished metadata. The atomic operation that adds the second bit
owns retirement. Duplicate or overlapping owners cannot retire that core
again. A5 resident uses UNCLAIMED/SIGNALING/SIGNALED/JOINING instead: a join
observing SIGNALING fails rather than spinning indefinitely on its owner.
Accepted current reports survive partial discovery failure.

Each run lazily installs a single absolute retirement deadline by
compare-and-exchange. Normal, emergency and late partitions reuse it; a new
partition does not receive a fresh timeout. The deadline begins at first
retirement ownership/signal, not at the Host API call. A claimed target is not
retried after timeout. An unacknowledged target receives neither the PMU
callback nor platform close nor a return-gate release. Core-keyed buffer
flushing is restricted to the released subset.

PMU restoration used to precede acknowledgement in several shutdown paths.
It now runs through the acknowledged target's callback. The callback also
requires successful PMU initialization. Each restored PMU control register
has one fixed same-register readback; there is no busy polling. This closes
the posted-write ordering boundary before the platform completion barrier
and return gate. The posted-MMIO unit model keeps a write pending until its
own register is read, so a read of a different close register cannot make the
test pass. This is a software ordering proof, not a measurement of peripheral
bus completion on every supported chip.

## Hardware method and identity

The machine-readable [evidence record](issue-1710-retirement-evidence.json)
contains all samples and batch identities. A3 and A5 DT are separate
platforms and are never paired. Device allocation and architecture checks
precede Worker creation. Only development devices 0 through 3 are eligible.

The diagnostic SDKs derive from the frozen Native candidate archive with
SHA-256 `8fb718d262bfb0c72a3859b189adcf23e4fc3d78cfaa52ac152da03f1477396f`.
Each private overlay has an exact inverse, does not change the stock incore
kernel, and records its source, actual compiler inputs and loaded Host SDK.
The final source adds PMU fixed readbacks and additional unit coverage;
format-only changes are checked for C++ token identity. The fault runs below
never call the newly changed PMU-stop branch because no core acknowledges.
Their source identity is retained rather than relabeled as a final-binary
measurement.

For each route, PMU is enabled on every discovered core (72 on A3, 96 on A5),
with two AICPU threads. The positive operation adds two 16,384-element float
tensors and checks all outputs. Legacy HBG also includes an AIC noop to select
the legacy route. Resident HBG is an A5-only route. The fault overlays are:

1. **silent**: every AICore parks at the actual exit tail before EXITED. The
   loop performs a real volatile register read, so the compiler cannot remove
   it. The graph has completed before normal retirement on the legacy/TMR
   owners.
2. **abort**: the same silent-core overlay, plus an injected AICPU failure
   after actual PMU initialization. PMU initialization and register values are
   real, not mocked. A5 resident takes the failed-initialization path.

Each fault process records current epoch, unique physical core IDs, PMU
enable readbacks, retirement start/end/deadline/frequency, ACK/close/PMU-stop
and Core-buffer-flush events. After the Host reports R1's error, R2 and R3
are attempted using the same failed context. Both must be rejected. Failed
owners are held until process exit; no failed close/free/reuse is attempted.
A separate canonical process then runs the healthy golden case and closes
normally. That recovery process is not reuse of the failed context.

The measured retirement duration is the group-entry-to-last-group-return
counter interval, converted using that platform's recorded counter frequency.
It excludes the Host error/synchronization envelope, which is about nine
seconds with the configured eight-second operator timeout. A slightly
sub-second result is expected when the absolute deadline was installed
before group entry. P95 uses nearest rank; with three samples it equals max.

## Results

All 48 fault invocations and all 48 corresponding fresh-process recovery
invocations passed the independent fault oracle. Every fault had PMU enabled
on all discovered cores, zero exit ACKs, zero closes, zero PMU-stop callbacks,
zero Core-buffer flush targets, retained allocations, and rejected same-context
R2/R3 fresh submissions. No samples are dropped or pooled across batches.

| Batch | Route | Fault | Samples | Mean (s) | P95/max (s) | Min (s) |
| ----- | ----- | ----- | ------: | -------: | ----------: | ------: |
| A3 r4 | legacy HBG | silent | 3 | 1.000002367 | 1.000005120 | 0.999999740 |
| A3 r4 | legacy HBG | abort | 3 | 1.000002887 | 1.000003680 | 1.000001500 |
| A3 r4 | TMR | silent | 3 | 1.000003787 | 1.000005500 | 1.000002920 |
| A3 r4 | TMR | abort | 3 | 1.000002027 | 1.000004860 | 1.000000360 |
| A5 r4 | legacy HBG | silent | 3 | 1.000008164 | 1.000011057 | 1.000006279 |
| A5 r4 | legacy HBG | abort | 3 | 1.000003824 | 1.000010979 | 0.999999286 |
| A5 r4 | resident HBG | silent | 3 | 0.999980796 | 0.999983024 | 0.999978609 |
| A5 r4 | resident HBG | abort | 3 | 1.000003986 | 1.000005302 | 1.000001560 |
| A5 r4 | TMR | silent | 3 | 1.000007451 | 1.000012287 | 1.000002332 |
| A5 r4 | TMR | abort | 3 | 1.000007838 | 1.000009987 | 1.000006400 |
| A5 r5 | legacy HBG | silent | 3 | 1.000007599 | 1.000010192 | 1.000005180 |
| A5 r5 | legacy HBG | abort | 3 | 1.000008437 | 1.000009726 | 1.000006783 |
| A5 r5 | resident HBG | silent | 3 | 0.999981242 | 0.999982493 | 0.999980332 |
| A5 r5 | resident HBG | abort | 3 | 1.000003090 | 1.000003773 | 1.000001779 |
| A5 r5 | TMR | silent | 3 | 1.000008074 | 1.000012722 | 0.999999600 |
| A5 r5 | TMR | abort | 3 | 1.000008909 | 1.000012798 | 1.000003566 |

These values demonstrate a shared one-second retirement budget rather than
one second per core or owner. They do not establish an overall one-second
Host failure bound or physical core termination.

The final candidate archive
`b4c4016daf6812416dbb187a1a03be0023f50587598ef0ae9e8fa610ac04f607`
was rebuilt independently on A3 and A5 DT. Its five applicable PMU-enabled
healthy routes pass complete-output golden checks and normal close. Source,
loaded Host/AICPU/AICore components and binding hashes were checked before
and after execution; the evidence JSON records both tasks and all component
hashes. The complete non-hardware C++ suite passes 325/325 targets, including
the new posted-write regression and partial-discovery tests.

## Negative controls and limits

- The original Native implementation fails the current-report/stale-EXITED
  tests and resident PMU/duplicate-retirement/deadline tests. The corrected
  implementations pass. A separate posted-MMIO regression fails all four
  PMU-finalize targets before the same-register readbacks are added.
- Two additional resident tests exercise real partial discovery with one
  stale peer and an overlapping join observing an in-progress signal owner.
- Early private builds were rejected because Python's editable import finder
  selected a different compiler source root. Corrected private builds use
  `python -S`, assert build-module origins, and inspect actual compile inputs.
  Successful operations from the rejected builds are not fault evidence.
- A3 r4 and A5 r4 wrapper exit status was nonzero because the collector
  incorrectly required an error log from quiet healthy recovery processes.
  All child invocations completed successfully. Post-run collection and the
  independent oracle verify all fault and recovery records; A5 r5 corrects
  the collector and exits zero.
- Heavy healthy diagnostic logs stop near a 64 KiB output boundary: they
  contain all ACK/close/PMU-stop records but omit part of the flush tail.
  Lower-volume diagnostics and a log-flush attempt did not establish complete
  healthy device telemetry. Normal golden completion is verified separately;
  no complete per-core healthy flush trace is claimed from those logs.
- Timeout, poisoned context, process exit, or green CI alone is not proof of
  physical execution stopping or arbitrary shared-memory non-contamination.
  The forced-successor and early-clear Kernel counterexamples remain outside
  this Native PR's accepted scope. This PR references #1710 and does not close
  the broader captured-replay safety issue.

## Reproduction checks

Build the repository's C++ suite and run all non-hardware targets:

```bash
cmake -S tests/ut/cpp -B build/cpp-ut -DCMAKE_BUILD_TYPE=Debug
cmake --build build/cpp-ut --parallel 4
ctest --test-dir build/cpp-ut -LE requires_hardware --output-on-failure
```

Focused targets include `test_a2a3_hbg_pmu_finalize`,
`test_a2a3_tmr_pmu_finalize`, `test_a5_hbg_pmu_finalize`,
`test_a5_tmr_pmu_finalize`, `test_a5_hbg_retirement_wiring`, both platform
retirement groups and both scheduler-retirement variants. For hardware
reproduction, allocate a checked development device, build compatible
Host/AICPU/AICore components together, apply each described private overlay,
and require all event, identity, retention, rejection and golden assertions
above. A timing value without these assertions is not an accepted fault run.
