# Agent Note: StackChan tailnet conversation

Status: proposed. The manual speech milestone is user-accepted; native networking and the joint gate remain unimplemented.

## Problem

The robot needs open-ended English conversation with private Linux reasoning.
Its 8 MiB quad PSRAM, limited internal SRAM and 16 MiB flash constrain running
voice inference, the original face and a native VPN together.

## Proposal

Use native MicroLink tailnet membership for remote LLM requests to gianrtx.
Keep Ito TTS and the original face on StackChan. Manual USB turns use Oído v2b
for local STT; the user selected existing Parakeet on gianrtx if local accuracy
fails its remaining acceptance tests.
Networking and speech have independent plans and acceptance gates.

The touch-free shell and [reserved inference workspace][ownership] are
implemented. The lease makes memory available to another engine only while
Ito workers are stopped. The native profile captures real microphone audio,
recognizes it locally and restores Ito for audible transcript echo or a supplied
USB reply. The user confirmed mouth animation and stationary motors. This
establishes local speech fit without a network. The [manual results][manual]
record 91 completed cycles: 20 public clips matching the host, 20 microphone
captures at 1, 3 and 10 seconds, and 51 digital-silence cycles with Ito replies.
There are 27 explicit passing golden cases and one boot PASS. The user requested
fewer passes, so the full 100-cycle target is deferred; the unobserved 92nd
recognition is excluded. Further native cancellation, battery/reset, Parakeet
comparison and recovery rehearsal are unrun. Networking can pass independently
with typed USB input and console answers. Keep one gateway contract and one
joint checklist in the networking plan.

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

The public-fixture WER is 19.63%; host parity does not establish perfect accuracy
or a broad quality estimate. Acoustic latency and wider intended-user coverage
are not established.
MicroLink's internal stacks exceed the current general internal free heap.
The conversation profile fits both speech models by using one application slot;
it requires USB recovery after a bad image. Reserved workspace ownership and
network task teardown still need their joint test before a native tailnet
conversation claim.

[plan]: ../../../../plans/2026-11-15-stackchan-tailnet-conversation.md
[execution]: ../../../../plans/2026-11-15-stackchan-native-tailnet-implementation.md
[speech]: ../../../../plans/2026-11-15-stackchan-local-stt-ito-implementation.md
[ownership]: ../../implemented/architecture/2026-11-15-ito-runtime-lifecycle.md
[manual]: ../../../../results/stackchan/2026-11-15-manual-oido/README.md
