# Native Tailscale conversation implementation

Status: option 1 selected. This is the detailed execution plan; implementation
has not started. The [research record][research] contains source pins, protocol
findings and alternatives. The [speech results][baseline] remain the comparison
and recovery baseline. Checkbox completion requires retained evidence.

## Selected scope

The robot joins Tailscale through pinned MicroLink and contacts a small gateway
on `gianrtx.tail8e80d.ts.net`. The gateway calls the existing local Nanbeige
Ollama alias. Ito synthesis and the original face stay on the ESP32.

Open-ended English STT on the ESP32 is the preferred recognition path. Probe
Oído v2b before committing to its flash layout or lifecycle work. If local STT
fails the memory or accuracy gate, use the already-selected resident Parakeet
fallback on gianrtx. Report which recognizer the actual demo uses.

The first wireless milestone is a text request from the ESP32 over its own
tailnet connection, followed by local speech. A complete voice milestone adds
the real microphone and the selected STT. Neither requires a nearby computer
to forward application traffic. DERP is a valid encrypted fallback within
native Tailscale; it does not turn the Mac into an application relay.

Use half-duplex capture and playback, one turn at a time, and complete short
text replies before starting Ito. Retain bounded PCM streaming. Do not add
full-duplex echo cancellation, motor movement, tools, always-listening services,
new cloud inference, or a full Xiaozhi backend to this implementation.

## Memory question and minimal UI candidate

The user asked whether removing touch and menus can give STT more memory while
retaining the face, physical power control, restart and reset. Measure this as
a separate candidate; selecting native Tailscale does not authorize a UI rewrite.

### What the existing artifact establishes

| Item | Bytes | Interpretation |
|---|---:|---|
| Linked static DIRAM, whole existing image | 108,163 | Code/data in internal RAM, not application flash size or runtime heap. |
| Free internal after face, before codec/Ito startup | 66,422 | Measured with the early hot arena already reserved. |
| Early Ito hot arena | 239,948 | Internal SRAM; reserved before UI initialization. |
| Above free heap plus reservation | 306,370 | Arithmetic estimate, 299.19 KiB, not a measured no-Ito build. |
| Free PSRAM after face, before codec/Ito startup | 8,271,320 | Measured, 7.888 MiB. Excludes future radio/capture/inference. |
| Ito runtime/frontend static DIRAM | 14,809 | Existing linker-map attribution. Removing them changes the layout. |
| Ito runtime/frontend external BSS | 72,580 | Existing map attribution, not dynamic arena usage. |
| Active Ito weight copy | 3,196,160 | PSRAM copy including 64-byte margin. The source weights are stored in flash. |
| Ito bulk arena | 1,579,920 | PSRAM working storage. |
| Six Ito PCM buffers | 115,200 | PSRAM, retained for streaming playback. |
| Quiet-text test scratch | 576,000 | Lazy diagnostic allocation, distinct from ordinary spoken playback. |

Source methods are the retained serial session, existing linker map and runtime
allocation sites. No stripped firmware was built or booted for these estimates.
The exact no-Ito footprint and largest free block need a dedicated build/run.
Do not add linked-section savings to an estimated heap value and label the sum
as measured. Internal SRAM and PSRAM are separate budgets.

The measured face-creation increment is 464 B internal and 9,628 B PSRAM.
LCD/LVGL initialize earlier, so this is not the entire display/face cost.
Keeping the original face also keeps the existing 7,168-byte LVGL task stack
and 5,120-byte LCD DMA buffer, plus renderer state.

The local cold-boot path already skips installing launcher apps. Removing their
source mainly reduces flash; it does not reclaim an active launcher's heap in
the measured speech mode. LVGL, its port, Smooth UI and Mooncake together account
for only 556 B of static DIRAM in the existing map. Dynamic costs are separate.

Touch polling uses the shared ESP timer task, so there is no dedicated touch
stack to remove. Treat touch-only savings as small and unmeasured, not tens of
kilobytes. The 2 MiB image-cache setting is a capacity limit, not evidence of a
resident 2 MiB allocation. Removing it cannot be booked as a guaranteed saving.

### Candidate comparison to run

