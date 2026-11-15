# StackChan conversation through Tailscale

Status: proposed. Source research and read-only inspection of `gianrtx` are
complete. Device experiments, service deployment and firmware changes are not
started. This plan extends the working [original-face Ito mode][baseline].

## Goal and recommendation

Add a separate conversation mode. The preferred final path is:

```text
StackChan microphone -> local STT -> transcript
    -> MicroLink / Tailscale -> gianrtx text gateway -> local Ollama LLM
    <- bounded answer text <- gateway
    -> local Ito TTS -> original speaker and animated face
```

Only the LLM runs on the computer in that target. The robot joins the tailnet
itself and reaches `gianrtx.tail8e80d.ts.net`, without a nearby Mac or phone.
Tailscale direct peer transport is preferred, but encrypted DERP relay must
also work when direct connectivity is unavailable.

Keep the working USB speech profile as the recovery and comparison baseline.
Begin with half-duplex, explicit start/stop recording and short replies. Wake
words, always-listening operation, simultaneous listening/speaking and motor
movement are outside the first conversation milestone.

The user selected existing Parakeet on `gianrtx` as the preferred fallback if
local STT cannot fit or meet accuracy needs. In that fallback only, captured
audio crosses the tailnet for recognition. Ito TTS and face animation remain
on the robot. Report this distinction in the demo and results.

Recommendation: prove a host-driven text loop first, then measure local STT and
native Tailscale independently. Combine only after the memory gates pass. Use
a LAN relay as the deadline fallback if native tailnet membership fails. Do not
quietly turn the requested direct connection into a permanent relay dependency.

## What the inspection establishes

### Working robot baseline

- Deployed StackChan code is `f799097c265d8c3c5c7980704c4a14dfcd0f6218`;
  Ito runtime is `b7412446a19e88bce34021d95c47d2bb81b2a953`, on IDF 5.5.4.
  Documentation HEADs at inspection are StackChan `a9218e1` and Ito `386fc61`.
- Hardware is ESP32-S3, 16 MiB flash and 8 MiB **quad** PSRAM at 80 MHz.
- Measured warm internal free memory is 13,202 B; minimum is 5,358 B. Ito's
  hot arena occupies 239,948 B internal SRAM and its bulk arena 1,579,920 B
  PSRAM. After the quiet-text scratch allocation, PSRAM free is 2,418-2,419 KiB.
- Paragraph compute RTF is 1.03515 with zero output underruns. Networking and
  capture do not have a demonstrated CPU or memory budget in that profile.
- Local mode explicitly disables networking and microphone power. The board's
  `GetNetwork()` returns null. Codec construction omits ES7210 input and I2S RX.
  Enabling a setting or changing a server address cannot activate conversation.
- The original codec owns I2S0. Input and output clocks are coupled and configured
  at 24 kHz. A 16 kHz recognizer needs tested conversion or coordinated rate
  changes through this same owner.
- Ito's public API starts once, submits commands and cancels. It has no public
  stop/free/restart API. Cancellation does not release its model arenas or tasks.
  Startup marks the service started before runtime initialization and does not
  reset that flag on failure. Recovery after failed initialization is a separate
  lifecycle requirement, not a property of cancel. [Runtime lifecycle][ito-life].

The [saved measurements][baseline] are the baseline, not a budget for added
features. Total free PSRAM cannot substitute for internal SRAM, contiguous
blocks, DMA buffers or task stacks.

### Existing firmware, WebSockets and phone setup

There are two different protocols in the original repository:

| Path | Purpose | Consequence for this project |
|---|---|---|
| Xiaozhi voice WebSocket | JSON hello/control, binary Opus microphone and reply audio | A normal backend expects server-side ASR/TTS. Local Ito needs a deliberate text path. |
| StackChan `/stackChan/ws` | App/avatar relay with binary message framing and its own authorization | The bundled Go server is not an Ollama voice gateway. |

