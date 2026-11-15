# Local Ito speech in the original StackChan firmware

Status: implemented and device-verified. The original face speaks local Ito
output from USB text, with motors and microphone power off. Golden PCM,
cancellation, a 196-second paragraph and launcher re-entry pass. The
[implementation record](../.agents/notes/implemented/hardware/2026-11-14-stackchan-animated-face.md)
contains source/image hashes and results. Compute RTF is 1.0352; the degraded
warning remains. Conversation remains outside this phase.

## Goal and boundary

Integrate local Ito text-to-speech into the original StackChan application.
Reuse its avatar, mouth animation, display, menus and board/codec implementation.
Keep the USB interface familiar:

```text
text Hello, I am StackChan.
volume 50
cancel
status
```

The Mac supplies English text; normalization, phonemization and synthesis run
on the robot. The original face stays visible while idle and animates during
actual speaker playback. The first local-speech mode keeps motor and microphone
power off. Cloud conversation and local speech must not own playback together.

The user chose full original-firmware integration for fidelity and maintenance.
Copying the face into the standalone Ito image is not the selected route.

## Source baseline

The supplied checkout `/Users/gianpaj_it/tmp/StackChan` is at
`447e7dcd64744f73bc8b26fc50aa506d2dffc983` and declares firmware 1.4.2.
The verified device backup contains active firmware 1.6.0, built with IDF 5.5.4.

Use official commit `94856a77876255ceee36f2a7ffae40f572eeb1f2` as the proposed
version-matched source baseline. Its [CMake version declaration][source-version]
is 1.6.0. This matches the version number; it does not prove a reproducible
match to the factory binary. Do not use an unpinned moving branch.

The local `firmware/xiaozhi-esp32` is a separate, ignored Git checkout at
`e77dedb1309153bb63fed285772962c920c97dd4`. Its parent commit does not pin it.
Verify and pin the dependency revision and any patches required by the 1.6.0
source before relying on its audio API. Preserve the supplied checkout and its
untracked documents, simulator files and binary.

Implementation belongs in a separate StackChan feature worktree. Run `wt list`
before creating it. The user's StackChan fork is remote `upstream`,
`git@github.com:gianpaj/StackChan.git`; `origin` is M5Stack's repository.

## Intended audio path

```text
USB text -> local speech service -> Ito frontend and engine
         -> bounded PCM playback -> original codec -> speaker
                         |
                         +-> original avatar speaking/standby states
```

- Keep the original board and codec as the sole I2S owner. Import the Ito C
  engine, frontend, optimized kernels and scheduling logic through a pinned
  dependency/component boundary. Do not import Ito's `app_main` or board setup.
- Add one local-speech backend to the original application. Begin with an
  explicit local build/profile using the existing avatar screen. Preserve the
  cloud build; runtime switching and new settings UI are separate decisions.
- Use the original PCM output path. If the selected dependency lacks a raw-PCM
  submission API, maintain the adapter change in a tracked dependency revision
  or patch. Do not rely on edits hidden in an ignored dependency checkout.
- Start only the audio services needed in local mode. Its playback must not
  allocate microphone processing, wake-word or Opus tasks merely to speak PCM.
- Preserve original menus and avatar code. First validate the local speech path;
  do not claim unrelated original applications have been regression-tested.

## Playback contract

The existing audio queue contains PCM, but its public submission path accepts
encoded packets in the inspected checkout. Queue-empty also does not establish
that an in-flight chunk or I2S DMA has drained. Revalidate these details against
the pinned 1.6.0 dependency before changing its API.

- Match the scheduler's buffer count to the actual bounded playback pool. Apply
  backpressure and keep PCM ownership explicit until the consumer releases it.
- Drive the original speaking state when PCM starts reaching output. Drive
  standby only after the final samples drain. Use the display's existing lock
  and application context for UI calls.
- On cancel, invalidate the active text job, stop its producer, discard its
  queued PCM, flush in-flight output and close the mouth. Reject stale chunks
  from a cancelled job. Idle power management must not disable active playback.
