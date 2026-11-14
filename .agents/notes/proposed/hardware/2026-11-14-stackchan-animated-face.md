# StackChan animated face integration

Status: proposed; implementation route needs selection. The user requests the
original talking face, or a copy, with USB text and local Ito speech.

The original `SetStatus()` installs a timed `SpeakingModifier`; it does not
require the external AI model for mouth animation. Neutral geometry and the
180 ms speaking cadence are available in the supplied source.

Recommend porting that small renderer behavior into the working Ito firmware
for the deadline. Full original-app integration also needs an audio-service
adapter, a memory budget and a model partition. Keep one I2S owner.

The current dot firmware is a tested rollback image. Preserve its native
synthesis profile and use the existing playback-state callback for the face.
The design, source anchors, alternatives and checks are in the
[face integration plan](../../../../plans/2026-11-14-stackchan-animated-face-ito.md).