The pinned Xiaozhi dependency is v2.2.4, commit
`e77dedb1309153bb63fed285772962c920c97dd4`, plus the tracked StackChan patch.
Its WebSocket handshake uses `Protocol-Version`, `Device-Id`, `Client-Id` and
an optional bearer token. Server `tts/sentence_start` includes answer text;
`llm` currently supplies emotion rather than an arbitrary answer-token stream.
The normal audio path still expects Opus. [Protocol source][xiaozhi-ws].

The Android/iOS app provisions Wi-Fi through BLE `setWifi`. Inspection found no
phone field for a custom voice-server URL. The local Ito profile substitutes
BLE stubs. Normal Xiaozhi server discovery separately reads NVS `wifi/ota_url`,
then `CONFIG_OTA_URL`; a discovery response can supply `websocket` settings.
MQTT takes precedence when both transport settings exist. A custom build must
choose its endpoint explicitly rather than inherit cloud discovery or stale
MQTT settings. [Wi-Fi provisioning][mobile], [discovery][ota].

Therefore neither the mobile app nor the bundled server is required for a small
text gateway. Restoring BLE solely to configure one endpoint would add memory
pressure. Start with USB configuration and saved Wi-Fi credentials.

### Existing Linux models and services

Read-only SSH inspection succeeded at `/home/gianpaj/github/gianpaj/local-voice-agent`,
commit `94a36d4af849c30799eb7ac5cd7cd3c877b65ee9`, with a clean worktree.

- Its transport is Pipecat SmallWebRTC, with HTTP offer/signaling endpoints.
  It is not a Xiaozhi WebSocket server. [Server][voice-server], [pipeline][voice-pipeline].
- Private configuration selects resident Parakeet and Ollama alias
  `local-voice-nanbeige`, from `nanbeige4.3-33b-iq2m:latest`. Both aliases exist.
  Qwen remains installed as `local-voice-qwen`; do not switch models implicitly.
- Ollama is active, but `/api/ps` reports no loaded models. The voice-agent user
  service is inactive and port 7860 is closed. Availability of weights is not
  warmed inference readiness.
- Port 3000 belongs to `zonos3-server`. Existing Tailscale Serve HTTPS 8443 points
  to that port. Serve routes also use 4702 and 8080. Preserve these routes and
  processes; do not run the voice app's default launcher into the occupied port.
- The current app's LLM module already uses local `/v1/chat/completions`, a
  4,096-token context, 128-token replies and bounded history. Reuse its model
  choices and request policy without loading Phonon for a text-only gateway.
  [LLM module][voice-llm], [Ollama compatibility][ollama].

The recommended installation is a small, separately launched gateway using the
existing local Ollama service. Add Parakeet only if the STT fallback is selected
after the device tests. Do not install another full inference stack.

## Options and viability

### Connection options

| Option | Robot joins tailnet? | Extra nearby computer? | Assessment |
|---|---|---|---|
| MicroLink on ESP32 | Yes | No | Requested target. Real implementation exists; current unmodified Ito profile lacks RAM for it. Needs isolated and combined tests. |
| Wi-Fi application relay on Mac, Pi or travel router | No | Yes | Simplest fallback. Robot contacts a local relay; relay reaches the Linux gateway over official Tailscale. |
| LAN gateway with explicit IP routing into tailnet | No | Yes, possibly router | Viable with verified outbound routes, return path and DNS. More network setup than an application relay. |
| Public HTTPS/WSS through Funnel or another tunnel | No | No | Technically possible, but exposes an application endpoint publicly. Not selected for this private design. |
| Plain WireGuard on ESP32 | Not by itself | Depends | Requires its own peer/key/server design. It does not become a Tailscale node merely by using WireGuard. |

