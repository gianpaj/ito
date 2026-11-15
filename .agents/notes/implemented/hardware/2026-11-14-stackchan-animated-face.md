# Original StackChan firmware with local Ito

Status: implemented and verified on the robot. Local English speech drives the
original face, with motors and microphone power off. The user confirms clear
speech, mouth animation and launcher re-entry. The deployed StackChan code is
`f799097`, using Ito runtime `b741244`.

Use the original avatar, UI and board/codec implementation, with a local Ito
backend feeding bounded PCM through the original audio output path. Preserve
one I2S owner. Mouth animation follows actual playback and drain, not text
arrival or an empty queue alone.

The supplied source declares 1.4.2, while the factory backup is 1.6.0. Official
StackChan commit `94856a77876255ceee36f2a7ffae40f572eeb1f2` declares 1.6.0 and
is the pinned baseline. Git revisions, registry components and the Xiaozhi patch
are pinned in the StackChan implementation branch. A parent Git commit alone is
insufficient to reproduce the ignored dependency checkouts.

Copying the face into standalone Ito was considered for speed. The user chose
full original-firmware integration for fidelity and maintenance. Retain that
choice; do not substitute a copied renderer to avoid integration work.

The baseline build, local PCM adapter, normal/local builds and flash-recovery
checks pass. Integrated memory, playback, cancellation and launcher re-entry checks pass.
The source anchors, boundaries and checkpoints are in the
[integration plan](../../../../plans/2026-11-14-stackchan-animated-face-ito.md).

## Implementation authorization

The user approved implementation and coordinated sub-agents on 2026-11-14.
The StackChan worktree is `/Users/gianpaj_it/tmp/StackChan.feat-local-ito`,
branch `feat/local-ito`, based on official 1.6.0 commit `94856a7`.
Dependency/bootstrap, reusable Ito runtime, and original board/audio work have
separate owners. The primary agent owns integration and device validation.

## Shared runtime

The reusable IDF component is `esp32/runtime`, alongside `esp32/frontend`.
It compiles the shared runtime with `ITOFS_EMBEDDED`; the standalone app keeps
its board setup. Codec callbacks preserve the original firmware's I2S ownership.
The component keeps six PCM buffers, scheduler calibration, self-tests and the
split guard. A second service implementation was rejected because it would
repeat those contracts.

The embedding application owns NVS initialization and its watchdog. The embedded
component cannot erase or deinitialize global NVS, initialize a second codec,
or take over the hardware watchdog. Startup reserves the 239,948-byte hot arena
in internal SRAM and rejects a PSRAM fallback. The service is a device-lifetime
singleton. Reinitialization and runtime cloud switching are outside this phase.

Cancellation tags text and PCM with a job generation so queued sentences cannot
restart after cancel. Playback callbacks run after the first output submission
and after final drain or flush. The original avatar owns its rendering and lock.

Validation passed for the standalone and embedded IDF builds, scheduler/split
host tests, 2,337 frontend utterances and 169 frontend streams. Device behavior for the shared runtime is verified by the integration below.

## Baseline and storage decision

The original StackChan build passed before code changes. Its app is 3,730,352
bytes and generated assets are 2,298,029 bytes. Its static internal memory use
requires a local profile without unused Bluetooth/controller, camera startup,
cloud audio services or SR model loading. The normal profile retains these paths.

The local layout keeps the existing Ito NVS at `0x9000`, size `0x6000`, so its
failed-full safety verdict stays in the same matching layout. OTA metadata moves
to `0x10000`. Two 4.75 MiB OTA slots start at `0x20000` and `0x4e0000`.
One int4 model occupies `0x9a0000`, capacity `0x310000`; assets have 3 MiB at
`0xcb0000`. Image size and runtime memory checks must pass before deployment.
A verified private NVS snapshot is retained with the device backups.

## Device validation

The deployed app is 2,867,152 bytes, SHA256
`a5690f3955fe2f3b0ce360cbd7d0d2bdb31c3eda55dbb30a8146e99be59a0a1e`.
Its hot arena remains 239,948 bytes in internal SRAM. Ordinary UI allocation
prefers PSRAM; task stacks and DMA request internal memory. Initialization uses
an IDF CORE priority-106 reservation hook, a 32 KB DMA reserve, flash-resident
heap/non-ISR ring-buffer functions and an eight-row LCD buffer. Engine arithmetic
is unchanged. Failed-full guard counters are preserved.

The user confirms the original face, clear speech and mouth start/stop behavior.
The golden self-test matches PCM `363d7d98`; quiet numbers match `c4472e58`.
Greeting and spoken numbers have zero underruns. Cancel flushes in 19.8 ms,
discards queued sentences and allows a following request. A 26-utterance,
196-second paragraph passes with zero underruns, no unexpected resets and stable
warm memory. Aggregate compute RTF is 1.0352; `degraded=1` remains truthful.

Home returns to the original launcher. AI.AGENT restores the face, reruns its
self-test and calibration, and speaks another greeting with zero underruns.
Final free internal memory is 13,242 bytes, with a 5,414-byte minimum. The USB
monitor is closed so the user can open it directly.

Logs and JSON results are in the StackChan worktree's
`firmware/build-local-ito/device-tests/`, session `20261115T075242.489421Z`.
Private candidate 3, rollback manifests and the NVS snapshot stay with the
verified device backup. The full factory flash was restored and verified without
booting it. Native rollback images and matching NVS were restored, verified and
boot-checked. Factory cloud/motor operation is outside this validation.

The [StackChan local-mode guide][local-guide] owns build, monitor and boot
commands. USB-only resets can preserve the cached download strap on this unit;
the guide uses esptool's whole-chip reset after flashing.

[local-guide]: https://github.com/gianpaj/StackChan/blob/feat/local-ito/firmware/LOCAL_ITO.md
