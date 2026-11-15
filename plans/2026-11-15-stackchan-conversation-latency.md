# StackChan local conversation latency

## Goal and measurement

Keep Oido STT, Ito TTS and the original speaking face on the ESP32. Replace the
LLM with the benchmark's fixed supplied reply. Target less than 1,500 ms from
the last captured input sample to the first output submission, with zero output
underruns. Report final-transcript-to-output separately. I2S submission excludes
DMA and acoustic onset, so this target alone does not prove audible latency.

The accepted baseline records five seconds, then performs all recognition.
The user's second run measures 4,991.0 ms STT, 729.2 ms restoration/control and
1,066.7 ms text-to-first-I2S. Capture-end to playback spans 6,800 ms. First PCM
is ready after 578.2 ms. The remaining TTS wait includes scheduled buffering.

## Scope and constraints

Preserve USB `listen`, `send`, `cancel`, `echo` and `text`, the face and motor
clamps. Keep the ten-second capture bound. Start with manual recording endpoints;
automatic silence detection and its latency budget are a separate slice.
No network, LLM, wake word, always-listening or full-duplex work is included.
Use the existing two task worktrees and retain the working firmware image.

## 1. Preserve copied Ito weights

- Add an explicit scratch-only workspace lease alongside the destructive lease.
  Lend the hot arena and PSRAM following the copied weights. Returning the exact
  lease preserves the weight bytes, while resuming rebuilds hot/bulk/PCM state.
- Keep destructive borrowing compatible and reload weights after it. Failed or
  uncertain ownership must retain the existing stopped/fault behavior.
- The reserved PSRAM pool is 4,891,328 bytes. Its weight region is 3,196,160
  bytes, leaving 1,695,168 bytes. Native Oido uses 1,309,152 bytes. Adjust Oido's
  conservative admission bound only with allocation-limit verification.
- Update the owning runtime lifecycle note and cover scratch/destructive leases
  with the existing actual-code host harness. Commit this chunk separately.

## 2. Recognize while recording

- Split the existing Oido adapter into begin/feed/finish/close operations, keeping
  the batch wrapper for uploaded WAV diagnostics and existing tests.
- Complete model validation and setup before the LISTENING cue. Capture must
  continue while a feed call runs an encoder chunk. Use the existing bounded PCM
  buffer with the USB control task as capture producer and the recognition
  worker as consumer. Poll USB without waiting while capture is active, and
  give its producer priority over recognition. This adds no task stack.
- Never infer directly in the microphone read loop, since chunk work can exceed
  the RX DMA window. Publish samples only after their writes complete. Measure
  the existing control stack high-water mark after its capture responsibilities.
- On `send` or the recording cap, finish capture, drain published PCM, finish
  recognition, close all Oido users and return the lease before Ito resumes.
  Cancellation and failed capture also join the producer before returning memory.
- Log final input, drained input, final transcript and resume completion with
  device monotonic timestamps. Keep setup, compute, backlog and finish visible.
- Update the conversation ownership note. Commit this chunk separately.

## 3. Reduce startup delay where measurements justify it

- Measure streaming and preserved-weight restoration before changing scheduling.
- Try a smaller first Ito chunk while keeping the steady chunk and existing
  underrun protection. Compare first PCM and first I2S time for the fixed reply.
- Do not globally force zero buffering. The baseline whole-utterance RTF is
  about 1.015, so long replies can drain their buffer. Retain a safe default if
  a short probe produces underruns or does not improve the complete turn.
- If the remaining Oido finish cost dominates, evaluate a smaller streaming
  encoder chunk against the same speech fixture and memory bounds.

An eight-frame native streaming turn reduces the legacy device-log interval to
1,820 ms with zero output underruns. Four-frame chunks take 5,606.6 ms of feed
work for five seconds of audio and leave a backlog, increasing the interval to
2,520 ms. Use six frames as the next bounded candidate. Its host fixture differs
by one word from chunk eight; keep the batch diagnostic at eight frames.

Retained-layout restoration still takes about 244 ms. Cache the immutable
trigonometric initialization tables in a separate optional 14,416-byte PSRAM
block. Rebind every context pointer and preserve exact table bytes. Keep full
initialization as the fallback. Verify cached initialization against ordinary
initialization and golden PCM before flashing. Keep TTS buffering unchanged if
this candidate meets the latency target.

## 4. Minimal validation and saved results

- Run only the affected runtime, adapter/controller and benchmark host checks.
  Use existing sanitizer harnesses where available, without adding soak loops.
- Build the conversation profile. Archive its image/hash/configuration and
  flash only the app partition, preserving models, NVS and the partition table.
- Start with one five-second native benchmark. If it exposes a problem, fix that
  problem and repeat once. Use one known speech fixture to check recognition.
- After scheduling changes, run one short and one longer reply to check startup
  and underruns. Stop once these targeted checks answer the latency question.
- Save sanitized metrics, image/source hashes, memory/stack usage and limitations
  under `results/stackchan/`. Keep private audio/transcripts outside Git.
- Report whether 1,500 ms is achieved. If it is not, name the measured remaining
  stage instead of extending the test run. Commit results and push both branches.

## Alternatives and trade-offs

Batch recognition preserves simple capture but adds the full STT duration after
speech. Streaming moves that work into recording and needs a producer/consumer
boundary. Lending the complete pool maximizes scratch capacity but overwrites
weights and adds about 460 ms to restoration. Scratch-only lending fits the
measured model while retaining one exclusive hot arena. Server STT remains a
fallback outside this local implementation. Automatic endpointing is deferred
to keep the first latency result independent of silence detection.
