# Agent Note: StackChan tailnet conversation

Status: proposed — Networking and recognizer integration remain unimplemented.

## Problem

The robot needs open-ended English conversation with private Linux reasoning.
Its 8 MiB quad PSRAM, limited internal SRAM and 16 MiB flash constrain running
voice inference, the original face and a native VPN together.

## Proposal

Use native MicroLink tailnet membership for remote LLM requests to gianrtx.
Keep Ito TTS and the original face on StackChan. Evaluate Oido v2b for local STT;
the user selected existing Parakeet on gianrtx if local fit or accuracy fails.
Networking and speech have independent plans and acceptance gates.

The touch-free shell and [reserved inference workspace][ownership] are
implemented. The lease makes memory available to another engine only while
Ito workers are stopped. It does not establish actual STT or VPN fit.
Networking can pass with typed USB input and console answers; speech can use
fixture/USB answers without a network. Keep one gateway contract and one joint
checklist in the networking plan.

## Alternatives considered

A nearby LAN relay remains a contingency requiring a topology decision; the
user selected direct tailnet membership. A full Xiaozhi server preserves its
voice protocol but adds services beyond the chosen text-only gateway. Remote
Parakeet remains the selected conditional STT fallback. ESP-SR wake words or
command lists do not supply the requested free-form transcripts.

## Acceptance criteria

The [research record][plan], [network plan][execution] and [speech plan][speech]
define the independent tests and final integration gate. Reuse installed Linux
weights and preserve occupied ports and Tailscale Serve routes. A local-model
result requires real microphone input, local recognition and local Ito output;
Parakeet must be reported as remote recognition when selected.

## Risks

Upstream octal-PSRAM timings do not establish Oido speed on this quad board.
MicroLink's internal stacks exceed the current general internal free heap.
The current two-slot flash layout does not also hold Oido. Reserved workspace
ownership, network task teardown and microphone/codec transitions need their
joint test before a working conversation claim.

[plan]: ../../../../plans/2026-11-15-stackchan-tailnet-conversation.md
[execution]: ../../../../plans/2026-11-15-stackchan-native-tailnet-implementation.md
[speech]: ../../../../plans/2026-11-15-stackchan-local-stt-ito-implementation.md
[ownership]: ../../implemented/architecture/2026-11-15-ito-runtime-lifecycle.md
