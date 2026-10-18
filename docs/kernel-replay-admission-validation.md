# Kernel replay admission, fatal propagation and retirement validation

**A3/A5 source-bound acceptance completed. CPU regressions, actual device fault controls and full raw-evidence replays are reported separately below. GitHub CI is reported by the checks on the published PR commit.**

Related to [#1710](https://github.com/hw-native-sys/simpler/issues/1710). The comparison base is Kernel integration commit `17e342455e2e8d9112c0613b6c9cd6eca79e71d0` on `feat/kernel-mode-integration-test`. This work makes illegal replay overlap fail before a rejected successor clears shared state, associates reports and retirement with the current execution, and retains resources when execution cannot be proven stopped. The claim is conditional on the supported launch and graph completion contracts described below; it is not a promise to recover and reuse an arbitrary failed device context.

This report separates source reasoning, deterministic CPU reproduction, diagnostic NPU experiments and final production-source acceptance. Private trace, transport suppression, launch omission and unsafe-clear components are experiment controls and are excluded from the production patch.

## Source and execution identity

| Input | Identity or status |
| ----- | ------------------ |
| Integration base | `17e342455e2e8d9112c0613b6c9cd6eca79e71d0` |
| PTO dependency | `327cd5869f3a7c4d2c6a1b945b2aed06e7665c5d` |
| Historical CPU r8 source map | 2,596 source files; 76 changed paths; manifest SHA-256 `86ed56aced8fbe2918d57b9f36fd8ff2790ff50a00c7e7d0283ec46fa71853fc` |
| Historical v3 production-source manifest | SHA-256 `aee5e17338c3d716f8d7f92aba3cb2d9158f975264c62c66e4dc31fc562ba322` |
| Historical CPU r8 versus v3 source comparison | All production files match exactly. CPU r8 adds only test-local `assert_impl` support to the HBG unit test; publication additionally fixes the public ST observer injection position, verified separately by six actual-SDK cases. New validation prose/navigation is documentation only. |
| Final r11 CPU input | 2599 files / 84 changed paths; source manifest SHA-256 `67a2dcf9d6c116a2f00597076380b5037fe6c493813bde6523fa22b834e12e18`. All runtime/test bytes match this input; final report prose is a separately checked documentation delta. |
| Canonical resident-v4 production source | Manifest SHA-256 `e76ebe1fc13244c9803e584d40bd07ee8fb66a339272be44bbee6ef8bfa4af9c`; all final production bytes match. Relative to v3, exactly five A5 lifecycle/helper files differ and receive the additional CPU/SDK/NPU evidence below. |
| Publication identity | The PR commit identifies the published tree. The final source is bound to the full r11 CPU run. Five later A5 resident/helper source changes have a new canonical SDK and separate actual resident NPU proof below; historical v3 results retain their original identities. Final report edits are documentation only. |
| A3 production components | Actual A3 SDK build and loaded Host/AICPU/dispatcher/AICore identities retained per process; exact component table is integrated below. |
| A5 production components | Actual A5 SDK build and loaded Host/AICPU/dispatcher/AICore identities retained per process; exact component table is integrated below. |
| GitHub CI | Reported by the PR checks for the published commit; local CPU and onboard evidence below are separate. |

The Linux validation checkout preserves Git symlinks and executable modes. Every CPU input file hash matched the working candidate, and the entire source map was unchanged by the successful hooks and tests. Each device result must separately identify its loaded Host, dispatcher, AICPU and AICore components, overlay source, allocation precheck and timeout configuration. A healthy result from a different frozen input does not validate a later runtime change.

## Screenshot capability matrix

The original screenshot contains 12 capabilities. Two useful subconditions are expanded separately here: current startup-report identity and cancellation of an unpaired core before its register window opens. They are marked **expanded**, rather than presented as two additional original screenshot rows.

| ID and capability | Candidate mechanism and CPU evidence | Device acceptance and remaining condition |
| ----------------- | ------------------------------------ | ----------------------------------------- |
| 1. Legal queued rounds remain isolated | Existing event/stream dependencies remain; replay completion releases the lease only after both native execution and AICore completion. Launch ordering and failure-stop tests pass in the full CPU scope. | A3/A5 final v3 healthy captured replay passes: 20 executions per check with fresh odd epochs 3..41, current reports, golden output and even release. Fault controls use separate new healthy processes. |
| 2. Host concurrent enqueue cannot interleave submissions | The submission lock and previous-tail check protect Host enqueue. Device admission additionally covers execution of an already captured graph. | Both platforms pass same-replay, two-graph and ordered cross-stream fault matrices. Independent-stream busy entry: **pass on both platforms; see the separate busy evidence below**. Host submission protection and replay admission are separate layers. |
| 3. Illegal overlap is rejected before successor shared-state mutation | A persistent atomic lease precedes clear. Only the successful prelude may clear control/reports; busy rejection permanently latches fault. Native and AICore paths reject a faulted replay before their protected writes. Busy/no-clear and single-winner CPU assertions pass. | Both platforms pass native error, forced-success transport and unsafe-clear controls in all five paths. Only unsafe-clear changes control/reports. Busy: **pass on both platforms; see the separate busy evidence below**. R1 convergence writes remain separately classified. |
| 4. **Expanded:** startup reports belong to this replay | The device prelude allocates a fresh non-wrapping odd epoch; AICore reports carry it; scheduler checks it before task publication and OPEN. Tests cover stale/current reports and distinguish replay identity from the internal rendezvous epoch. | Complementary coverage: actual scheduler CPU tests reject stale reports before task publication/OPEN; A3/A5 hardware executes unchanged captured packets with fresh replay/current-report identities. Stale-report injection is CPU coverage, not claimed as an NPU injection. |
| 5. Exit confirmation cannot reuse an earlier acknowledgement | The TMR request differs from the previous core-owned ACK. Only an ACK matching the current request permits close and release. Tests cover stale ACK, wrap, current ACK and absent ACK. | A3/A5 TMR: old ACK 77 is rejected; current request/ACK 78 delayed 250 ms permits close/release and all Core returns. An ACK arriving at 1.2 s remains unreleased after the 1s helper failure. Legacy HBG retains its separate COND-only protocol. Additional A5 resident tests below cover current-report IDLE ordering and initialization-abort; they do not claim a GM nonce. |
| 6. Exit requests received during initialization are retained | Atomic REQUESTED/READY handoff retains early requests. An initializer that owns OPENING publishes its metadata and READY before retirement. Waiting threads do not fabricate READY on timeout. Targeted OPEN/CANCEL and owner-delay regressions pass. | Both platforms pass early fatal and interrupted OPENING with native and forced-success transport. Non-OPEN targets cancel; the OPENING owner publishes READY and retires. Missing-report startup is separately covered by Program PMU and CPU actual-native regressions. The additional resident fix retains known targets after partial handshake and covers actual initialization-abort below. |
| 7. AICPU closes the window before the core returns | Current TMR ACK is followed by the close pass, per-window readback, drain and only then release. AICore waits for release. Platform-specific ordering and static/CPU register tests pass. | A3/A5 delayed-current-ACK experiments observe ACK, close/release and all 72/96 Core post-close returns. Silent/deadline-late cases keep release=0 with no post-close return. Deterministic platform tests additionally cover readback/drain ordering. This independent Core return gate is a TMR guarantee; HBG resident COND-only does not add that gate. |
| 8. Host partial submission failure stops later enqueue | Each failing step stops the launch sequence, poisons the context and retains resources. Pre-window cancellation is sent only when core submission is known accepted and AICPU submission is known not attempted. Failure-point tests retain the original error. | All deterministic Host failure points pass, including cancellation-publication failure and uncertain CPU acceptance. Actual-SDK regressions pass 3/3 per platform: execution-dispatch refusal, failed initialization registration and free-failure retention/retry. Early/late device response is separate; uncertain execution is retained. |
| 9. **Expanded:** unpaired cores can cancel before OPEN | REQUESTED-to-CANCELLED and OPENING use exclusive atomic ownership. A cancelled core returns without fabricating a current ACK; an OPENING winner must complete its normal READY/retirement handoff. Both architecture regressions pass. | Both platforms pass early no-OPEN cancellation and late OPENING-owner READY/retirement controls without fabricated current ACK or extra OPEN. Host known-unattempted publication and cancellation-failure logic are actual Host CPU coverage; they are not conflated with uncertain SDK acceptance. |
| 10. Device conflicts reach the caller with the original cause | Sticky replay state and the shared-memory first error are retained. A real deadline is scheduler error 100; an existing admission fault is error 5. Scheduler failure is bridged to cooperative producer APIs. Actual native-entry tests preserve raw diagnostics and transport status. | Normal native fault matrices expose actual nonzero caller synchronization status with the failed R1 lease on both platforms; per-path values are listed below. Actual-native CPU regressions distinguish fault 5/deadline 100 and retain prior first errors. Program PMU retains fatal -9/startup -100. Busy: **pass on both platforms; see the separate busy evidence below**. |
| 11. Queued successors stop modifying protected state after failure | Failed admission cannot clear or prepare R2/R3. Native entry and AICore reject before protected writes. Running R1 schedulers consume sticky fault; producer APIs and blocked waits consume shared fatal state on the owner thread. Actual producer and native regressions pass. | All five paths pass native, forced-success and unsafe-clear controls on both platforms, with no successor clear/prepare/OPEN or payload in protected variants. R1-only post-Final scheduler latch remains a strictly classified SM difference. Busy first-producer entry: **pass on both platforms; see the separate busy evidence below**. |
| 12. Unresponsive cores have an explicit failure boundary | Actual TMR native membership/initialization waits receive the configured software policy; its report loops share a startup deadline. Retirement broadcasts before polling and spends one absolute group deadline. A5 HBG legacy's remaining per-core budget defect is fixed. | A3 HBG (72 targets), A5 TMR (96 targets) and A5 HBG legacy (96 targets) each have three actual silent helper measurements near 1 s, below. Supplemental A3 TMR is separate. The additional public Program A5 resident lifecycle now has two three-run silent/PMU groups below. Older ordinary Program startup barriers remain conditional on successfully configured SDK watchdogs, as detailed below. These bound the measured helper under a working clock/MMIO, not physical device stop or arbitrary user-code total runtime. |
| 13. Uncertain execution never authorizes resource reuse | Failed gates, leases and borrowed storage remain retained. Active/failed leases reject registration/revocation. Reclamation requires the supported completion/revoke receipt or an external stop contract. Borrowed-storage and retry tests pass. | Silent/late-ACK faults retain unreleased storage and failed odd leases. Prequeued successors are rejected at device admission, and deterministic active/failed-context registration/revoke tests pass. The separate Host-failure SDK case rejects retry with -1003. The borrowed Kernel contexts remain quarantined; this is not a blanket claim about automatic owned-Program destruction. The additional resident lifetime experiment below holds the failed native owner until process exit. Separate fresh-process golden/health success does not establish failed-context quiescence. |
| 14. Fault injection demonstrates error plus successor protection | The source mechanisms above have valid CPU negative cases and broad integration coverage. Diagnostic device controls separate SDK cancellation, internal rejection and an intentionally broken clear order. | Final v3 native/soft/unsafe-clear, early/late, ACK/retirement, Kernel PMU rejection and Program PMU failure/recovery pass on both platforms. Busy: **pass on both platforms; see the separate busy evidence below**. The added resident finish/init-abort/PMU fault controls also pass, separately bound below. Source/component identities and setup failures remain separate. |

## Conditional protocol proof

### Admission before clear and an identity for each actual replay

`TmrReplayAdmission` is persistent and outside the per-round clear plan. A successful begin requires an unpoisoned even sequence and atomically changes it to a new odd value. Only this CAS winner executes clear, and only while the native gate is idle and the invocation inactive. It flushes the cleared control/reports before release-publishing `ready_epoch`. Identity exhaustion fails; it never wraps to a reused replay identity. Running an unchanged captured prelude again therefore creates a new device identity without rewriting its Host packet.

A busy or failed begin permanently latches fault. Subsequent preludes cannot clear, native entry rejects before constructing/admitting its execution request, and AICore checks the read-only lease before broad shared-cache operations and again before ACK/report writes. Already accepted R1 operations can be in flight between checks and writes. They stop cooperatively when scheduler loops or supported producer APIs observe fault; this is not an atomic device-wide stop barrier and cannot terminate arbitrary user code that never returns to the runtime.

The producer fix does not write an owner's ordinary `fatal_` boolean from a scheduler thread. The owner acquires the shared error and latches its own state before submit, dummy task, allocation, scope APIs and the real fatal callback can mutate their protected state. Completion/error publication remains allowed for failure convergence.

### Why the context-only epilogue is conditional

The real epilogue carries descriptor/context identity, not an independent per-replay nonce. It reads the current epoch and requires an idle native gate, inactive invocation, matching completed control epoch, zero runtime/cleanup status and a successful odd-to-even CAS before releasing the lease. Any failure poisons it.

This proof relies on each supported graph node executing once, graph dependencies and native completion semantics. E1's epilogue is after its AICPU completion and AICore join; until E1 releases, the lease is odd and E2 cannot be admitted. After a legitimate release, E1's required native readers are complete. A stale epilogue independently duplicated after its prior completion, or execution contrary to the promised graph dependencies, is outside this supported contract. Tests of the lower-level explicit-epoch helper are useful but do not turn the real context-only packet into a nonce-bearing packet.

### OPEN/CANCEL ownership, current ACK and storage lifetime

The cancellation CAS can claim only a still-unowned REQUESTED core. The OPENING CAS competes on the same atomic state, so cancellation and window opening cannot both win. The OPENING owner completes its own ordinary metadata, publishes READY with release ordering and services any retained REQUESTED state. A waiting/timeout thread cannot synthesize READY or read the owner's unfinished metadata. The REQUESTED/READY handoff selects a single retirement claimant.

For TMR, the helper invalidates the old core ACK, chooses a different current request, broadcasts requests and polls all targets against one absolute deadline. Only current ACK targets are closed. Close, readback and drain precede release; silent cores remain unreleased. A later ACK after the helper has failed does not itself close or release a core. A5 legacy HBG uses an explicitly separate COND-only group helper with the same group budget and exclusive claim policy, without pretending to implement TMR GM ACK.

The caller must stop submitting, drain supported eager/replay execution and destroy every graph retaining the context before a successful close/revoke. A failed Kernel lease has no in-place recovery/reuse path in this change. Software deadlines cannot bound a physically wedged MMIO transaction or establish that a hardware reader has stopped. The borrowed-device Kernel caller must install its applicable operator watchdog; the runtime does not silently configure that caller policy. A timeout/error does not authorize freeing borrowed storage or reusing the failed context.

## Actual defects reproduced and corrected

| Gap | Valid negative evidence | Corrected behavior and regression |
| --- | ----------------------- | --------------------------------- |
| Running R1 ignored another replay's sticky fault | Original production scheduler paths failed three fault-consumption assertions on both architectures. | Scheduler polling consumes persistent fault and retires rather than continuing normal dispatch. The independent corrected targets passed 25 cases each before later unified additions. |
| Early fatal had no exclusive pre-window cancellation | Two original-implementation tests failed on both architectures; negative task `task_20261017_202221_296585727620`. | OPENING/CANCELLED ownership; corrected complete targets passed 23 cases each in `task_20261017_203107_32546419765`. Later unified retirement targets contain 27 cases each. |
| First producer API could mutate before consuming the shared error | Seven actual API/callback/wrapper negatives per architecture failed while healthy controls passed; `task_20261017_204020_395256516812`. | Owner-only shared-error observation before the first protected API action; both complete fanin targets passed 35 cases each. SM and arena were compared byte for byte, with heap/owner cursors checked separately. |
| Production native dispatch bypassed the wrapper's wait policy | With one participant missing, a configured 5 ms wait had not returned at 100 ms; explicit sticky-fault rescue was needed. | Both real registration dispatch and architecture wrappers delegate to `AicpuExecutor::execute_prepared_kernel_round()`. `NativeDispatchMissingPeerUsesConfiguredBudget` exercises the actual native entry. |
| All native threads joined but report polling had no startup deadline | A 50 ms budget remained blocked at 200 ms with a finite producer and all core reports missing. | Both report loops consume one initialization start time and existing scheduler budget. The real native all-core-no-report regression returns error 100. |
| Startup scheduler failure did not reach a cooperative producer | The valid continuous-producer red case differs from the earlier finite-producer fixture; two earlier setup/capacity failures were excluded from negative proof. | First scheduler cause is bridged to producer-visible fatal state. Actual producer APIs and a blocked allocator stop; preexisting first errors remain unchanged. |
| Existing sticky fault was relabeled as a timeout | Actual native peer-wait injection and a coordinator test distinguished the wrong cause. | Provider abort observes the preexisting cause before the coordinator enforces poison. Existing admission fault remains 5; a real deadline remains 100; earlier SM/execution errors survive. Six complete targets, 126 cases passed in `task_20261017_210435_3437794335`. |
| A5 HBG legacy still paid a deadline per core and retried shutdown | Three silent stub cores with a 100-tick budget took 306 ticks; first poll had only one EXIT. Emergency followed by normal shutdown reached 612 ticks and duplicated EXIT. Four of four actual production-path regressions failed in `task_20261017_212600_86850618848`. | Broadcast all EXITs first; one absolute group deadline; close only ACK targets; per-core atomic exclusive claim prevents a second exit path paying again. Eleven complete targets/226 cases passed in `task_20261017_212741_90498428294`. The four HBG tests use `SIMPLER_DFX=0` and do not establish PMU behavior. |

The earlier 63-case helper-only run did not prove the production native packet route. Targeted results retain their own source/binary identities; the historical integrated CPU run below checks its frozen source and older targets; the later full r11 run additionally covers the resident delta.

## Historical v3 integrated CPU validation

Task `task_20261017_213526_104015210873` completed successfully on the r8 source map above.

| Check | Command/scope | Result |
| ----- | ------------- | ------ |
| Simulator package | `python -m pip install --no-build-isolation --config-settings=build.targets=build_package_sim -e .` | Passed; both simulator architecture/runtime builds; 13 artifact hashes recorded. |
| All applicable touched-file hooks | `pre-commit run --files` with all 76 changed paths | Passed, including clang-tidy, clang-format, cpplint, repository checks, YAML and Markdown. No hook bypass. File-type hooks without matching inputs retain their normal no-files skip. |
| Complete C++ build | Configure `tests/ut/cpp` with `SIMPLER_ENABLE_HARDWARE_TESTS=OFF`; build all targets with `--parallel 4` | Passed to 100% with assertions enabled under the default configuration. |
| Actual CI CPU CTest selection | `ctest --test-dir tests/ut/cpp/build -LE requires_hardware -j4 --output-on-failure --timeout 300` | **187/187 targets passed**, zero failures, 9.34 s. |
| Complete CPU Python UT | `python -m pytest tests/ut -m 'not requires_hardware' -v` | **2,548 passed**, 79 deselected, one retained warning, 85.35 s. |

Using only `-L no_hardware` would select 161 targets and omit 26 unlabeled CPU targets. The run used CI's broader exclusion selection. CTest truncates successful stdout, so 187 is the target count; no global GTest count is inferred from incomplete captured output.

The Python warning is the existing read-only-buffer `torch.frombuffer` warning in `test_mapped_args_from_blob_delivers_tensors_and_scalars`; its assertions passed. No full ST or NPU test is included in these CPU figures.

The complete build also exposed and fixed integration defects beyond the new focused targets: the simulation swimlane target lacked the new retirement-header include path; an older A3 scheduler platform stub lacked the current ACK signature; an original feature-base thread-scheduling target omitted a common platform include; and the new isolated HBG target lacked `assert_impl` with assertions enabled. The last was fixed with local assertion support, not by defining `NDEBUG`. Their failed build logs remain preserved.

The clang-tidy hook now declares `require_serial: true`: concurrent hook batches rewrote one compile database and raced during recovery. Identical input passed the serial diagnostic, then all applicable paths passed with the diagnostic environment variable removed and the repository hook setting in effect. This changes concurrency, not checked scope. Normal PR CI also permits the intended feature base in its branch filter; detector base/head handling and workflow permissions are unchanged. The published commit must also pass its normal GitHub checks.

## A strict diagnosis of post-Final SM changes

The original native same-replay matrix reported an SM hash difference and remains recorded as a failure of its original strict oracle. It had not retained the full pre-change SM, so it cannot be described as a full before/after byte comparison.

An append-only private trace subsequently retained an exact 1,272,704-byte SM copy at the original finalizer point. Host readback independently compared every byte, recomputed the copied hash and retained the original difference. The copy is a retained byte sequence, not an atomic snapshot for arbitrary concurrent writers.

| Diagnostic platform/task | Scenario and queued rounds | Complete SM comparison |
| ------------------------ | -------------------------- | ---------------------- |
| A3 `task_20261017_213118_99495112695` | R1-only `[1]` | All 1,272,704 bytes identical. |
| Same A3 task | Same graph queued `[1,2,3]` | All bytes identical. |
| A5 `task_20261018_123002_8189834405` | R1-only `[1]` | Exactly one differing byte: offset 792 changed 0 to 5; every other byte identical. |
| Same A5 task | Same graph queued `[1,2,3]` | All bytes identical. |

Offset `[792,796)` is this frozen ABI's 32-bit `sched_error_code`; `[784,788)` is `orch_error_code`. In the changed R1-only case, the scheduler word goes 0 to 5, its other three bytes stay zero, and the existing orchestration error remains 5. The fault-copy SHA-256 is `d4a2b85472aeb5ec2f10d69258c0725bad85c6a867662113f7af140b4f9d76c1`; after-SM SHA-256 is `ac5eb605d9b019a2df3cc66697095f1f09492d1c24aaf52a3870e35fc33a20a5`. Restoring only that word reproduces the entire original copy and its FNV value `9008984192289299625`.

The source mechanism matches the distinguishing R1-only control: all execution roles have arrived when the finalizer publishes its report, but some native peers can still be reading Final. One R1 native dispatch returns an error and poisons replay; an R1 peer's final sticky-fault check then invokes the real software wait abort callback, whose CAS may record scheduler error 5 while retaining the existing orchestration first error. This callback does not write the scheduler bitmap, thread locator, stall fields, payload, arena or task queues. No extra thread-event trace identifies which native index won that CAS, so that is not claimed.

Rejected R2/R3 native dispatch sees the persistent fault before constructing the SM binding or its software wait context. It cannot reach this callback, prepare, OPEN or child execution. A single R1 reproducing the same change proves successors are unnecessary for this effect; source ordering and successor counters are also required to attribute it correctly.

The final oracle may classify only this proven case as `r1_postfinal_error_latch`, while retaining `strict_sm_equal=false` and all original bytes/differences. It requires, simultaneously:

1. Matching frozen components and the specific no-child Kernel `report_fatal(INVALID_ARGS)` injection, failed odd lease and matching snapshot epoch.
2. Complete fault-copy and after-SM, exact descriptor size, no snapshot overflow and copied hash matching the device value.
3. Scheduler word strictly 0 to 5, orchestration word strictly 5 before and after, and **every byte outside that one 32-bit word identical**. Bitmap/thread/stall changes are not exempt.
4. Control, reports, arena, runtime and payload retain their strict original checks. Clear and prepare occur once for R1; OPEN and worker admission belong only to R1; no successor payload executes.
5. The same component set's R1-only control and the real early-rejection code support the classification. Forced-success transport separately proves successor entry execution; normal SDK cancellation cannot substitute for it.
6. Any extra changed offset, different code transition, overwritten first error, reusable lease, extra clear/OPEN/payload, unexpected release or identity mismatch remains a failure.

This is not reported as five regions being byte-for-byte immutable. It is a narrow, retained diagnostic change during R1 error convergence. A product contract requiring every SM byte to freeze at Final publication would need a different last-native-departure observation boundary. The distinguishing R1-only control uses the older frozen source; the final v3 matrix independently executes this strict classifier with its own component identities and full SM pairs. The v3 runtime changes since that control are the separately verified legacy HBG retirement fix; the later resident changes below also leave the relevant TMR native-tail/callback logic unchanged.

## Retirement and PMU device contracts

The historical three retirement paths are **A3 HBG, A5 TMR and A5 HBG legacy**. Three `native:silent` TMR repetitions are three repetitions of one path. A5 HBG resident is an additional, distinct lifecycle and must not be silently included under the legacy result.

| Path | Acknowledgement and measurement | Final v3 result |
| ---- | ------------------------------- | --------------- |
| A3 HBG | Actual HBG group retirement; silent cores; one absolute group deadline and existing per-core claim. Record target count, EXIT broadcast, acknowledgement/close count, helper start/end/frequency and Host watchdog separately. | 72 silent targets, PMU-enabled actual group helper; EXIT broadcast and zero close/release. Three spans: 1.000004020 / 1.000006100 / 1.000002600s. Original collector exit1 retained; correct PID device dlog independently verified posthoc without NPU rerun. |
| A5 TMR | Current-request GM ACK retirement; all OPEN targets silent. A stale COND value or old ACK is not a current acknowledgement. | 96 silent targets, current GM-ACK helper, zero close/release. Three spans: 1.000009850 / 1.000006811 / 1.000009434s. Delayed and deadline-late ACK controls separately verified. |
| A5 HBG legacy | Actual legacy scheduler plus COND-only group helper; fixed broadcast/one-budget behavior and unique claims. No TMR release claim is made. | 96 silent targets, PMU-enabled COND-only actual legacy helper, zero close. Three spans: 1.000006811 / 0.999999384 / 1.000010395s. Correct PID dlog posthoc verification retains the original collector exit1; no TMR GM-ACK claim. |

For HBG silent tests, run a real healthy first invocation, then make the next actual AICore invocation write IDLE and remain silent. The actual production helper records its own deadline and targets. Verify silent targets are not acknowledged or closed and retain EXIT. The original probes make no explicit failed-Worker close or reuse call and run recovery in a new process. Their pre-teardown observations do not establish the absence of automatic owned-Program destructor cleanup; the later resident lifetime control distinguishes that boundary. New-process success does not establish the failed context's quiescence.

| Parameter or diagnostic control | Required value/scope |
| ------------------------------- | -------------------- |
| Native missing-peer CPU budget | 5 ms; independent 100 ms negative observation before rescue. |
| CPU missing-report startup budget | 50 ms; original negative observation at 200 ms. |
| HBG deterministic unit-test budget | 100 virtual ticks for three cores; these are not NPU durations. |
| TMR/HBG retirement device budget | 1 s configured group budget; compare actual group span, not expected value. |
| Stale/current/late TMR ACK | Old ACK 77; current ACK after 250 ms; late ACK after 1.2 s. |
| Healthy captured replay | 20 executions per healthy-process check; expected distinct odd epochs 3 through 41 after the warmup. Distinct sequence/report/completion checks pass in the final healthy processes. |
| Program PMU failure configuration | Scheduler 2 s, operator 8 s, stream 10 s, with actual applicable API/environment state retained. |

Kernel mode currently rejects PMU configuration as unsupported. Its test must establish rejection before native launch or committed device allocation, then a healthy retry with PMU disabled on the same context. That does not exercise PMU collection during a Program/Worker failure.

Program/Worker PMU is a separate supported mode. Final v3 runs passed the explicit-fatal and missing-report-startup scenarios independently on A3 and A5, with matching source/component identities and separate fresh-process recovery. The explicit-fatal case first executes a real PMU healthy seed and checks golden output plus nonempty CSV, then reports fatal 9 and verifies original error classification. The missing-report case omits only the targeted AICore launch while forwarding real AICPU execution: require one omitted launch, zero forwarded target core launches, actual CPU entry and scheduler-timeout classification. It tests runtime scheduler startup with PMU collection configured; it is not Host `Worker.init()` failure or a hardware PMU-register initialization error. Each fault is followed by a new-process healthy PMU control, with no explicit retry or close call on the failed Worker. This is not evidence that scope-based native destruction never ran after the recorded observations.

## Final v3 NPU acceptance matrix

The immutable v3 source matrix is used below. The subsequent five-file resident/helper production delta is validated separately in the additional resident section. Setup failures and prior-source diagnostics are retained separately; they do not substitute for accepted cells.

| Acceptance group | A3 final v3 | A5 final v3 | Required retained evidence |
| ---------------- | ----------- | ----------- | -------------------------- |
| Healthy captured replay and identity | Pass, 20 per process | Pass, 20 per process | Golden, epoch/sequence/completion per replay and matching production components. |
| Native R1 fatal with R2/R3 already queued | 5/5 paths, real caller error | 5/5 paths, real caller error | Eager, chain, same replay, two graphs, ordered cross-stream; real caller error; retained lease and strict protected-region checks/classification. |
| Forced-success transport | 5/5 paths, actual successor entry | 5/5 paths, actual successor entry | The same scenarios; successors actually enter and remain internally rejected; private transport success is not production success. |
| Unsafe-clear negative control | 5/5 control/reports corruption detected | 5/5 control/reports corruption detected | Deliberately reordered clear must be detected; preserve the negative result and its separate components. |
| Early fatal, OPENING interruption and busy prelude | Early/late4/4; busy 2/2 faults plus three canonical healthy processes pass | Early/late4/4; busy 2/2 faults plus three canonical healthy processes pass | Ownership/READY/cancellation evidence, no counterfeit ACK, producer consumption and actual dispatch counts. |
| Real missing-core-report startup | Actual Program PMU startup -100 | Actual Program PMU startup -100 | Correct actual entry, configured budget/cause, cooperative producer stop and pre-teardown resource snapshot; owned-Program automatic cleanup is a separate boundary. |
| Three actual retirement paths | HBG3/3; supplemental TMR3/3 | TMR3/3; HBG legacy3/3 | Path-specific helper timings, group targets, remaining/ack/close state, per-platform frequency and separate Host wall. |
| Stale, 250 ms delayed and 1.2 s late TMR ACK | All controls pass | All controls pass | Current identity, close/readback/drain/release or strict release-zero retention after deadline. |
| Kernel PMU unsupported | Prelaunch -1001; same-context disabled retry | Prelaunch -1001; same-context disabled retry | Rejected before execution/allocation; healthy disabled-PMU retry. |
| Program/Worker PMU explicit fatal and startup failure | 2 faults + 2 independent PMU recoveries pass | 2 faults + 2 independent PMU recoveries pass | Healthy PMU seed/CSV, original error/cause, exact omission evidence and new-process PMU recovery. |
| Health/recovery after each fault | 25 rest faults + 26 healthy; busy 2/2 faults plus three canonical healthy processes pass | 25 rest faults + 26 healthy; busy 2/2 faults plus three canonical healthy processes pass | Device health and independent healthy golden; failed-context non-reuse stated separately. |

## Evidence retention and publication status

| Retained bundle | SHA-256 | Scope |
| --------------- | ------- | ----- |
| `evidence-publish-cpu-r8.tar.gz` | `7048106debde7fa44e4b5316ec441f95100fbdca4e3dae7daa115e64e18c2b34` | Final integrated CPU logs/XML, source/artifact identities and the preceding assertion-link failure. |
| `evidence-publish-cpu-r6.tar.gz` | `09d3e296589728f1bf615e832fdd0141f1d4f884d95025d4b2fe8b19bd4ccb56` | Earlier 186-target CPU snapshot and earlier build/tooling failures; retained historical evidence. |
| `hbg-evidence.tar.gz` | `31058c27db03f24414daa5ffdb0c9b92bc52abc7e01f9b58b2d5beceb77a1fe2` | Actual A5 HBG four-negative/226-case targeted proof, before final formatting. |
| SM-copy A3 diagnostic bundle | `c36340b5fcddced4bd03127359cfa3c17771a79507f313bbd0d6e464141b4290` | Complete R1-only and same-replay SM pairs and execution identities. |
| SM-copy A5 diagnostic bundle | `fd27bef1d94a443484881550a8bccdc14717a415285563d23662c41dd83944cd` | Complete SM pairs including the preserved strict R1-only difference. |
| Final v3 NPU bundles | Main, HBG, busy and actual-SDK bundle identities are tabulated below. | Full source/component and raw-region verification completed; distinct experiments retain distinct identities. |

Bundle names and hashes identify retained audit evidence; they are not public download links. Original failed assertions, setup failures, skipped/deselected counts and negative controls are retained alongside accepted results. No download location is claimed for a retained private raw bundle. No merge, deployment, automatic recovery or failed-context reuse is implied by this report.

## Actual-SDK error/ownership regressions

Three existing public capture cases ran in independent processes on each actual architecture:

| Case | Required result | Observed on A3 and A5 |
| ---- | --------------- | --------------------- |
| `host_submit_failure` | Accepted Core submission followed by execution-dispatch API refusal; retry stops before another enqueue; committed ledger retained. | Original `-4334`, then `-1003`; exact positive ledger unchanged before/after both errors. |
| `init_fail_handshake` | Registration submission refused; later prepare/launch rejected; no forbidden synchronization; explicit external drain before close. | Original public PASS marker and process exit0. |
| `close_fail_free` | Free refusal after completed execution retains accounting across retry; removing injection permits correct close. | Original public PASS marker and process exit0. |

The failure observer now skips the 16-byte context-only begin/end packets while keeping the execution-dispatch injection armed. Without that test-only adjustment, the added admission prelude consumed the injection before Core submission. A5 explicitly uses the A5 compiler, binaries, Core source and platform header. The private adapter changes four architecture literals in memory and removes only the A3-specific FFTS-member comparison, because A5 KernelArgs has no such member. Runtime/regs residency checks and all other assertions remain. This is actual A5 SDK coverage, not a claim that the public A3 pytest marker selects A5.

| Platform/device | Task | Results | Raw archive SHA-256 |
| --------------- | ---- | ------- | ------------------- |
| a3/device 0 | `task_20261017_221217_146279617302` | 3/3 exit0, all PIDs exited | `fa345e0a4fe9f8f635d697e96b0e3ab914935ed6c0cd6bb35f1d733cba3e26ab` |
| a5/device1 | `task_20261018_131105_32832815345` | 3/3 exit0, all PIDs exited | `3361c37a7c1072e91370d8dd71f61123f95b31f28079777fe6ee245f3c1434ac` |

Host launch acceptance can remain unknown after a failed SDK submission. That case retains resources and is not treated as the known-unattempted-CPU cancellation branch. CPU failure-point tests prove that branch's publication/error handling; device early/late cases independently prove the responder and OPENING ownership behavior.

## All-core silence: measured helper distributions

The measurement is actual production retirement-helper entry to return, with private same-domain CPU counter stamps; it excludes compilation and Host synchronization. Every listed invocation retains all targets, broadcasts EXIT, has no current acknowledgement and closes no silent target. There are three samples per path; the linearly interpolated P95 at `(n-1)*0.95` is descriptive, not a population estimate. The diagnostic instrumentation is not normal-path latency evidence.

| Actual path | Targets | n | Mean (s) | P95 (s) | Min (s) | Max (s) |
| ----------- | ------- | - | -------- | ------- | ------- | ------- |
| A3 HBG | 72 | 3 | 1.000004240000 | 1.000005892000 | 1.000002600000 | 1.000006100000 |
| A5 TMR | 96 | 3 | 1.000008698333 | 1.000009808400 | 1.000006811000 | 1.000009850000 |
| A5 HBG legacy | 96 | 3 | 1.000005530000 | 1.000010036600 | 0.999999384000 | 1.000010395000 |
| A3 TMR supplemental | 72 | 3 | 1.000002886667 | 1.000005144000 | 1.000000740000 | 1.000005440000 |

A3 HBG uses a 50MHz counter; A5 HBG uses 1GHz. Each span uses its own recorded frequency. The A5 HBG value 0.999999384s is retained: the absolute deadline was established 1,769ns before helper entry and return was 1,153ns after that deadline, so the remaining budget plus overshoot is 999,998,231+1,153ns. It is not an early acknowledgement or a truncated sample.

The first HBG collector searched only redirected Host native.log and returned exit1. Actual onboard retirement LOG_ERROR records were in the matching PID's CANN device dlog. The accepted proof retains each original failure and independently checks those full device logs against the sole PMU1 fault invocation, all unique targets, register values, start/end/deadline and frequency. It does not combine unrelated clock domains to manufacture ordering; no runtime/source change or NPU rerun was needed for that collection correction.

The 1.2s late-ACK controls take 1.000023860s on A3 and 1.000049954s on A5 at the helper boundary; these higher values are retained separately from the silent three-sample distributions. The production helper checks its absolute deadline after a complete target sweep, then executes the final close/release decision pass. In silent mode COND stays IDLE, so the sweep skips GM ACK reads; in delayed/late mode COND is already EXITED, so each unacknowledged target additionally invalidates and reads its owned ACK line. This locates deadline-check granularity and the distinct polling path. No per-read trace was collected, so the extra tens of microseconds are not attributed quantitatively to a particular MMIO/cache operation or presented as a second per-core timeout.

TMR current-ACK controls use old ACK 77 and request 78. A 250 ms delayed current ACK permits all 72/96 post-close Core returns. A 1.2 s late ACK is observed changing from77 to78 after the helper's failed one-second deadline but before outer synchronization; release remains0 and no Core post-close return appears. The caller requests an 8,000,000us operator watchdog; the actual API receipt is 8,589,934us on both platforms. That outer watchdog and stream synchronization are separate from the one-second retirement helper; neither proves execution stopped.

## Production component identity

The following are canonical production TMR components, independently identified as loaded by the SDK regressions. Diagnostic native/soft/unsafe-clear components have separate source and artifact maps in the retained archives. They must not be substituted for these canonical identities.

| Platform | Component | SHA-256 |
| -------- | --------- | ------- |
| a3 | `libhost_runtime.so` | `78bb4e5eb0b6c2d9eebaddea2b33df29fff5bf88159d4dcae503decafbdf3de2` |
| a3 | `libaicpu_kernel.so` | `d1501b2bb509b99fc01b2f39a6efa2b13d897135e485accc8cda6edc34c6552e` |
| a3 | `aicore_kernel_mode.o` | `38bbfbfbf2737d89ffe32c27dd2e92b383c27090a1b35cb05b3fa0851e425255` |
| a3 | `libsimpler_aicpu_dispatcher.so` | `f8540e44f41c78371fe66f006105b58233979178524d6ac91ea5ed0c2db5b84a` |
| a5 | `libhost_runtime.so` | `d08a1868dc5c78db0290f20974b0a34c5531ac79aae8303a57987d725364c9a4` |
| a5 | `libaicpu_kernel.so` | `c995398cdaabcb09b539a613015faf05b3c0413fb72509dec98cc5179fdab93e` |
| a5 | `aicore_kernel_mode.o` | `fdcc3427103fef68aa5fc03a96153cf88545572c215b733e56cf2e7bd9013ea0` |
| a5 | `libsimpler_aicpu_dispatcher.so` | `3581ce6d8a86d1330705c72863863dbb13f0e99812904ed12268513b91157258` |

Private busy source, trace snapshots, launch omission, native transport suppression and deliberately unsafe-clear variants remain outside the production patch. The first default-cohort busy attempt enqueued successfully but never entered the extra begin while all six native slots were occupied; SDK stream-timeout507046 with fault 0 is retained as an injection-not-executed setup failure. It is not counted as a product rejection or a passing adversarial case.

## Final v3 fault matrix: independently decoded results

The main rest batch has 25 fault processes and 26 independent canonical healthy processes per platform: 15 matrix controls, four early/late controls and six TMR ACK/retirement controls. That is 102 completed rest results, plus eight Program PMU results, independently replayed from retained raw data. The 52 canonical healthy processes execute 1,040 captured replays. Busy uses a separate allocation/configuration and is counted separately below.

In normal native matrix controls, only R1 enters: begin=1, clear=1, prepare=1, native entries=6, OPEN=72/96 and no successor payload. Each forced-success control actually executes three begin nodes, 18 native entries and three epilogues, with every Core entering three times; clear/prepare stay1 and each Core is admitted only for R1. These counters distinguish internal rejection from SDK simply skipping R2/R3. Soft success belongs only to the private transport override.

Every deliberately unsafe variant executes the same successor entries but clears four times; both control and reports become all-zero and fail the protected-state oracle. The negative control succeeds only as a corruption detector. SM, arena or runtime retention cannot hide those two detected corruptions.

| Platform | Scenario | Normal native stream API statuses | Native / soft / unsafe-clear acceptance | Native SM changed offsets | Soft SM changed offsets |
| -------- | -------- | --------------------------------- | --------------------------------------- | ------------------------- | ----------------------- |
| a3 | eager | `[507018, 507018]` | pass / pass / corruption detected | `[792]` | `[]` |
| a3 | graph-chain | `[507011, 507011]` | pass / pass / corruption detected | `[792]` | `[]` |
| a3 | same-replay | `[507011, 507011]` | pass / pass / corruption detected | `[]` | `[]` |
| a3 | two-graphs | `[507011, 507011]` | pass / pass / corruption detected | `[792]` | `[]` |
| a3 | cross-stream | `[507011, 507011]` | pass / pass / corruption detected | `[]` | `[]` |
| a5 | eager | `[507018, 507018]` | pass / pass / corruption detected | `[792]` | `[]` |
| a5 | graph-chain | `[507011, 507011]` | pass / pass / corruption detected | `[792]` | `[]` |
| a5 | same-replay | `[507011, 507011]` | pass / pass / corruption detected | `[]` | `[]` |
| a5 | two-graphs | `[507011, 507011]` | pass / pass / corruption detected | `[]` | `[]` |
| a5 | cross-stream | `[507011, 507011]` | pass / pass / corruption detected | `[]` | `[]` |

A nonzero stream return is the caller's failure boundary. Both actual SDK headers define507018 as `ACL_ERROR_RT_AICPU_EXCEPTION` and 507011 as `ACL_ERROR_RT_MODEL_EXECUTE`. Eager execution exposes the former; graph executions return the latter at the stream boundary. Its integer value is retained per API/path; a lower native error and the graph API's returned error are not collapsed into one code. The persistent failed R1 identity, actual entry counters and protected-state evidence establish the protocol cause separately.

Across the 38 final matrix and early/late SM pairs, 32 are strictly identical across all 1,272,704 bytes. Six retain only the proven R1 scheduler diagnostic transition at byte792, 0→5, with orchestration word784 already5 and every other byte identical. They remain `strict_sm_equal=false`. The following are those six cases; all other pairs are exact:

- a5: `matrix-native-eager-1`.
- a5: `matrix-native-graph-chain-1`.
- a5: `matrix-unsafe-clear-eager-1`.
- a3: `matrix-native-eager-1`.
- a3: `matrix-native-graph-chain-1`.
- a3: `matrix-native-two-graphs-1`.

Control/reports/arena/runtime use device-snapshot FNV plus complete after-region bytes/SHA; these four regions are not described as a before/after full byte memcmp because only the SM has a complete retained before-copy. Private unsafe-clear controls confirm that the control/reports oracle detects its deliberate violation. The SM comparison independently recomputes the copied hash and compares every byte, with no general field/line mask.

| Platform/device | Accepted rest task | Accepted PMU task/device | Raw bundle SHA-256 |
| --------------- | ------------------ | ------------------------ | ------------------ |
| a3/device 0 | `task_20261017_215228_12408185647` | `task_20261017_214032_110644412019` / device 0 | `be71ed231727845e4bc807b8038dec233bf68aba979b29abb8d061ac59959a8d` |
| a5/device 0 | `task_20261018_125112_292169825031` | `task_20261018_123913_21324177474` / device1 | `2c3610c93a57199639bf88e24828d68a88a6e1f231a5a1844ae688002cbe6353` |

The main/PMU archives retain all per-case raw regions, snapshots, original native logs, component maps, source inputs, health and process-exit records. The independent verifier checks every member against its manifest, canonical 2,596-file source input and actual loaded component binaries, and confirms all 55 oracle PIDs per platform have exited. The root workflow reran that verifier successfully for all 110 cases. Process exit is cleanup evidence and is not promoted to device-stop proof.

Program PMU fault wall times are recorded below as single observations, not runtime benchmarks. Each fault has a real healthy PMU seed and CSV with positive counters. Each fresh recovery runs two healthy golden iterations with PMU output and closes normally; these earlier probes make no explicit close, free or retry call on the failed Worker; automatic native destruction after the observations is not excluded.

| Platform | Explicit fatal | Missing-core-report startup | Original cause / independent recovery |
| -------- | -------------- | --------------------------- | ------------------------------------- |
| a3 | 0.008688414s, code -9 | 2.009920237s, code -100 | Original cause retained; both fresh PMU recoveries pass. |
| a5 | 0.026366290s, code -9 | 2.024182480s, code -100 | Original cause retained; both fresh PMU recoveries pass. |

Setup failures remain outside these counts: initial strict SM fingerprint failures led to the complete-copy/R1-only diagnosis; default six-native busy injection never executed; HBG initially searched the wrong log channel; private builds had a branch API/header mismatch, an observer include/TMPDIR error and an editable-module-origin mismatch. Corrected collection/setup has its own recorded identity and does not rewrite the original failed result into a pass.

## Busy overlap: actual independent begin and in-flight failure propagation

The default six-native experiment could not execute an extra independent begin while R1 occupied all six AICPU slots. Its successful enqueue, fault 0 and stream-timeout507046 remain a setup failure. The accepted experiment selects a protocol-legal four-native/two-execution cohort in a private Host before descriptor publication. It keeps the actual topology/allowed CPU IDs and every physical Core worker. A private AICPU observation counts real request capture and real return; it changes no product completion/control state. Core/dispatcher and all other components are byte-identical to the matching v3 diagnostic variant. These hooks are excluded from the production PR.

Each platform first completes a real four-native healthy warmup with golden output. Before the extra begin, all four R1 requests must be captured and every Core must have observed OPEN. The actual device begin counter must increment 1; an SDK enqueue count alone cannot pass. The saved begin descriptor/generation and distinct begin/end handles are checked against the actual warm launch.

| Platform/device | Task | Actual begin / captured R1 | Native busy caller | Soft requests / returns / snapshot marker | Soft Core post-close returns | Raw archive SHA-256 |
| --------------- | ---- | -------------------------- | ------------------ | ----------------------------------------- | ---------------------------- | ------------------- |
| a3/device 0 | `task_20261017_222131_158290226091` | +1 / 4 | `507018` | 4 / 4 / 2 | 72 | `18e9dcf32187096d0a195c5dda5a6ffea93f422cde962857ac61dfbd1e6a6b66` |
| a5/device 0 | `task_20261018_132758_355022831392` | +1 / 4 | `507018` | 4 / 4 / 2 | 96 | `691dc996ca039b5f2bf9163d6f2ca8ce4e14a29ff46c564d882d292074de6507` |

In soft transport, all four actual R1 dispatches return through the instrumented tail before the complete SM copy is taken. That marker is 2, explicitly not product Final; both platforms retain the observed product completion 0. All R1 protected writers have passed the tail, but the last native has not returned to RTS yet, so dependent R2/R3 cannot execute until the copy is complete. Rejected successors return above the private capture/return counters and cannot counterfeit four R1 departures.

Subsequent soft execution observes begin increment 4 (including the independent busy begin), native-entry increment 12, three epilogues and three entries per Core. Thus R2/R3 actually run their guarded entries. Clear and prepare each increment 1, OPEN belongs only to R1, no child payload executes and the producer's first fatal check permits zero submit attempts/zero additional scheduler dispatches. All 72/96 Core post-close returns are witnessed. At this later boundary both complete 1,272,704-byte SM pairs are strictly identical, including orchestration/scheduler error words both 5; the earlier post-Final single-field allowance is deliberately not used. Control/reports/arena/runtime retain their strict snapshot fingerprints and complete after-region SHA.

Native transport observes actual busy entry and error 507018, failed odd lease 3/fault 1, no successor clear/prepare/OPEN/payload and unchanged positive committed-resource accounting. CANN can cancel R1 before a product Final/return snapshot; the native test does not require or fabricate one. Both transports retain the failed context and do not free/close/reuse it; the experiment does not promote an error to a general device-stop guarantee.

Each busy allocation has an initial canonical control plus one fresh canonical recovery per fault, six independent healthy processes/120 replays across both platforms. Together with the main 52 healthy processes, this is 1,160 current-input canonical captured replays; Program PMU and HBG healthy seeds/recoveries remain separate. Private four/two warmup correctness is additional evidence, not a claim that an extra default six-native task executes concurrently.

The initial private SDK build stopped at a source-origin assertion because an old editable finder selected another tree. A separate venv then loaded only the intended environment/builder/compiler/simpler modules, preserved original failed logs and rebuilt only Host/AICPU. The first A5 pending request also had the wrong submission cwd/policy and never executed; it was formally cancelled and replaced from the correct topic directory. The accepted A5 request explicitly records pool/whitelist 0–3, ignore-whitelist 0, actual device 0 and the cancellation receipt/not-found status of the old task. No other task was cancelled and no CI card was used for these experiments.

| Additional retained proof | SHA-256 |
| ------------------------- | ------- |
| a3 HBG full raw/posthoc evidence | `7eefdcf8a9cc9b72d04a8c86cad9677b87b68fa1ff1547ee4582155df16cd50a` |
| a5 HBG full raw/posthoc evidence | `349aa11af48a1ed91f5b04a89a4e5624090f828c759bdbe4ba13863f729dc0e5` |

The independent busy verifier checks all raw members, original/canonical/private source and actual binary hashes, real request/return/entry counters, strict SM/FNV, caller errors, committed retention, board/health, all five process exits per platform and the A5 device policy. It does not use recorded pass_oracle flags as its acceptance condition. The root workflow also replays the final verifier. All diagnostic inputs and original failed collection/setup records remain retained outside the production source.

## Additional A5 HBG resident lifecycle: review finding and closure

The final call-graph review found a fourth lifecycle beyond the issue's historical three trees. A supported ordinary public Program graph with one subtask, one block and no sync-start is assigned `RESIDENT_PENDING` directly by `create_scheduler_state`; the actual AICPU dispatcher then runs the resident executor. Public Kernel HBG being unsupported does not exclude this Program path. Both resident initialization-abort and normal finish still called the one-core deinitializer in a loop. The publication was held before staging or pushing so this actual omission could be fixed and verified.

The final change preserves normal shutdown's partition-wide EXIT signaling, existing cross-partition signal barrier and subsequent join. A per-core atomic claim permits one EXIT and one join attempt. The first nonempty signaling phase publishes one absolute deadline shared by all partitions and both cleanup entry points. The COND group helper defaults to broadcasting for its existing legacy caller; resident supplies `send_exit=false` after its own signaling phase. Initialization-abort broadcasts its own partition before joining; no new global pre-join abort barrier is claimed. A subsequent cleanup of already claimed targets adds no work and does not establish that a failed core stopped.

Only an observed COND acknowledgement permits close, per-window readback and drain. Only the resulting closed worker IDs may be passed to PMU finalize or profiling flush. PMU finalize restores MMIO CTRL registers; profiling flush also mutates pending/shared buffers, so neither operation is valid on an unacknowledged target. PMU initialization completion is tracked for this invocation, and an abort before initialization cannot restore stale PMU state. The public Program Host prepares PMU storage and stops submission when collector initialization fails before the AICPU task is launched; this is a required precondition of the device collector's initialization API.

Partial handshake failure retains each already validated physical-core/register target immediately, so a missing peer cannot discard known ownership. Unknown or invalid reports do not acquire an invented register address. On AICore, COND is set to IDLE and a barrier completes before publishing the current startup report. Host preparation clears startup reports before launch. Consequently an initialization abort may not interpret the previous invocation's retained EXITED as this invocation's confirmation. This is an invocation handshake plus COND protocol, not a TMR GM request/ACK nonce or a claim that HBG supports arbitrary concurrent replay.

### Actual production CPU reproduction and final integration

The original three-core lifecycle test consumed 306 virtual ticks for a 100-tick budget. Eleven of twelve actual lifecycle regressions failed on the old code; the supported-mode marker control passed. Separately, the full production Core translation unit was run with a retained EXITED register: both AIC and AIV tests failed after publishing the current report, because COND still carried the old value. Both pass after the production ordering change. The test then sends a real pre-READY abort through scheduler error and observes the actual Core exit path; it is not a source-text assertion.

The final assertion-enabled focused run passes nine targets and 168 cases: resident retirement 12, actual resident startup 2, legacy retirement4, resident contracts 17, ready 35, dispatch 26, A3/A5 retirement 27 each and A5 GM ACK 18. Mixed-ACK tests verify that only closed IDs are finalized, all-silent PMU/profiling targets are untouched, repeated cleanup does not repeat EXIT/close/finalize, and partial initialization retains only known targets. The complete subsequent r11 run rebuilds simulation/package, passes normal hooks for all 84 changed paths, builds all C++ tests and passes the actual CI selection `ctest -LE requires_hardware -j4`: 189/189 targets, including 26 older unlabeled tests. Python UT passes 2548 with 79 hardware cases deselected and one existing torch warning. The entire 2599-file r11 source map is unchanged by this validation. Final report prose is a separately checked documentation delta.

| CPU evidence | Task / archive SHA-256 |
| ------------ | ---------------------- |
| Actual lifecycle valid red | `task_20261017_230336_208587825803` |
| Actual Core retained-EXITED red/green | `task_20261017_231251_224987413699` |
| Final nine-target assertion-enabled green | `task_20261017_231604_228794923079` |
| Focused full original evidence | `d8575f18d1889f584df068bf079f90aac3f4425498405e8a2ddc41e5287bea63` |
| Full r11 CPU/sim/hooks/UT | `task_20261017_231816_232796718588` / `f2c64998131a1b3f958a4e7ffa3f71a703fdcd9f2b9378c3a191dc677a46e346` |

The first lifecycle/Core test-link setup failures, two editable-import source-selection failures and all valid red XML are retained. Normal hooks eventually run against the verified intended source without skipped checks or disabled assertions.

### New A5 resident SDK and actual PMU fault results

The canonical SDK is rebuilt from the frozen resident source, with all 2598 input hashes, six runtime build-cache source roots, actual Python module origins and all twelve artifact identities checked. Its first build task completed SDK compilation but failed post-build collection against the older manifest; a second collector expected seven caches instead of six. Both original failures are retained. Corrected posthoc collection verifies the unchanged build without recompiling it. The final r11 tree adds a CPU Core regression and test/CMake formatting; all production source bytes match this canonical resident input.

The diagnostic AICPU adds only observations in three source files: resident lifecycle, COND helper and PMU collector. The finish/abort Core variants add one narrowly placed park each. Finish parks after real graph completion and receipt of EXIT, immediately before writing EXITED; abort parks after READY/context refresh but before bootstrap, causing the real two-second bootstrap deadline and `release(false)`. There is no private COND clear. Healthy Core is byte-identical to the canonical Core. Host and dispatcher are canonical in every variant. Private changes and raw bundles are excluded from the production patch.

Final task `task_20261018_143930_249244028156` uses the A5-DT development allocation, actual device 2, after architecture/pool precheck. Six fault processes each run a real diagnostic healthy PMU seed, then a fault invocation with 96 workers and two AICPU partitions. Seven independent canonical PMU healthy processes also pass golden output and close; all thirteen PIDs exit. No result is paired with the earlier device-1 batch for performance comparison.

| Case | Actual helper group s | Actual retirement method s | Host invocation wall s | Original caller classification | PMU started / stopped on fault | Closed targets |
| ---- | --------------------- | -------------------------- | ---------------------- | ------------------------------ | ------------------------------ | -------------- |
| abort-1 | 0.999974774 | 1.000989739 | 8.690999770 | `-100` | 96 / 0 | 0 / 96 |
| abort-2 | 0.999971977 | 1.000944493 | 8.682439360 | `-100` | 96 / 0 | 0 / 96 |
| abort-3 | 0.999978981 | 1.000986630 | 8.686654150 | `-100` | 96 / 0 | 0 / 96 |
| finish-1 | 0.999960628 | 1.000967028 | 8.687820210 | `507018` | 96 / 0 | 0 / 96 |
| finish-2 | 0.999952310 | 1.000979436 | 8.706451140 | `507018` | 96 / 0 | 0 / 96 |
| finish-3 | 0.999956725 | 1.000982853 | 8.684181910 | `507018` | 96 / 0 | 0 / 96 |

All six fault invocations observe the current startup report with COND IDLE, PMU initialization completed, DMB EXIT sent, and no acknowledged/closed target. Their real PMU start observations cover all 96 unique physical targets; PMU finalize/CTRL-restore calls remain zero. In contrast every diagnostic healthy seed acknowledges/closes all 96 and performs 96 PMU stop calls. The device experiment disables chip swimlane; closed-only trace flush is covered by the actual production CPU tests, not relabeled as device coverage. Resident CSV emission is best effort and is not used as a substitute for the actual PMU MMIO/stop observations. Earlier Program PMU scenarios separately validate positive CSV output.

| Entry and statistic, seconds | Mean | P95 | Minimum | Maximum |
| ---------------------------- | ---- | --- | ------- | ------- |
| finish, helper group, n=3 | 0.999956554 | 0.999960238 | 0.999952310 | 0.999960628 |
| finish, method, n=3 | 1.000976439 | 1.000982511 | 1.000967028 | 1.000982853 |
| finish, Host wall, n=3 | 8.692817753 | 8.704588047 | 8.684181910 | 8.706451140 |
| abort, helper group, n=3 | 0.999975244 | 0.999978560 | 0.999971977 | 0.999978981 |
| abort, method, n=3 | 1.000973621 | 1.000989428 | 1.000944493 | 1.000989739 |
| abort, Host wall, n=3 | 8.686697760 | 8.690565208 | 8.682439360 | 8.690999770 |

P95 uses linear interpolation at `0.95*(n-1)` and describes only these three observations per entry. Helper group duration is `max(group end)-min(group start)` on one 1 GHz AICPU clock. Both 48-worker partitions share the same absolute deadline. The deadline starts during signaling, before helper entry: each span satisfies `1s - pre-helper deadline lead + final scan overshoot`; all final ends reach or exceed that deadline. The slightly sub-second group spans therefore do not mean an early acknowledgement. Across these six cases the lead is 26877–50142 ns and the final overshoot is 2452–6149 ns. The method includes about 1 ms of private per-target logging and post-helper work. Host wall includes SDK error/drain handling and must not be reported as the one-second helper duration. Scheduler timeout is 2 s, requested operator timeout 8000000 us (SDK receipt 8589934 us), and stream timeout 10 s.

All Host high values are retained. Within this one allocation, finish-2 minus finish-3 adds 22.269230 ms of Host wall: runner-start to AICPU-error adds 17.745880 ms, error-to-failed-drain adds 1.796690 ms, drain-to-runner-end subtracts 0.574730 ms and work outside that runner interval adds 3.301390 ms. The helper is 4.415 us shorter. Abort-1 minus abort-2 adds 8.560410 ms: runner-to-error subtracts 4.176770 ms, error-to-failed-drain subtracts 2.379290 ms, drain-to-runner-end adds 7.444890 ms and outside-runner work adds 7.671580 ms. Its helper adds only 2.797 us. These exact per-call Host intervals locate the variation in error/drain/tail handling, rather than a per-Core retirement budget. Host CLOCK_MONOTONIC and AICPU counters remain separate domains; no absolute cross-clock alignment or unique hidden RTS-subfunction attribution is inferred.

| New resident evidence / component | SHA-256 |
| --------------------------------- | ------- |
| Canonical source manifest | `e76ebe1fc13244c9803e584d40bd07ee8fb66a339272be44bbee6ef8bfa4af9c` |
| Private observation source manifest | `ca1a6bfbe56b8b69b8d6d740a98f27372a258a888d76a50d22715dcc58127ae4` |
| Canonical / private Host | `b5b0ba5286ee98652b49f9dcf5558a887271dd1f0e686b498c66d0da50ba638f` |
| Canonical / private dispatcher | `79360594eba9973c350ef2f2782efd67c94d98552fd4d587065a286f681b58a9` |
| Canonical / diagnostic healthy Core | `7cb07990346c4582efacaa9eceecae3a75a66224403571b1bc93270ab2b374bf` |
| Canonical AICPU | `6b19d0ddeb241ce84902f0b433c7932325778e3fbf5eae305da0c26cafc24c93` |
| Diagnostic AICPU | `bd22b2aa4376e0b096dc2520489afa12e33f2a81ead7495c00ab6d49bbed55ba` |
| Finish park Core | `55818ff751eeb84d20af52a8a3f4a4757a0c74f6482d8b2291096340b2d636b8` |
| Abort park Core | `2d06cecf51b3e65386db08b35b55a29f39e7b40e8c88d27cd471232e5d93fc69` |
| Final full original raw bundle, 123051818 bytes / 5687 files | `cc9ac6cabdb79afb3f7ac4d336777a207c3b9f590c15581b8d464c4cfc85561e` |
| Independent raw verifier | `875dc967abdc55dae018c77d89846646d60316e307585d2b2df1abe87abb0df6` |
| Retained earlier reset-bearing batch | `a7a3b084713d3ad9455b4232be945aa09717c0fb0cc56547334f4ca221678829` |

The root review independently replays all 5687 raw members, canonical/private source maps and components, original process receipts and complete native/device logs using the frozen oracle. It recomputes each PMU/COND/deadline/ownership condition and does not trust saved pass flags. The earlier Python integer-property-as-method failure occurred before the fault invocation and supplies zero accepted fault measurements. Those six setup failures and the earlier reset-bearing batch remain separately retained.

### Ownership correction retained as a distinguishing control

An earlier valid resident batch completed six helper/PMU measurements, but the private script called `run()` before its outer `_exit`. Returning from `run()` released its local Python wrappers and eventually the native `ChipWorker`; the existing C++ destructor calls finalize, and an owned Program runner already marked unusable performs fatal cleanup and force-reset. All six original logs show that recovery. The post-fault positive ledger snapshot preceded it. That batch remains valid for its earlier helper/COND/PMU observations, but is explicitly rejected as evidence of quarantine through process exit. None of this reset behavior was introduced by the resident patch.

The final private batch globally retains the Worker, native wrapper, callable/handle/config/library, tensors, argument object and its second returned storage owner before any failing invocation. They remain live until `_exit`, bypassing scope-based destruction. The original complete logs are checked for absence of fatal force-reset and ownership-clear markers, while the old real logs must fail the same predicate. This proves the caller-held lifetime case for this experiment; it does not change or relabel the default owned-Program destructor policy, and `_exit` does not prove physical Core stop. A healthy seed is normally closed, which can tear down/reset its owned device: its EXITED snapshot followed by the next report's IDLE is not claimed as an old value persisting across that close. The independent actual-Core CPU counterexamples establish retained-EXITED rejection.

### Exact evidence reuse boundary after the resident fix

The final production delta from v3 comprises five A5 source files: resident lifecycle header/implementation, resident Core implementation, and the COND helper header/implementation. All 305 common files, 130 A2/A3 files and 54 A5 TMR runtime files remain byte-identical to v3. The complete A5 TMR current-ACK helper function in the shared platform translation unit also remains byte-identical. Existing legacy calls retain the COND helper's default broadcast branch; resident alone uses its explicit join-only branch. Both branches are covered by actual production CPU tests.

Historical v3 device results above remain bound to their own source/components. They are not relabeled as new resident measurements or as byte-identical final A5 binaries. The additional resident source receives new full r11 CPU/sim validation, a new A5 SDK and the separate actual hardware results above. The runtime compiler's build-root and shared-translation-unit changes can alter component hashes even when a particular function's source is unchanged.

### Precise remaining software-wait and resource boundaries

This work does not make every ordinary HBG Program startup phase internally clock-bounded. Concrete older A3 HBG and A5 HBG legacy setup, handshake-arrival, initialization-completion and classification barriers still contain software waits without their own elapsed-time check. They are distinct from the TMR native membership/startup waits fixed here and the measured resident/HBG/TMR retirement helpers. The onboard Program normally configures a CANN op watchdog (default 45 s) and a Host stream synchronization timeout (default 50 s), subject to configuration; the op-timeout setter can fail and only log, so its protection is conditional on successful SDK setup. A finite Host synchronization error does not prove a core stopped.

The screenshot's Kernel illegal-replay contract is therefore supported within the stated launch/completion rules, while this broader ordinary-Program startup boundary remains explicit. No arbitrary-user-code termination, physically wedged MMIO bound or automatic failed-context recovery is promised. Failed leases and uncertain execution require quarantine and the caller's supported stop/drain/destroy contract; new-process correctness, card health, process exit or an error alone cannot authorize reusing failed storage.