| Candidate | Keep | Change | Purpose |
|---|---|---|---|
| A: existing face, no Ito start/reservation | Original display, face, board, USB, power | No speech runtime initialization | Establish the real base footprint and largest blocks. |
| B: face and hardware controls | Same renderer, PMIC, watchdog, codec hooks, USB | No touch polling/input, Home/status widgets or launcher integration | Measure the user's proposed simpler shell without copying the face. |
| C: phase-owned speech workspace | Candidate A or approved B | Release or lend TTS resources only while synthesis is stopped | Recover the large inference budget for STT and networking. |

Test B only as an isolated diagnostic until its interface is selected. Keep the
one-time FT6336 controller identification needed to select ILI9342C versus
ILI9342E initialization, or replace it with a verified board-specific choice.
Do not remove a shared timer callback without preserving needed PMIC polling.

Candidate C offers the largest budget change: the hot arena is 234.32 KiB and
the PSRAM weight copy plus bulk arena total 4.555 MiB. These remain allocated
in the current service even after cancel. Safe reclamation needs code and tests.
Keeping both engines resident is acceptable only if measurements prove fit.

Preserve the physical power button and RST behavior. Manufacturer documentation
specifies click for power on, hold for power off, RST click for reboot and RST
hold for download mode. Power-click events come through the PMIC, not a spare
GPIO. Verify event/hold behavior before assigning recording or menu actions.
Never use GPIO0 as a spare button input; it is the audio master clock.
[Hardware controls][buttons], [button event API][button-api].

A basic on-screen menu can remain display-only, with USB configuration first.
The proposed hardware interaction is one power-button click to start/submit a
recording, and a click during speech to cancel, only if PMIC event tests pass.
Keep hold-to-power-off and RST semantics. Do not add a destructive reset gesture.
If menu navigation needs another independent button, decide between an external
Grove button and USB navigation rather than assuming RST is available as input.

## Repositories and working boundaries

| Repository | Existing boundary | Proposed additions |
|---|---|---|
| Ito | `esp32/runtime/itofs_service.h`, `esp32/firmware/main/main.c`, `kernels_s3.c`, host runtime tests | Only measured lifecycle/ownership changes, a host USB bridge test, canonical results. |
| StackChan | Board/codec/display adapters under `firmware/main/hal/board/`, `main/local_ito.cpp`, `repos.json`, local build script | Conversation profile, capture, MicroLink transport, turn controller, optional minimal shell. |
| local-voice-agent on gianrtx | `config.py`, `llm.py`, `resident_stt.py`, `server.py` and `telemetry.py` | Independently launched text gateway, optional PCM transcription adapter and focused tests. |

New filenames below are proposed, not existing commands or completed APIs.
Run `wt list` in each repository, reuse suitable task worktrees and preserve
unrelated changes. Use feature branches. The Linux repo explicitly requires no
PR; respect that exception. Keep the current StackChan and Ito artifacts intact.

Commit logical units after their checks. Add short decision records to the
existing Agent Notes lifecycle directories. Move an implemented decision note
only after its relevant device gate passes; research findings remain proposals.

## Task 1. Freeze inputs and prepare reproducible experiments

- [ ] Refresh clean Git state, dependency revisions, USB identity, Linux listeners
  and tailnet address. Detect an existing monitor before opening the serial port.
- [ ] Record the exact baseline app hash, Ito model hash, IDF version and existing
  partition/NVS map from the canonical results and private manifests.
- [ ] Pin MicroLink `216da3300f0493b0860247d43f7af5ce29df63a5` and Oído
  `c8d60325ba8bffd4bad65a9ac63c713ee64d1aae` for the probes. Pin any corrective
  patch in the dependency mechanism; never depend on ignored checkout edits.
- [ ] Create private experiment directories outside build output. Give each
  run a manifest with profile, code/config/model hashes and test case IDs.
- [ ] Add a reusable stage-memory snapshot in the experimental profile: internal,
  DMA-capable and PSRAM free/minimum/largest block, task stack watermarks and
  audio overflow/underrun counters. Do not infer contiguous fit from totals.

Existing read-only checks can be repeated before changes:

