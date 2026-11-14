# Original StackChan firmware with local Ito

Status: route 2 selected; implementation is pending the user's go-ahead. The
user requests notice before implementation. This planning change does not
modify or flash firmware. Keep the working green-dot image installed.

Use the original avatar, UI and board/codec implementation, with a local Ito
backend feeding bounded PCM through the original audio output path. Preserve
one I2S owner. Mouth animation follows actual playback and drain, not text
arrival or an empty queue alone.

The supplied source declares 1.4.2, while the factory backup is 1.6.0. Official
StackChan commit `94856a77876255ceee36f2a7ffae40f572eeb1f2` declares 1.6.0 and
is the proposed baseline. The separate ignored Xiaozhi checkout also needs a
verified revision/patch record. A parent Git commit is insufficient to reproduce
that dependency.

Copying the face into standalone Ito was considered for speed. The user chose
full original-firmware integration for fidelity and maintenance. Retain that
choice; do not substitute a copied renderer to avoid integration work.

The first proposed checkpoint is an unmodified source build and memory/flash
report, without changing the device. Later work needs a PCM adapter, measured
RAM and partition budgets, cancellation/drain handling and recovery rehearsal.
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
host tests, 2,337 frontend utterances and 169 frontend streams. Device behavior
for the shared-runtime extraction remains to be checked with the integration.

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