Advertising the robot's LAN as a subnet route does not automatically let a robot
on arbitrary Wi-Fi reach `100.x` tailnet addresses. A non-member client needs an
actual forwarding gateway and suitable routes. [Subnet routers][subnet].
Serve is private service publication, not a VPN client for the robot. Funnel is
public and officially supports clients without Tailscale. Issue #230's assertion
that Funnel universally rejects non-tailnet ESP32 clients contradicts that
documented behavior; treat its failure as a setup-specific result to reproduce,
not a protocol rule. [Serve][serve], [Funnel][funnel].

### MicroLink findings

Research pin: `216da3300f0493b0860247d43f7af5ce29df63a5`.
It implements coordination, WireGuard, peer discovery and relay transport.
The advertised SRAM figure is not the incremental peak of adding it to Ito.

- Four default task stacks total **42 KiB**, before task metadata, queues,
  Wi-Fi and TLS. Ordinary pinned-task creation uses internal stacks in the
  inspected configuration. This alone exceeds the baseline's 13,202 B free.
  [Stack sizes][ml-stacks], [startup][ml-start].
- Default coordination buffers include 512 KiB H2, 512 KiB JSON and a 64 KiB
  frame buffer, plus parsing and temporary allocations. Large allocations can
  prefer PSRAM; other paths use ordinary allocation. Measure actual peaks.
  [Coordination source][ml-coord].
- Outbound TCP exists. An ESP-IDF HTTP/WebSocket client over the VPN route still
  needs verification. There is no turnkey WSS/TLS adapter in its TCP API.
  [TCP implementation][ml-tcp].
- Machine, WireGuard and DISCO identity keys persist in NVS. Auth-key persistence
  requires an explicit provisioning path; the optional upstream config server
  is disabled in this proposal. Registration and node expiry are distinct;
  reusable auth keys also expire. Test reboot, revocation and reauthorization.
  Keep tailnet credentials out of committed configuration and logs.
  [Persistent identity][ml-keys], [auth keys][authkeys].
- DERP TLS explicitly sets `MBEDTLS_SSL_VERIFY_NONE`. WireGuard protects peer
  payloads, but certificate validation and control/relay trust need a focused
  review before relying on this client. [DERP TLS][ml-derp].

