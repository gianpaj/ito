# Local STT and Ito TTS plan

Status: local STT is an investigation candidate. Ito TTS with the original face
is working. New model, memory-lifecycle and control changes have not started.
This plan is independent of the [native Tailscale plan][network].
The [research record][research] supplies pinned sources and alternatives.
Keep the [working speech baseline][baseline] for comparison and recovery.

## Goal and independent completion

On StackChan, capture English speech, recognize it locally if feasible, and
synthesize supplied English answer text using Ito with the original face.
Start with Oído v2b for open-ended STT. Wake words and command recognition are
not substitutes for a transcript.

This plan can pass using prerecorded audio, the real microphone, typed USB
answer text and a deterministic mock responder. It does not require Tailscale,
a live Linux LLM, Wi-Fi or a custom voice server for its local-engine tests.
The local-model acceptance loop is microphone -> local transcript -> fixture
answer -> local Ito -> speaker and original mouth animation.

If local STT fails its fit or accuracy gate, use the already-selected Parakeet
fallback on gianrtx. That fallback requires the network plan for wireless
operation; it is not evidence of on-device STT. Its adapter and recognition
quality tests remain owned here.

Use half-duplex capture/playback and one active turn. Preserve original face
geometry, hardware power/reset, watchdog behavior, USB diagnostics and motor
power clamps. Touch removal is an optional measured candidate, not an approved
renderer rewrite. No always-listening or full-duplex echo-cancellation work.

## Interface to any responder

The controller supplies a recognized transcript and current session/turn IDs to
a responder, then accepts bounded answer text or an error for that same turn.
Start with a fixture/mock responder. The [network gateway contract][contract]
defines the production protocol and bounds; do not duplicate its socket logic.

- Reject old or cancelled turn completions before starting Ito.
- Parse and validate answer text; never pass a raw network message as a console
  command. Use the existing busy/READY gate and bounded PCM ownership.
- Drive mouth animation from actual playback and drain/cancel, not answer arrival.
- Publish each engine's allocation/lifetime requirements for joint integration.
  An idle engine is not necessarily a released engine.

## Repositories and preserved baseline

StackChan owns board/codec/display integration, capture and the controller. Ito
owns shared synthesis lifecycle changes, its actual-code host tests and canonical
results. The Linux repo owns a Parakeet adapter only if the fallback is selected.
Use Worktrunk feature worktrees, logical commits and existing notes. Respect the
Linux repo's no-PR rule. Keep the tested USB image, models and matching NVS/layout.

## Memory and minimal UI measurements

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

## Phase 1. Measure the base firmware and simple-control candidate

Proposed StackChan files are `sdkconfig.conversation.defaults`,
`build_conversation.sh` and a small `main/conversation/` directory. Start with
diagnostic startup selection. Keep `build-local-ito` and `sdkconfig.ito` separate.
Do not add a generic plugin system or duplicate the board implementation.
Audit the existing local-mode compile guards before changing them. A no-TTS
probe must preserve motor/microphone power policy and cannot fall through into
normal cloud startup merely because the Ito runtime component is omitted.

- [ ] Build candidate A without importing/starting Ito or reserving its hot arena.
  Keep the original face and its renderer. Produce the ELF/map and archive sizes.
  Reuse a matching base artifact from the network diagnostics when its board
  configuration is identical; record configuration differences before comparing.
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

## Phase 2. Validate bounded microphone capture without networking

- [ ] Through the original codec, enable ES7210 and I2S RX only for capture.
  Identify real microphone versus reference channels and signed sample format.
- [ ] Test 24-to-16 kHz conversion or coordinated codec rate switching. Retain one
  I2S owner and mute output while recording. Do not start cloud audio tasks.
- [ ] Capture 1-, 3- and 10-second clips. Verify exact sample counts, clipping,
  overflow counters and resampling with synthetic input and the physical mic.
- [ ] Bound the first utterance to 10 seconds of 16 kHz mono int16 PCM, 320,000 B.
  Stop visibly at the cap rather than silently truncating.
- [ ] Exercise capture/cancel and capture -> playback transitions at least 20
  times. Check rate changes, DMA release, microphone-off error paths and face
  responsiveness. Keep private human speech recordings outside Git.

Gate: correct real audio and measured capture/codec resources with no networking
needed. Preserve board safety when separating local-mode compile guards from
whether the Ito engine starts.

## Phase 3. Evaluate local STT and the Parakeet fallback

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
- [ ] Add face and capture one at a time. Test 100 allocation transitions,
  including failure during partial initialization and retry/recovery. Adding
  native networking belongs to the final joint check.

Proposed local-STT targets are zero input overflow, streaming RTF below 1 and
p95 post-submit final text below 2 seconds. Evaluate transcription errors with
the user; latency alone cannot select the model. These are targets, not claims
about this board.