```bash
git -C /Users/gianpaj_it/tmp/ito.docs-stackchan-ito-plan status --short
git -C /Users/gianpaj_it/tmp/StackChan.feat-local-ito status --short
ssh gianrtx 'git -C /home/gianpaj/github/gianpaj/local-voice-agent status --short'
ssh gianrtx 'tailscale serve status'
ssh gianrtx 'ss -ltnp "( sport = :3000 or sport = :7860 or sport = :11434 )"'
```

Deliverable: baseline manifest and per-profile allocation estimates. A reviewed
static budget and recovery path allow isolated instrumented probes. Measured
subsystem peaks are required before combining them.

## Task 2. Implement the smallest Linux text gateway

Proposed files are `apps/agent/src/local_voice/stackchan_server.py`,
`stackchan_turns.py`, `tests/test_stackchan_server.py` and
`tests/test_stackchan_turns.py`. Reuse configuration/telemetry helpers where their
dependencies remain small. Do not instantiate the existing browser pipeline,
Phonon or resident Parakeet for a text-only process.

### API contract

| Route | Behavior |
|---|---|
| `GET /health` | Authenticated readiness for this gateway and selected LLM; GET does not trigger model loading. |
| `POST /v1/turn` | Accept bounded JSON text and session/turn IDs; return matching IDs, spoken answer text and timing metadata. |
| `POST /v1/cancel` | Cancel only the authenticated device's matching active turn; return a terminal outcome. |
| Optional `POST /v1/transcribe` | Added only for selected remote STT fallback; bounded 16 kHz mono int16 PCM. |

Use one small authenticated protocol. Start with a 4 KiB JSON request limit,
2 KiB answer-text limit, one active inference and 30-second generation timeout.
Keep the existing 4,096 context and 128-token reply policy. Retain the installed
Nanbeige alias and reasoning suppression. Reject empty or non-spoken output;
do not speak private reasoning or treat arbitrary JSON as a console command.

Keep recent turn outcomes in bounded session memory for duplicate detection.
The robot plays each turn at most once. Server restart invalidates a session;
require a new explicit turn rather than silently replaying an uncertain request.
No database or durable conversation store is needed.

- [ ] Test limits before inference, wrong credentials, busy, malformed JSON,
  duplicate IDs, late output, timeout, disconnect and concurrent cancel.
- [ ] Close the owned Ollama response on cancel. Test resource cleanup and an
  immediately following successful request. Do not unload unrelated models.
- [ ] Test warmup readiness, empty output and loss of the selected loaded model.
- [ ] Run one real cold request and at least ten warmed fixture requests. Save
  model identity, first-answer/completion time, output length and GPU memory.

Use an unused loopback port for the first probe, for example 8767 if it is still
free. Reach it from the Mac through an SSH local forward over Tailscale. Before
device testing, bind the dedicated authenticated gateway to the current Linux
Tailscale address on an unused port. Ollama calls stay on loopback. Preserve
existing Serve 8443/4702/8080 and the process occupying port 3000.

If HTTPS is selected later, add a separate Serve endpoint and test its exact
URL. Native HTTP over WireGuard is the initial lower-memory transport candidate.
Never expose the raw Ollama API as the robot's public endpoint.

Proposed private configuration includes gateway bind address/port, selected
model, log directory and a credential-file path. Keep the device credential out
of argv, saved request fixtures, Git and ordinary logs. Finalize names in code
and provide a secret-free example. Do not change global Ollama configuration.

Gate: host client obtains real bounded answers, cancellation works, and the
gateway starts/stops independently of all existing services.

## Task 3. Demonstrate LLM answers through working USB speech

Proposed host helper: `esp32/host/stackchan_turn.py`. Reuse the existing serial
helper's port selection, logging and READY/busy handling where possible.

- [ ] Send public English text to the gateway, parse its answer and pass only
  validated answer text into Ito's `text` path. Never forward raw response lines.
- [ ] Wait for the current speech job to finish or cancel before submitting a new
  answer. Match session/turn IDs before every submission.
- [ ] Test a delayed answer arriving after cancel and after a newer turn.
- [ ] Speak a greeting, numbers and a two-sentence answer. Check physical speech,
  mouth start/stop and stationary motors. Keep the microphone off in USB mode.

