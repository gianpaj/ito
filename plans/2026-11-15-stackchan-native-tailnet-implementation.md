# Native Tailscale and remote LLM plan

Status: native tailnet membership selected; implementation has not started.
This plan owns networking, enrollment and the Linux LLM gateway. The separate
[local STT and Ito plan][speech] owns microphone capture, models, memory sharing
and face/control behavior. [Research][research] preserves the source evidence.

## Goal and independent completion

Make the ESP32 itself join Tailscale through MicroLink and exchange authenticated
text with a gateway on `gianrtx.tail8e80d.ts.net`. The gateway uses the existing
local Nanbeige Ollama alias. Direct peer transport and DERP must both work.

This plan can pass with typed USB input and answers printed to the console.
It does not require a microphone, local STT, Ito or an animated face. Its test
firmware must preserve board power safety and avoid factory cloud startup.
A nearby LAN relay is a contingency requiring a separate topology decision.

The preferred first transport is bounded HTTP over WireGuard. If actual
measurements require WebSocket or HTTPS, test that transport explicitly.
Do not import Xiaozhi Opus processing or install a full voice-server stack just
because the normal firmware uses WebSocket.

## Boundary shared with the speech plan

This plan is canonical for the gateway protocol below. Speech consumes and
produces UTF-8 text tagged with a session ID and turn ID, plus explicit cancel,
busy and error outcomes. It does not own radio, enrollment or socket code.

- The input can come from typed USB text, a local recognizer or remote Parakeet.
- The output is bounded answer text. No generated audio crosses this interface.
- The consumer accepts an answer only for its active turn and plays it at most
  once. A cancelled or superseded turn can never start playback.
- The network worker exposes its readiness, current turn and resource lifetime.
  The speech controller can wait for completion without running socket work on
  the display or synthesis task.
- Network-only free memory is not evidence that a speech engine fits beside it.
  Publish measured peak allocations and largest-block requirements for the joint
  check. An idle task still owns its stack.

The optional Parakeet audio endpoint is owned by the speech fallback phase. It
reuses this plan's authentication and private transport rather than adding a
second networking design. The text gateway stays independently usable.

## Repository ownership

| Repository | Work |
|---|---|
| StackChan | Opt-in network diagnostic profile, Wi-Fi, MicroLink, provisioning and bounded text client. |
| local-voice-agent | Independently launched text gateway and its focused tests. |
| Ito | Host-side protocol test, canonical network results and this plan. |

Use Worktrunk feature worktrees and logical commits. The Linux repo's no-PR rule
applies there. Keep the working USB speech build and its recovery artifacts.
New filenames and commands described here are proposals until implemented.

## Phase 1. Pin inputs and establish a network-only budget

- [ ] Check worktrees and clean Git state; preserve unrelated work and serial
  monitors. Refresh Linux listeners, Serve routes and the current tailnet address.
- [ ] Pin MicroLink `216da3300f0493b0860247d43f7af5ce29df63a5`, IDF and dependency
  patches. Record the exact baseline app/partition/NVS recovery manifest.
- [ ] Prepare a separate diagnostic build without Ito or STT. Reuse the board
  implementation and motor power clamps. Do not enter cloud mode when omitting Ito.
- [ ] Inventory static sections, radio buffers, task stacks, TLS/JSON buffers and
  queues. Default MicroLink stacks total 42 KiB; the working Ito profile has
  only 13,202 B internal free. Do not combine those unmodified profiles.
- [ ] Require a conservative positive preflash budget and reviewed rollback
  before an isolated probe. Instrument internal/DMA/PSRAM free, minimum and
  largest blocks plus stack watermarks to establish actual peaks afterward.

Gate: reproducible network-only candidate, source manifest, estimated allocation
ceiling and recovery procedure. No dependency on recognition or speech playback.

## Phase 2. Implement the Linux text gateway

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

## Phase 3. Verify ordinary Wi-Fi and the text client

