# StackChan animated face with local Ito speech

Status: proposed. The green playback dot is implemented, tested and confirmed
by the user. This plan describes the next step; no face integration is installed.

## Goal

Send English text over USB and hear local Ito speech while the original-style
StackChan face animates its mouth. Keep the current monitor commands:

```text
text Hello, I am StackChan.
volume 50
cancel
```

The text frontend and speech model run on the robot. The Mac supplies text.
Use the neutral white face on black, with a closed mouth while idle. During
playback, animate the mouth; close it when playback drains, is cancelled or
fails. Keep the face visible while idle. Motors and microphone power stay off
for this text-to-speech demo.

## Two implementation routes

1. **Copy the original face into the working Ito firmware. Recommended.** Port
   its neutral eye/mouth geometry and speaking cadence into the small LCD
   renderer. Reuse the tested local voice, USB commands and playback callbacks.
   This is the shortest path to the deadline demo.
2. **Add local Ito speech to a copy of the full original firmware.** Reuse the
   original avatar classes and application UI, then add a local text-to-speech
   mode. This requires audio-service, memory and partition work before it is
   ready to flash. Choose this when the original menus and app modes matter.

Route 1 copies the appearance and mouth behavior. Route 2 preserves the
original UI implementation. The initial work needs only neutral eyes and a
speaking mouth; idle blinking and additional expressions can follow separately.

## Source evidence

Reference checkout: `/Users/gianpaj_it/tmp/StackChan`, HEAD
`447e7dcd64744f73bc8b26fc50aa506d2dffc983`. Paths below are relative to it.

| Source | Useful behavior |
| --- | --- |
| `firmware/main/hal/board/stackchan_display.cc`, `SetStatus()` | Speaking adds `SpeakingModifier(0, 180, false)`; standby removes it and closes the mouth |
| `firmware/main/stackchan/modifiers/speaking.h` | Alternates open/closed mouth weights every 180 ms; head motion is optional |
| `firmware/main/stackchan/avatar/skins/default/` | Neutral colors, eye geometry and mouth size/radius interpolation |
| `firmware/xiaozhi-esp32/main/audio/audio_service.cc`, `AudioOutputTask()` | Existing PCM playback queue feeds `codec_->OutputData()` |
| `firmware/main/hal/board/cores3_audio_codec.cc` | Original firmware owns the board's I2S and codec devices |

The mouth animation is driven by speaking state and a timer. It does not need
the external AI model or phoneme alignment. Keep source attribution and license
notices when porting code.

## Recommended route, step by step

### 1. Draw the idle face

- Retain the current dot image as the known-working rollback firmware.
- Extend `esp32/firmware/main/stackchan_display.c` to draw the original neutral
  eyes and closed-mouth geometry. Use the existing LCD driver and row buffer.
- Keep the face lit while idle. Leave audio initialization and USB parsing intact.
- Check the physical appearance before adding animation.

Completion: the original-style idle face is visible and `text` still speaks.

### 2. Connect mouth animation to actual playback

- Reuse `stackchan_display_playing(bool)`. Its caller already marks the first
  successful I2S submission, drained playback and cancellation flushes.
- Have that callback notify a small, low-priority display worker. Keep LCD
  drawing out of the audio task. Only one context owns animation drawing.
- Animate only the mouth region at the original 180 ms cadence. Reuse the
  original open-weight range of 40..80 and closed range of 0..20.
- Stop animation and draw the closed mouth after playback ends or is cancelled.
  Silent `textq` checks must leave the mouth closed.
- Use one bounded drawing buffer and a fixed worker stack. Avoid per-frame
  allocation. Preserve the synthesis hot arena in internal SRAM.

Completion: the mouth follows sound playback, including the stored greeting.

### 3. Verify and save the demo

- Check greeting, numbers, a longer paragraph and cancellation on the device.
- Require zero playback underruns, no resets and stable memory after warm-up.
  Compare a deterministic PCM case with the host reference.
- Check that the 239,948-byte hot arena remains in internal SRAM. The dot
  firmware leaves about 29 KB free internal SRAM after warm-up, so measure
  animation stack and buffer use before retaining them.
- Keep the measured RTF/degraded warning truthful. If rendering causes gaps,
  reduce its work; keep synthesis on the robot and retain bounded audio buffers.
- Keep fast startup, volume controls and existing model self-tests. Save the
  image, hashes and serial logs, then commit and push the tested chunk.

## Full original-firmware route

If route 2 is selected, start with a separate Worktrunk worktree and a build of
the supplied source. Preserve its existing untracked files and the working Ito
image. First measure memory with the original face and a local-demo mode.
The current display wrapper configures a 2 MB image cache and a 320-by-20 RGB565
DMA buffer. Their real allocation/use must fit beside Ito; the wrapper cannot
be assumed to fit unchanged.

Import Ito's C engine, frontend and one approved int4 model. Keep the original
board/codec as the sole I2S owner. Add a bounded raw-PCM submission path to the
existing audio service; do not initialize a second I2S driver or encode PCM to
Opus merely to decode it again. Put external-AI audio and local Ito in mutually
exclusive modes.

Add bounded USB `text`, `volume`, `cancel` and `status` handling for local mode.
Drive the existing avatar speaking/standby states from PCM playback. Disable
head-motion modifiers and motor power for the first local demo.

Inspect the app size and design a reviewed partition layout for the model and
assets. The factory layout has two large OTA slots and assets; it has no spare
3.2 MB model slot. Rehearse recovery before changing that layout. Complete
native speech and memory checks before restoring optional original features.

## Decision to make

Approve route 1 for the deadline face demo, or route 2 for integration into the
full original app. Keep the current green-dot firmware installed until that
choice is made and the chosen implementation passes its device checks.