Gate: repeatable Linux LLM -> USB Ito speech. Label this early demonstration as
host-assisted; it does not pass native Tailscale membership or microphone tests.

## Task 4. Measure the base firmware and simple-control candidate

Proposed StackChan files are `sdkconfig.conversation.defaults`,
`build_conversation.sh` and a small `main/conversation/` directory. Start with
diagnostic startup selection. Keep `build-local-ito` and `sdkconfig.ito` separate.
Do not add a generic plugin system or duplicate the board implementation.
Audit the existing local-mode compile guards before changing them. A no-TTS
probe must preserve motor/microphone power policy and cannot fall through into
normal cloud startup merely because the Ito runtime component is omitted.

- [ ] Build candidate A without importing/starting Ito or reserving its hot arena.
  Keep the original face and its renderer. Produce the ELF/map and archive sizes.
- [ ] After announcing the exact candidate and rollback command, boot it and
  record base, display, face and idle allocations. Check largest internal blocks.
- [ ] Compare candidate B only if the simple-control interface is selected.
  Disable touch interaction/polling and unneeded widgets independently so each
  saving has evidence. Preserve panel detection and PMIC responsibilities.
- [ ] Verify power-on, power-off, reboot and entry to download mode on battery
  and USB power. Test PMIC click/hold events without changing hardware semantics.
- [ ] Confirm hardware RST reboots without clearing settings. Preserve Ito guard
  records, partition data, model bytes and VPN identity. Configuration-reset
  functionality is a separate decision if it is needed later.

Gate: measured candidate A base memory and working hardware controls. If
candidate B is selected, also compare its actual savings and frame cadence.
Choose the smallest approved shell that preserves the required face and hardware
controls. Do not budget a UI saving before that comparison.

## Task 5. Establish bounded capture and ordinary Wi-Fi

- [ ] Through the original codec, enable ES7210 and I2S RX only for capture.
  Verify real microphone versus reference channels, rate and signed sample format.
- [ ] Test 24-to-16 kHz conversion or coordinated codec rate switching. Keep one
  I2S owner and mute output while recording. Do not start Xiaozhi cloud audio tasks.
- [ ] Capture 1-, 3- and 10-second clips. Verify exact sample counts, clipping,
  overflow counters and resampling with synthetic input and the physical mic.
- [ ] Use at most a 10-second 16 kHz mono int16 utterance for the initial remote
  STT path, 320,000 B payload. Stop cleanly at the cap; never truncate silently.
- [ ] Connect ordinary Wi-Fi and exchange bounded HTTP with a controlled LAN
  endpoint, with Ito absent. Measure connection, reconnect and request peaks.
- [ ] Exercise capture/cancel and capture -> speaker transitions at least 20
  times before adding a recognizer. Verify microphone power returns off.

Gate: correct real audio and measured radio/capture budgets. Add Wi-Fi to a
resident Ito build only after memory is reclaimed and positive headroom exists.

## Task 6. Prove native MicroLink with the actual gateway

Integrate the pinned component under one opt-in conversation configuration.
Disable optional config-server/cellular features. Audit its IDF 5.5 allocation
and TLS paths before enrollment. Its 42 KiB default task stacks already exceed
the working speech profile's free internal heap.

- [ ] Start with no Ito or STT. Test component init failure and teardown without
  credentials. Record JSON allocator-hook effects on other linked components.
- [ ] Provide a private provisioning path for enrollment configuration and identity
  storage. Machine/WireGuard/DISCO keys and enrollment auth keys have different
  lifetimes. Do not assume the disabled upstream config server persists auth keys.
- [ ] Prepare a limited test device identity and access policy permitting only the
  gateway port on gianrtx. Verify secret redaction, then enroll the real robot.
- [ ] Make an outbound TCP echo request, then a real authenticated `/v1/turn`.
  Verify both tailnet IP and MagicDNS. Confirm the selected lwIP source/route.
- [ ] Repeat from another Wi-Fi LAN, with the Mac forwarding helper stopped.
  Verify direct transport and a controlled DERP-only condition separately.
- [ ] Test Wi-Fi loss, peer/server restart, cold reboot, revoked node, expired
  enrollment key and reauthorization. Retain route, timings and failure outcomes.
