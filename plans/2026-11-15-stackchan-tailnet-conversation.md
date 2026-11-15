# StackChan conversation research and plan index

Status: native tailnet membership selected; implementation has not started.
Execution is defined in two independent plans:

1. [Native Tailscale and remote LLM][execution] owns enrollment, Wi-Fi/VPN,
   the text gateway, network tests and the final joint integration gate.
2. [Local STT and Ito TTS][speech] owns microphone capture, the possible Oído
   model, Ito memory ownership, the original face, hardware-control probes and
   the selected Parakeet fallback if local recognition fails.

Networking can pass with typed USB text and console answers. Local speech can
pass with microphone input and fixture/USB answer text. Combine them only after
both independent results and their measured memory budgets are available.

This document preserves inspected facts, alternatives and shared measurement
rules. Use the linked execution plans for tasks and acceptance gates. The
[working speech results][baseline] remain the baseline and recovery reference.

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

## Sources

Source snapshots were inspected on 15 November 2026. Upstream benchmarks remain
upstream observations until reproduced on this StackChan.

[baseline]: ../results/stackchan/2026-11-15-original-face/README.md
[execution]: 2026-11-15-stackchan-native-tailnet-implementation.md
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
[speech]: 2026-11-15-stackchan-local-stt-ito-implementation.md