[stackchan-mcp issue #230][issue230] is open. Its reported integration is
scaffolding on branch `issue-230-microlink-component` at `de3c4ee`, pinned to
MicroLink v2.1.0 `5a60e24`. It reports no main-side wiring or physical out-of-LAN
verification. This is another StackChan project, not an integration already
available in the M5Stack firmware used here.

### Speech recognition options

| Recognizer | Open-ended English? | Assessment |
|---|---|---|
| Oído v2b on ESP32 | Yes | First local candidate. Flash-resident weights and limited caching offer a plausible fit, subject to board tests. |
| Parakeet on gianrtx | Yes | User-selected fallback. Reuse existing resident worker via a bounded audio endpoint. |
| ESP-SR WakeNet/VAD/MultiNet | No freeform dictation | Wake-word, activity and configured-command tools. Useful later, not equivalent STT. |
| BabyTalk int4 | Yes, project claims | Secondary local candidate if Oído fails for a specific measured reason. No source/runtime validation in this investigation. |

Oído pin: `c8d60325ba8bffd4bad65a9ac63c713ee64d1aae`.
Committed artifacts are v2b **5,931,424 B**, v2a **7,705,504 B**, and optional
language model **1,288,852 B**. Start with v2b and flash-resident weights.
Its allocator can put working buffers in PSRAM when internal memory is scarce;
that changes performance. [Model artifacts][oido-models], [allocator][oido-main].

Upstream's v2b no-weight-cache run leaves 5,059,880 B PSRAM and 75,888 B internal
free at minimum, with streaming RTF about 0.656. This is an upstream benchmark
on an **octal**-PSRAM board, not a measurement of this robot. The live microphone
path is explicitly unmeasured there. Do not transfer its throughput or final-text
latency to the quad-PSRAM StackChan. [Benchmark][oido-flash], [method][oido-readme].

Sequential STT/TTS is promising, but not a working lifecycle. Oído's optional
weight relocation allocates copies that its ordinary model-free path does not
release. Ito has no public teardown. Prove ownership and reclamation before
sharing workspaces or unloading models per turn. Disabling a task is insufficient.
Oído currently dereferences a mapped model blob; direct inference from SD is not
a supplied substitute for a flash partition. [Placement/free][oido-engine].

Flash also needs a decision. Existing application, assets, Ito weights and v2b
sum to **14,292,701 B**, leaving 2,484,515 B of 16 MiB before boot/system data,
alignment, added code and partition slack. Adding the optional LM leaves
1,195,663 B before those costs. These are lower-bound sums using the current
app size, not a proposed layout. The current pair of 4.75 MiB OTA slots cannot
be retained together with a 5.9 MB ASR model and current assets. Evaluate a
single app slot with verified USB recovery, smaller assets, or an external
storage design. Any recovery/layout change needs a concrete reviewed map first.

ESP-SR's command recognition is not open-vocabulary conversation. Its AFE and
models also consume memory beyond the current free internal heap. Do not add
them merely because they are present in the dependency lock. [Official scope][multinet].
[BabyTalk][babytalk] describes a 6 MB int4 model and shared workspace; its claims
are a reason for a later probe, not evidence of fit with Ito or native Tailscale.

## Proposed service and device behavior

The smallest first gateway accepts one bounded text turn and returns one bounded
answer. Use HTTP over the private tunnel for the first experiment. WebSocket is
an option if measured streaming or cancellation needs justify a persistent
channel. The original firmware's use of WebSocket does not require this mode to
carry Opus, cloud activation or the complete Xiaozhi protocol.

Candidate gateway contract, finalized in phase 1:

- `GET /health` distinguishes process alive, model warming and model ready.
- `POST /v1/turn` accepts a session ID, turn ID and English text, with a 4 KiB
  request cap. Response contains the same IDs, bounded answer text and timings.
  Start with a 2 KiB answer cap and the existing 128-token reply policy.
- One active turn per device, one inference admission initially, a 30-second
  timeout and bounded server-side history. A repeated turn ID cannot trigger
  duplicate inference/playback. Retry only before confirmed acceptance or use
  an explicit idempotency lookup. Disconnect cancels owned work.
- The robot parses JSON before passing validated text to the Ito API. Network
  text is never a raw console command, so it cannot become `volume` or another
  diagnostic command. Respect Ito's busy state and READY gate.
- Start with a complete short reply before synthesis. This makes backpressure
  and network/inference phase separation straightforward. It does not buffer
  whole generated audio. Add sentence streaming only after this path works.
- Use a separate device credential and tailnet access rule limited to the
  gateway. Native `http/ws` over WireGuard avoids another device TLS handshake;
  use verified `https/wss` if the threat model or route requires it. A plaintext
  LAN relay hop is not encrypted by the later Tailscale hop; protect that hop
  appropriately if the LAN is untrusted.

If selected, the Parakeet endpoint accepts only a short bounded PCM utterance.
Ten seconds of signed 16-bit mono at 16 kHz is 320,000 B. Validate rate, length,
encoding, timeout and busy limits. Reuse the existing worker without starting
Phonon, browser WebRTC or an unrelated app. Model warmup and worker supervision
must have independent readiness. Audio and transcripts stay out of routine logs.

The alternative [Xiaozhi Python server][xiao-server] supports Ollama and accepts
text through `listen/state=detect`. Its normal reply path still invokes server
TTS and sends Opus. Suppressing that work and adapting sentence text/cancel
would be required. Choose it only if compatibility with normal Xiaozhi clients
becomes a requirement. The bundled StackChan app relay solves a different task.

The proposed user interaction is tap to start recording, tap to submit, and tap
while speaking to cancel. Use an existing face touch event if suitable, with a
minimal existing status label: `Listening`, `Thinking`, `Speaking`, `Offline`.
Begin with USB `listen`, `send`, `cancel` diagnostics before wiring touch. Keep
the original mouth animation tied to actual PCM playback, not LLM generation.
Do not restore head-touch/IMU services solely to obtain a trigger.

Initially make this a separate opt-in build profile. A single image with a
launcher choice is a later milestone after mode exit/re-entry and allocation
ownership pass. Motors remain off. Microphone power is enabled only during the
conversation capture phase and must return off on cancel, error and mode exit.

## Phases, experiments and exit gates

### 0. Preserve the reference and establish the budget

Completed here: source audit, host connectivity, model inventory and service/
port inspection. No inference requests, device connections, firmware writes,
tailnet enrollment or service/network changes were made.

Before implementation:

1. Pin sources and record app/model hashes, SDK configuration and current NVS
   layout. Reuse the verified private device backup and rollback instructions.
2. Inventory task stacks, static memory, largest internal/DMA blocks and PSRAM
   peaks by stage. Reserve explicit radio, capture and transport budgets rather
   than subtracting published example totals from physical RAM.
3. Inspect safe reduction of unused runtime tasks/buffers. Test a targeted
   lifecycle or phase-owned workspace only if measured needs require it. Keep
   Ito's hot SRAM requirement and golden checks intact in its speech phase.
4. Define candidate flash maps for the Parakeet path and local-Oído path. Build
   both size reports before considering partition changes.

Exit gate: a conservative static and estimated allocation budget for each
isolated diagnostic profile, plus reviewed candidate images and recovery.
Instrumented device experiments then establish actual peaks. Maintain a table
for idle, recording, STT, LLM request and playback, including allocation
size/heap, peak/minimum, largest block, stacks and a justified safety margin.
Require positive measured headroom before combining tested subsystems. Unknown
allocations remain unknown; never count them as zero or flash the full stack
just to see whether it boots.

### 1. Reuse Linux inference and prove the text loop through USB

1. Work on a feature branch in `local-voice-agent`, respecting its no-PR rule.
   Choose an unused loopback gateway port after checking listeners. Reach that
   first host test from the Mac through an SSH local forward over Tailscale.
   Before direct device tests, publish a dedicated authenticated listener bound
   to the Linux Tailscale address on an unused port. Keep Ollama calls loopback.
   If HTTPS is chosen, use a separate new Serve route and test that exact URL.
   Preserve shared Ollama settings and all existing Serve routes.
2. Add the small gateway and host tests for health/readiness, bounded input,
   wrong credentials, busy, duplicate IDs, timeout, cancellation and empty output.
3. Run a real local request against the installed Nanbeige alias. Record cold
   load, warmed first-answer and completion timings, model/context and GPU memory.
   Validate reasoning suppression, plain spoken answer text and output limits.
4. Use the Mac as a temporary host test client over its existing Tailscale route.
   Feed a returned short answer through the working USB `text` command. This
   validates remote reasoning plus local Ito/face without adding radio memory.
5. Delay/reorder a response, cancel, then issue a new turn. Require no stale
   answer playback and no duplicated sentence.

Exit gate: repeatable host text -> Linux LLM -> USB Ito speech with correct face
and cancellation. This is a useful early demonstration, explicitly host-assisted.

### 2. Prove device Wi-Fi and microphone capture separately

1. Build an experimental conversation profile, without MicroLink or STT first.
   Retain the original codec, face, USB diagnostics and motor power clamps.
2. Bring up Wi-Fi, resolve an ordinary LAN endpoint and exchange bounded text.
   Measure association/reconnect and transport peaks with Ito absent, then with
   Ito present only after measured headroom exists. The baseline's 13,202 B free
   does not meet that gate; first reclaim enough memory in the experimental
   profile. If necessary test closing network resources before speaking.
   A low-memory allocator failure must remain recoverable and visible.
3. Enable ES7210 and RX through the existing codec. Identify microphone versus
   speaker-reference channels, verify signed PCM and test a 24-to-16 kHz path.
4. Capture bounded 1-, 3- and 10-second clips, with the speaker muted. Check
   clipping, channel selection, dropped samples, sample count and capture rate.
   Use a known synthetic input for repeatability and human speech for the actual
   microphone check. Keep private speech recordings outside Git.
5. Exercise repeated capture/cancel and capture -> playback transitions. Check
   both rates, DMA release, microphone rail shutdown and original mouth behavior.

Exit gate: correct real microphone audio and bounded Wi-Fi/codec resources on
this board. Half-duplex is intentional; acoustic echo cancellation is deferred.

### 3. Test direct tailnet membership in an isolated profile

1. Integrate pinned MicroLink with optional config server/cellular features off.
   Begin without Ito or STT. Audit IDF 5.5 compatibility, task placement, global
   JSON allocation hooks and control/DERP TLS verification.
2. Prepare a narrowly scoped test identity and grant. Provision credentials
   privately over USB; inspect key persistence and redaction before enrollment.
3. Join the tailnet and make an outbound TCP echo request. Then run the actual
   gateway HTTP request over the VPN. Test both the peer IP and MagicDNS name.
   A successful ping is insufficient.
4. Test direct transport and a controlled relay-only condition. Test a second
   Wi-Fi network, reconnect, server restart, cold boot, revoked identity and
   expired enrollment credentials. Record route and recovery time for each.
5. If WSS is selected, separately prove verified certificates, time setup, SNI,
   reconnect and heap peaks. Do not treat TCP support as WSS validation.
6. Add the original face, then Ito. Measure speech performance during normal
   traffic and coordination refresh. Compare persistent VPN against an explicit
   request-then-release lifecycle if memory demands it; verify released heaps
   and measure the reconnection cost instead of assuming resources disappear.

Exit gate: real text requests from the robot to `gianrtx`, on a different LAN,
through both direct and relayed tailnet paths, plus a measured fit with playback.
If this fails, retain the result and select a LAN relay for the first voice demo.
Do not weaken golden correctness, bypass memory checks or disable certificate
checks to declare success.

### 4. Decide local STT from a bounded Oído experiment

1. Build the pinned Oído host and ESP32 engine with exact model hashes. Test v2b
   from flash first, then optional caching/LM only when justified by results.
   Confirm terms for the intended use before distributing combined firmware.
2. On the StackChan, configure **quad** PSRAM correctly and test deterministic
   prerecorded 16 kHz input before the real microphone. Report full streaming
   feed plus finish time; do not use the skipped utterance-pass RTF field.
3. Measure accuracy on at least 20 fixed public English prompts and a separate
   set of intended-user microphone phrases. Include names, numbers, longer
   questions, silence and room noise. Keep public corpus WER separate from
   private human acceptance. Compare with Parakeet on the same public clips.
4. Add face/capture, then Wi-Fi/native networking. Measure audio overflow and
   final-transcript delay. Investigate STT/TTS arena ownership if simultaneous
   residency fails. Run at least 100 listen/speak allocation cycles, checking
   heap return, largest block and golden Ito output after reuse.
5. Inject allocation and initialization failures at each phase. Require bounded
   cleanup, no use of released buffers, and a working retry or explicit safe
   restart path. Include failure during partial startup, not just successful
   stop/start cycles.

Exit gate: acceptable measured English recognition, fit with the chosen network
path, and repeatable phase transitions. Candidate targets are no input overflow,
streaming RTF below 1, and p95 final-text delay below 2 seconds after submit.
These are proposed targets, not measured capabilities or guaranteed quality.
Review actual error examples with the user before choosing local STT.

If fit or accuracy fails, use the user-selected Parakeet fallback. Add and test
the bounded PCM endpoint with cancellation, worker recovery and real robot audio.
This avoids the Oído flash-layout change. It still needs the measured Wi-Fi/VPN
and capture budget; remote STT does not resolve all networking memory pressure.
Time-box a BabyTalk investigation only if it addresses a specific blocker.

### 5. Assemble the conversation mode

1. Connect the proven pieces with one active turn and explicit states:
   idle, recording, recognizing, waiting for LLM, speaking, error.
2. Use USB diagnostic triggers first, then the chosen minimal touch interaction.
   Keep mode configuration separate from factory cloud/OTA NVS keys.
3. Reject old turn IDs after cancel/reconnect. Bound captured audio, history,
   input/answer text and queues. Keep HTTP/network callbacks off synthesis/UI.
4. Verify correct resource ownership and allocation return at each state change.
   If phase switching is required, wait for workers to stop before reusing their
   memory. Keep only the smallest necessary lifecycle API.
5. Confirm local TTS and original face with the physical robot. Run deterministic
   PCM checks, a short conversation and long replies with zero underruns.

Exit gate: speak a question at the robot, receive an answer from the selected
local Linux model, hear local Ito synthesis and see correct mouth animation.
Report explicitly whether STT and tailnet membership are local or fallback paths.

### 6. Validate recovery, modes and handoff

Run 100 consecutive turns and a 30-minute idle/reconnect session. Cover cancel
while recording/recognizing/requesting/speaking, Wi-Fi loss, DERP recovery, LLM
timeout, malformed response, busy backend, microphone failure, service restart
and cold power cycle. Require no unexpected resets, stale speech or growing
allocation counts; investigate trends rather than rounding them away.

Only then combine USB speech and conversation into a launcher choice if both
fit in one image. Test entry, exit, microphone-off USB mode, Home and re-entry.
Retain the normal cloud build as a separate buildable profile. Recheck recovery
with the exact new layout; a second empty OTA slot is not a recovery image.

Exit gate: documented start/stop commands, configuration, exact firmware/model
artifacts, measured results and a verified way back to the working USB image.

## Results, performance and logs

For every experiment record commit/config/model hashes, board and PSRAM mode,
network topology, direct/DERP route, model cold/warm state and pass/fail evidence.
Save stage timings for capture, resampling, STT, LLM first text/completion,
Ito first PCM/I2S submission, playback/drain and cancellation. Use each host's
monotonic clock for local durations; correlate with turn IDs. Do not subtract
timestamps across computers without a measured clock relationship.

Report p50/p95 with sample counts, failures, cancellations and cold starts
separately. End-of-speech, submit, first generated PCM, I2S submission and first
audible output are different boundaries. Measure audible latency separately if
needed. Do not add independent stage medians to invent an end-to-end result.

Record internal free/minimum/largest block, DMA heap, PSRAM free/minimum/largest,
task stack watermarks, CPU load, audio underruns/overflows and reconnect peaks.
Linux results include model readiness, GPU VRAM and process memory. Compare
Ito RTF/underruns with the fixed baseline; keep `degraded=1` truthful.

- Robot raw serial sessions stay in private dated experiment directories outside
  disposable builds. Retain the same USB logs and export sanitized measurements.
- Proposed gateway log path is ignored `.local/metrics/stackchan.jsonl` in
  `local-voice-agent`, with bounded rotation and metadata-only records. Service
  output is available through its dedicated user-service journal after deployment.
- Commit public fixture definitions, sanitized `results.json`, a short report
  and source/artifact hashes under `results/stackchan/<date>-<experiment>/` in
  Ito. Keep raw private audio, transcripts, keys, device identity and NVS out of Git.
- Archive raw evidence, binaries and manifests with checksums beside the existing
  private device backups. Do not leave the only copy under a build directory.

## Work boundaries and commits

The plan and canonical measured reports live in Ito. Device integration lives
in StackChan. Gateway and optional Parakeet adapter changes live in
`local-voice-agent`, whose existing workflow requires a feature branch and no PR.
Use Worktrunk to reuse/create task worktrees and preserve unrelated work.

Commit independently reviewable chunks: gateway contract/tests; host USB demo;
capture and Wi-Fi diagnostics; isolated MicroLink proof; local STT findings;
chosen conversation path; lifecycle/UI integration; final measurements. Record
decisions under `.agents/notes/{proposed|implemented}/architecture/` and hardware
results under the existing hardware class. Link canonical reports instead of
copying their numbers into several guides. Do not commit failed experiments as
working product features.

This is an investigation and implementation plan. Approval of a connection
option selects the next implementation scope. Public exposure and changing the
flash recovery layout need explicit decisions. Parakeet is already selected
conditionally and becomes the STT path if local recognition fails its fit or
accuracy gate. None of those choices is a side effect of installing a server.

## Sources

Source snapshots were inspected on 15 November 2026. Upstream benchmarks remain
upstream observations until reproduced on this StackChan.

[baseline]: ../results/stackchan/2026-11-15-original-face/README.md
[ito-life]: https://github.com/gianpaj/ito/blob/b7412446a19e88bce34021d95c47d2bb81b2a953/esp32/firmware/main/main.c#L2352
[xiaozhi-ws]: https://github.com/78/xiaozhi-esp32/blob/e77dedb1309153bb63fed285772962c920c97dd4/main/protocols/websocket_protocol.cc
[mobile]: https://github.com/gianpaj/StackChan/blob/a9218e1f9518891a2e71b399de73fe5c94f24eb4/app/lib/view/popup/device_wifi_config.dart#L303
[ota]: https://github.com/78/xiaozhi-esp32/blob/e77dedb1309153bb63fed285772962c920c97dd4/main/ota.cc#L46
[voice-server]: https://github.com/gianpaj/local-voice-agent/blob/94a36d4af849c30799eb7ac5cd7cd3c877b65ee9/apps/agent/src/local_voice/server.py
[voice-pipeline]: https://github.com/gianpaj/local-voice-agent/blob/94a36d4af849c30799eb7ac5cd7cd3c877b65ee9/apps/agent/src/local_voice/pipeline.py
[voice-llm]: https://github.com/gianpaj/local-voice-agent/blob/94a36d4af849c30799eb7ac5cd7cd3c877b65ee9/apps/agent/src/local_voice/llm.py
[ollama]: https://docs.ollama.com/api/openai-compatibility
[subnet]: https://tailscale.com/docs/features/subnet-routers
[serve]: https://tailscale.com/docs/features/tailscale-serve
[funnel]: https://tailscale.com/docs/features/tailscale-funnel
[authkeys]: https://tailscale.com/docs/features/access-control/auth-keys
[issue230]: https://github.com/kisaragi-mochi/stackchan-mcp/issues/230
[ml-stacks]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/include/microlink_internal.h#L45
[ml-start]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/src/microlink.c#L372
[ml-keys]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/src/microlink.c#L53
[ml-coord]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/src/ml_coord.c#L1393
[ml-tcp]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/src/ml_tcp.c#L37
[ml-derp]: https://github.com/CamM2325/microlink/blob/216da3300f0493b0860247d43f7af5ce29df63a5/components/microlink/src/ml_derp.c#L720
[oido-models]: https://github.com/lokutor-ai/oido/tree/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/models
[oido-main]: https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/firmware/main/main.c
[oido-flash]: https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/bench/r_nops_b3.json
[oido-readme]: https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/README.md
[oido-engine]: https://github.com/lokutor-ai/oido/blob/c8d60325ba8bffd4bad65a9ac63c713ee64d1aae/esp32/components/tinyasr/tasr_nemo.c#L215
[multinet]: https://docs.espressif.com/projects/esp-sr/en/latest/esp32s3/speech_command_recognition/README.html
[babytalk]: https://github.com/tlack/babytalk
[xiao-server]: https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/2dfaf44269e651775f2011162f8967d9fc3fdd5f