- [ ] Investigate the upstream DERP `VERIFY_NONE` setting and control trust paths.
  Record and test the required correction; do not disable verification to pass.
- [ ] Add the face and capture only after the isolated network peaks are known.

Gate: the robot itself makes authenticated requests to gianrtx across networks,
with measured direct and DERP behavior. A ping, successful registration or a
working LAN proxy does not satisfy this gate.

If native membership fails, report the exact blocker. A LAN relay remains a
possible deadline contingency, but changing the selected topology needs a decision.

## Task 7. Choose STT using measured local recognition

Start with Oído v2b, 5,931,424 B, SHA256
`9e8b40913f532fb44b716a1f882f38b3b21e220713e417899aba32ace8c35066`.
Keep its weights flash-resident and disable optional LM/caching in the first
fit probe. Confirm intended-use terms before distributing a combined artifact.

- [ ] Build host reference and an isolated instrumented StackChan profile with
  correct quad PSRAM settings. Upstream octal timings are comparison data only.
- [ ] Before a layout change, present exact aligned partitions, new application
  bounds, model/assets hashes and the tested USB restoration procedure.
  Two current 4.75 MiB app slots plus ASR/Ito/assets do not fit this flash.
- [ ] Run at least 20 fixed public English clips and a separate intended-user mic
  set, including noise, silence, names and numbers. Compare public clip outputs
  and latency with Parakeet. Retain failures, not just successful examples.
- [ ] Report streaming feed plus finish time, WER and post-submit final-text delay.
  Do not use the deliberately skipped utterance-pass RTF field.
- [ ] Add face, capture and native networking one at a time. Test 100 allocation
  transitions, including failure during partial initialization and retry/recovery.

Proposed local-STT targets are zero input overflow, streaming RTF below 1 and
p95 post-submit final text below 2 seconds. Evaluate transcription errors with
the user; latency alone cannot select the model. These are targets, not claims
about this board.

If local fit or quality fails, implement the selected remote Parakeet path:

- [ ] Wrap the existing resident worker in a bounded PCM adapter, independently
  of Phonon/WebRTC. Validate format, size, silence, busy, deadline and ownership.
- [ ] Test exact public-fixture outputs, cancellation/reaping, temporary-file
  cleanup, worker restart and a successful request after every injected failure.
- [ ] Transfer a real robot utterance over its native tailnet connection and
  confirm correct transcript. Record upload time separately from inference.

Gate: either proven local STT or the explicitly reported Parakeet fallback.
Do not undertake a second STT engine port without a specific measured blocker.

## Task 8. Combine resources without exceeding the budget

First try the measured resident fit. If it fails, introduce only the lifecycle
needed for half-duplex ownership. Proposed Ito API changes belong in
`itofs_service.h` and the shared runtime, with tests on the production functions.

- [ ] Define ownership for hot/bulk arenas, PSRAM weights, frontend state/stack,
  PCM buffers, task stacks, kernel tiles, GDMA channels, queues and codec state.
- [ ] Stop admission, cancel the current generation, join producers/consumers,
  flush/drain output as appropriate and close the mouth before lending/freeing
  speech memory. No worker may retain pointers into a borrowed arena.
- [ ] Preserve the early contiguous-allocation requirement. Repeatedly freeing
  and hoping a 239,948-byte block reappears is not a design. Compare a reserved
  phase-owned arena against measured safe reacquisition; choose one small path.
- [ ] Audit Oído relocated-weight/LM allocation ownership. Its stock free calls
  do not establish that all optional cached allocations return.
- [ ] Test failed startup, partial task creation, cancellation at each stage and
  100 STT/LLM/TTS transitions. Compare free heap and largest blocks at the same
  idle state. Golden Ito PCM must still match after memory reuse.
- [ ] Compare persistent VPN against releasing network resources before speech
  only if necessary. Measure teardown/re-enrollment cost and identity persistence.
  Require actual memory return; an idle network task still consumes its stack.

Gate: face + selected STT/capture + native transport + local speech fit through
every transition with justified headroom, no stale pointers and no heap drift.
Keep the original speech profile's hot-arena location and correctness unchanged.

## Task 9. Implement turn control and the selected physical interface