- Keep main-loop/UI work independent of long synthesis. Reuse the original
  watchdog policy and preserve Ito's self-tests and failed-full row-split guard.
- Keep error reporting and the degraded flag truthful. Do not route synthesis
  to the Mac or buffer an entire utterance to conceal throughput limits.

## Checkpoints

### 1. Reproduce the source build, without changing the device

After approval, fetch and pin the selected StackChan source in an isolated
worktree. Audit its SDK, dependencies, patches and asset-generation commands.
Reproduce an unmodified build without flashing or contacting cloud activation.

Deliver a source/dependency manifest, build log, app size, linker memory map,
asset sizes and a proposed component boundary. Identify the actual audio and
avatar hooks in that pinned version. Report which baseline dependencies differ
from the supplied checkout. No Ito implementation or partition changes yet.

### 2. Finalize the memory and flash budgets

Use one approved female int4 model, 3,196,096 bytes. The working synthesis
profile uses a 239,948-byte hot arena in internal SRAM and a 1,579,920-byte bulk
arena in PSRAM. The complete original UI/runtime must fit around these needs.
The standalone image's free-memory figures are not the original app's budget.

The original display configures a 2 MB image cache and a 320-by-20 RGB565 DMA
buffer. Measure actual allocations and peak use; cache capacity is not evidence
that all of it is immediately allocated. Preserve the original face while
sizing its buffers and cache from measured needs. Keep the hot arena in SRAM.

The factory layout has two `0x4f0000` OTA slots and 4 MB of assets. It has no
unused 3.2 MB model slot. Propose a layout only after the baseline app and assets
are measured. Report whether retaining two OTA slots is feasible. Review the
layout before writing it; do not silently remove recovery or assets.

Before any layout change, capture the current Ito NVS safety state and retain
its tested images/models. Rehearse the verified full factory restore and the
return to the working Ito image. Record the commands, checksums and results.
The local layout keeps Ito's 24 KB NVS partition at `0x9000`, preserving guard
records without migration. OTA metadata starts at `0x10000`. The factory NVS is
16 KB. Restore a raw NVS snapshot only with its matching layout, so it cannot
overwrite neighboring partitions.

### 3. Implement the local backend in logical commits

First add the raw-PCM path and playback-state hooks using a known local PCM
reference. Verify bounded ownership, drain and cancellation. Then connect the
Ito frontend/engine and USB commands, keeping the same output contract.

Keep one synthesis worker and one active text job. Use the measured int4,
32-frame row-split profile. Retain self-tests and short calibration; the long
benchmark stays a manual diagnostic. Disable head-motion modifiers in local
mode. Preserve the original mouth animation rather than writing a new face.
Keep the engine arithmetic flags and host PCM self-test hashes unchanged.

### 4. Build, review and announce the first device write

Build the normal and local variants. Verify model and asset offsets, image
bounds, RAM placement and error behavior. Present the exact candidate images,
hashes, partition layout and rollback procedure before flashing. Tell the user
before the first device write. Keep credentials and private backups outside Git.

### 5. Validate the integrated firmware

Check original face/idle behavior, greeting, numbers, a long paragraph, volume,
cancel during playback and repeated requests. Compare a deterministic PCM case
with the host. Exercise cancellation while producing, queued and in flight.

Require zero playback underruns, no resets, stable warm-up memory and correct
mouth start/stop behavior. Check UI responsiveness, idle power management and
leaving/re-entering local mode through the original application lifecycle.
Record compute RTF independently of audible stability. Test the normal build
for changes to shared audio code. Commit and push each verified logical chunk.

## Use the deployed profile

Use the [StackChan local-mode guide](https://github.com/gianpaj/StackChan/blob/feat/local-ito/firmware/LOCAL_ITO.md)
for build and monitor commands. The robot is left on the original face with
local speech ready and the USB port released. Conversation and additional
performance work are separate follow-up work.

[source-version]: https://github.com/m5stack/StackChan/blob/94856a77876255ceee36f2a7ffae40f572eeb1f2/firmware/CMakeLists.txt
