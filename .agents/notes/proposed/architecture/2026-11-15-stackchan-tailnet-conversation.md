# StackChan tailnet conversation investigation

Status: proposed implementation. The user selected native tailnet membership.
The [research record][plan] preserves source pins and alternatives. Two plans
define independent tasks and gates: [networking][execution] and
[local STT with Ito TTS][speech]. Implementation has not started.

The preferred target keeps open-ended English STT, Ito TTS and the original face
on StackChan, with only the LLM on gianrtx. Native tailnet membership is a measured
experiment. The user selected existing remote Parakeet as the STT fallback.
A nearby LAN relay remains a contingency requiring a topology decision.

The main constraints are internal SRAM and model storage. Existing Ito leaves
13,202 B internal free; unmodified MicroLink's task stacks require 42 KiB before
its other allocations. Oído v2b offers a flash-resident local STT candidate, but
its upstream octal-PSRAM timings do not establish performance on this quad board.
Neither engine provides a demonstrated repeated STT/TTS allocation swap.

Networking can pass with typed USB input and console answers. The local speech
path uses microphone input and fixture/USB answers without networking. Parakeet
adapter tests can use host-assisted PCM transfer; wireless recognition requires
the joint check. Keep one canonical gateway contract and one joint checklist in
the network plan. Combine only after independent results and measured budgets.

Reuse installed Linux model weights and preserve occupied ports and Tailscale
Serve routes. A full Xiaozhi stack is an alternative if protocol compatibility
becomes necessary; it is not required for text-only local speech.

[plan]: ../../../../plans/2026-11-15-stackchan-tailnet-conversation.md
[execution]: ../../../../plans/2026-11-15-stackchan-native-tailnet-implementation.md
[speech]: ../../../../plans/2026-11-15-stackchan-local-stt-ito-implementation.md