Proposed `conversation_controller` states are idle, recording, recognizing,
waiting for answer, speaking and error. One owner controls a turn's generation.
Existing Ito busy/READY checks remain authoritative for its speech phase.

- [ ] Begin with proposed USB diagnostics `listen`, `send`, `cancel`, `status`
  and `memory`. Names must be checked against existing command semantics before
  adding them. Keep credentials on a separate non-logging provisioning path.
- [ ] Verify turn IDs on every completion and reject events from cancelled work.
  Send only parsed validated answer text to Ito, never raw protocol messages.
- [ ] Wire the approved hardware-button mapping after its PMIC event test. For
  the minimal-shell candidate, disable touch interaction and show only necessary
  state/menu text. Keep original face geometry and speaking modifier behavior.
- [ ] Tie mouth animation to PCM reaching output and closing after drain/cancel.
  Keep I2C/PMIC/display work responsive while inference and networking block.
- [ ] Keep physical off/reboot working in every state. Error recovery cannot
  require a touchscreen that the selected profile has disabled.

Gate: ask a question at the robot, receive the Linux model's answer and hear
local Ito while its original face animates. Test a second turn immediately.

## Task 10. Regression, measurements and operational handoff

- [ ] Run greeting/numbers golden checks and a long speech case. Require zero
  output underruns and no unexpected resets. Preserve the honest degraded flag.
- [ ] Run 100 consecutive turns and a 30-minute idle/reconnect session. Exercise
  cancel during recording, STT, LLM wait and playback; late replies; bad payloads;
  backend busy/timeout; Wi-Fi loss; DERP recovery; cold boot and physical off/reset.
- [ ] Compare USB speech mode before/after. Its microphone must stay off. Test
  launcher/mode transitions only if both modes are being packaged in one image.
  Separate working build profiles are an acceptable first handoff.
- [ ] Save exact application/model/configuration manifests and recovery commands.
  Restore and boot the known USB profile with its matching partition/NVS layout.

For each stage retain bytes for internal/DMA/PSRAM free/minimum/largest blocks,
stack watermarks, allocations outstanding, overflow/underrun counts and CPU load.
Linux measurements include process memory, VRAM, cold/warm model state and
first-answer/completion times. Compare like configurations.

Use turn IDs for correlation and each machine's monotonic clock for durations.
Keep capture end, submit, STT final, first LLM answer, first generated PCM,
first I2S submission and audible onset separate. Report p50/p95 with sample
counts and failed/cancelled outcomes; never add stage percentiles to manufacture
an end-to-end value.

Store private raw serial/audio/build evidence beside the device backups, outside
build trees. Proposed gateway metrics are ignored `.local/metrics/stackchan.jsonl`
with bounded rotation; journal output belongs to a dedicated service unit.
Commit sanitized reports, fixture manifests and JSON under Ito's
`results/stackchan/<date>-<experiment>/`. Keep secrets, NVS, private speech and
conversation text out of retained routine logs and Git.

## Commit and review sequence

| Chunk | Completion evidence |
|---|---|
| Gateway contract and isolated Linux service | Unit checks and actual local Nanbeige answers. |
| Host USB integration | Original face speaks remote answers; cancellation test. |
| Base/UI and capture diagnostics | No-Ito memory report, hardware controls and correct microphone PCM. |
| MicroLink integration | Native direct/DERP requests, reconnect and memory report. |
| STT selection | Local recognition evidence or tested Parakeet fallback. |
| Required memory lifecycle | Failure injection, 100 transitions and golden PCM. |
| Conversation controller and interface | Real two-turn physical demonstration. |
| Validation and runbook | Retained results, recovery and exact start/stop commands. |

Before each device write, state the candidate, destination offsets, evidence and
rollback path. Stop at failed technical gates, retain the result and choose the
smallest correction. No phase grants permission to erase unrelated settings,
change shared services, publish a public endpoint or hide a failed acceptance test.

[research]: 2026-11-15-stackchan-tailnet-conversation.md
[baseline]: ../results/stackchan/2026-11-15-original-face/README.md
[buttons]: https://docs.m5stack.com/en/StackChan#power-onoff
[button-api]: https://docs.m5stack.com/en/arduino/stackchan/button