- [ ] Bring up saved Wi-Fi credentials in the diagnostic profile without cloud
  discovery, BLE app services, microphone or speech engine startup.
- [ ] Resolve a controlled ordinary LAN endpoint and send bounded text. Validate
  JSON and IDs before exposing answers to a consumer.
- [ ] Test association, bad credentials, dropped requests, timeout, malformed
  response, busy backend and cancel with a late answer. Require the next request
  to succeed after each recoverable failure.
- [ ] Record connection/reconnect and request peaks. Fix allocation failures in
  the isolated profile before adding VPN or audio workloads.

Gate: typed USB input reaches the test gateway over ordinary Wi-Fi and returns
bounded text. This is a transport control test, not native tailnet acceptance.

## Phase 4. Prove native MicroLink transport

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
- [ ] Save the network-only allocation peaks and API result before adding any
  speech workload. Face/capture coexistence belongs to the final joint check.

Gate: the robot itself makes authenticated requests to gianrtx across networks,
with measured direct and DERP behavior. A ping, successful registration or a
working LAN proxy does not satisfy this gate.

If native membership fails, report the exact blocker. A LAN relay remains a
possible deadline contingency, but changing the selected topology needs a decision.

## Phase 5. Accept the independent networking milestone

- [ ] Run at least 100 text turns and a 30-minute idle/reconnect session.
- [ ] Exercise cold boot, identity persistence, Wi-Fi change, direct/DERP paths,
  gateway restart, backend timeout, duplicate IDs and cancellation.
- [ ] Show a real Nanbeige answer on the serial console with the Mac forwarder
  stopped. Keep the microphone and motors off in the network-only profile.
- [ ] Deliver source/configuration hashes, exact startup/provisioning commands,
  measured memory peaks, transport timings and verified recovery instructions.

Gate: a reproducible ESP32-native tailnet text client and Linux gateway. Do not
mark this milestone blocked merely because local STT is not ready.

## Final joint check with speech

After the independent network and speech milestones, use their measured budgets
to build one candidate. The [speech plan][speech] owns model/workspace lifetimes.
This plan owns transport lifecycle, reconnection and network memory return.

- [ ] First connect typed USB input to the real gateway and feed the returned
  answer into local Ito. Verify speech cancellation and mouth closure.
- [ ] Then connect the chosen recognizer. If Parakeet is selected, measure audio
  upload separately from transcription and LLM time.
- [ ] Test coordination refresh/reconnect while the face and speech are active.
  Compare persistent VPN with an explicit release-before-speech path only if
  measured memory demands it. Verify release and reauthorization behavior.
- [ ] Repeat the combined budget, failure injection, long speech and physical
  power/restart checks. No stale answer, reset or audio underrun may be hidden.

Combined conversation is a separate result from the network-only milestone.
If the measured combination fails, retain both independent working artifacts
and report the exact simultaneous allocation that does not fit.

## Logs and delivery

Follow the [shared measurement and retention rules][measurement]. Record radio,
registration, direct/DERP route, DNS, request/cancel/reconnect timings, internal/
DMA/PSRAM peaks and stack watermarks. Linux results include cold/warm model
state, first-answer/completion time, process memory and GPU VRAM.

Gateway metadata lives in ignored `.local/metrics/stackchan.jsonl` with bounded
rotation. Retain private raw evidence outside builds; commit sanitized reports
under Ito `results/stackchan/<date>-native-tailnet/`. Keep keys, NVS, device
identity and conversation text out of routine logs and Git.

Commit units are the gateway contract/tests, ordinary Wi-Fi client, isolated
MicroLink proof, networking results/runbook and final joint integration. Public
exposure and changes to shared services or recovery layout are separate choices.

[research]: 2026-11-15-stackchan-tailnet-conversation.md
[speech]: 2026-11-15-stackchan-local-stt-ito-implementation.md
[measurement]: 2026-11-15-stackchan-tailnet-conversation.md#results-performance-and-logs