If local fit or quality fails, implement the selected remote Parakeet path:

- [ ] Wrap the existing resident worker in a bounded PCM adapter, independently
  of Phonon/WebRTC. Validate format, size, silence, busy, deadline and ownership.
- [ ] Test exact public-fixture outputs, cancellation/reaping, temporary-file
  cleanup, worker restart and a successful request after every injected failure.
- [ ] Test actual robot PCM through the adapter using a host-assisted transfer.
  This proves the audio/recognizer pairing without requiring ESP32 networking.
  Wireless upload and its timing belong to the final joint check.

Gate: either proven local STT or the explicitly reported Parakeet fallback.
Do not undertake a second STT engine port without a specific measured blocker.

## Phase 4. Prove STT and Ito memory ownership

First try the measured resident fit. If it fails, introduce only the lifecycle
needed for half-duplex ownership. Proposed Ito API changes belong in
`itofs_service.h` and the shared runtime, with tests on the production functions.
If Parakeet is selected, prove capture/Ito transitions and skip unnecessary
Oído arena-sharing work. Preserve local recognition failures as results.

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
  100 STT/mock-response/TTS transitions. Compare free heap and largest blocks at the same
  idle state. Golden Ito PCM must still match after memory reuse.

Gate: the face, selected local engine/capture resources and Ito fit through
every transition with justified headroom, no stale pointers and no heap drift.
Keep the original speech profile's hot-arena location and correctness unchanged.

## Phase 5. Validate local turn control and hardware controls

Proposed `conversation_controller` states are idle, recording, recognizing,
waiting for a supplied answer, speaking and error. One owner controls a turn's
generation.
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

Gate for the local-model path: record a question, produce a local transcript
and speak a supplied fixture answer with Ito and the original face. Test a
second turn immediately. For the Parakeet fallback, independently pass capture,
the host-assisted recognition test and supplied-answer playback; wireless voice
acceptance waits for the joint check.

Use the mock responder for the local acceptance gate. Live Linux reasoning and
wireless recognition upload are integration tests after the networking milestone.

## Phase 6. Local regression and result retention

- [ ] Run deterministic Ito greeting/numbers checks before and after shared-memory
  reuse, plus a long spoken case. Require correct PCM and zero output underruns.
- [ ] Run 100 local listen/respond/speak cycles using fixed answers. Test silence,
  bad audio, maximum utterance length, STT failure, late completion, cancel and
  partial initialization failure. Require bounded recovery and no heap drift.
- [ ] Verify physical power-off/reboot in every state and cold-boot recovery.
  Test the selected shell; errors cannot require disabled touchscreen controls.
- [ ] Preserve microphone-off behavior in USB speech mode. Separate diagnostic
  builds are acceptable until combined mode entry/exit is proven safe.
- [ ] Restore and boot the known USB profile with matching partition/NVS data.

Follow the [shared measurement rules][measurement]. Record public-fixture WER,
recognizer feed/finish time, post-submit final text, resampling, Ito generation/
I2S/drain/cancel timings, CPU use, task watermarks and internal/DMA/PSRAM free,
minimum and largest blocks at each phase transition. Label measured values and
arithmetic estimates separately. Keep `degraded=1` truthful.

Save raw private evidence outside builds and commit sanitized reports under
Ito `results/stackchan/<date>-local-stt-ito/`. Retain exact model/code/config hashes
and failures. Routine logs do not retain private audio or transcript text.

## Final joint check with native Tailscale

Use the [network plan's joint checklist][joint] as the single integration gate.
Local tests can be completed before that connection exists. Include the measured
capture, STT, Ito and display allocations when checking combined peaks. If the
combination needs network teardown before synthesis, networking owns that teardown;
this plan owns safe speech shutdown/restart and memory ownership.

A successful local STT result is microphone -> Oído -> transcript on the robot.
A successful Parakeet result is explicitly remote recognition. Both can feed
local Ito; only the former establishes that both speech models run on the ESP32.

Commit units are base/UI measurements, capture, local STT proof/selection,
necessary Ito lifecycle work, local controller/controls, recognition fallback
if needed, and local results/recovery. Final network integration is a separate
logical commit after both plans pass their independent gates.

[research]: 2026-11-15-stackchan-tailnet-conversation.md
[network]: 2026-11-15-stackchan-native-tailnet-implementation.md
[contract]: 2026-11-15-stackchan-native-tailnet-implementation.md#api-contract
[joint]: 2026-11-15-stackchan-native-tailnet-implementation.md#final-joint-check-with-speech
[measurement]: 2026-11-15-stackchan-tailnet-conversation.md#results-performance-and-logs
[baseline]: ../results/stackchan/2026-11-15-original-face/README.md
[buttons]: https://docs.m5stack.com/en/StackChan#power-onoff
[button-api]: https://docs.m5stack.com/en/arduino/stackchan/button
