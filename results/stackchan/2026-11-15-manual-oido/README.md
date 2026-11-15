# Manual local Oido and Ito results

Physical StackChan validation on 15 November 2026 stopped at the user's request
for fewer passes after **91 completed STT/Ito turns**.
The planned 100-turn stress run was not completed. Turn 92 was recognizing when
logging stopped and is excluded from completed-turn and speech claims.
The profile records or accepts USB PCM, recognizes it locally with Oido v2b,
then accepts supplied USB answer text for Ito playback with the original face.
It uses no external responder, local LLM or speech language-model decoder.
The acoustic model is mostly flash-backed with no optional weight relocation.
Mandatory transposed depthwise weights are included in the measured workspace.
This is record-then-recognize, not recognition while audio is being captured.

[results.json](results.json) contains numeric metrics and allowlisted public
transcripts. Raw serial logs, commands and microphone transcripts remain in the
private device archive. No microphone or silence transcript strings are copied here.

## Public recognition

| Group | Clips | Match greedy host | WER | Setup + feed + finish RTF | Feed + finish RTF |
|---|---:|---:|---:|---:|---:|
| all | 20 | 20 | 19.63% | 0.9690 | 0.8560 |
| demo | 3 | 3 | 25.58% | 0.9665 | 0.8579 |
| real | 7 | 7 | 21.43% | 0.9960 | 0.8639 |
| rooms | 10 | 10 | 17.22% | 0.9548 | 0.8511 |

The public corpus has seven real recordings, ten adverse-room variants and three
public demo recordings. Inputs are mono PCM16 at 16 kHz, at most ten seconds,
without trimming. WER uses lowercase word-token Levenshtein distance against the
public references. Host parity is separate from correctness against those references.
The [fixture manifest](../2026-11-15-local-stt-ito/oido-public-fixtures.json) retains
source URLs, references and source/decoded hashes.

STT timing includes setup and SHA256 verification of the flash-backed model.
It excludes USB upload and Ito stopping/restoration. Per-clip observer elapsed
time includes upload and restoration through conversation READY.

## Transitions and playback

The run records 91 completed API STT/Ito cycles: 20 public, 20 microphone and 51 silence turns.
It records 20 bounded microphone captures, 9
golden-test commands and 28 individual engine self-tests.
Observed Ito timing lines total 0 underruns.
The run was stopped before the separate final quiet-numbers and greeting checks;
those checks are not claimed. The nine explicit golden commands produced 27
passing comparisons, plus one boot comparison. These are distinct from the
91 completed speech turns.
The user confirmed the human microphone loop, audible post-capture greeting and
transcript echo, mouth animation, and stationary motors. One proper name was
misrecognized. Human utterance text remains private. These confirmations do not
establish audibility of every automated turn.
All observed check results and the intentionally incomplete stress target are retained in JSON.

Ito's strict compute RTF below 1 remains unmet, and `degraded=1` remains truthful.
The controller preserves half-duplex ownership. Oido borrows the retained hot and
PSRAM workspaces only after Ito stops, and returns them before Ito resumes.

## Independent monitor confirmation

The user confirms that `listen 5`, followed by `echo` after
`CONVERSATION READY`, works from their own terminal. The supplied log records
80,000 samples in five seconds, no clipping, successful audio cleanup and zero
playback underruns. Recognition setup, feed and finish total 4,923.4 ms;
Ito weight reload takes another 460 ms. Text-to-first-I2S submission is 833.5 ms.

[Sanitized confirmation](manual-monitor-confirmation.json) retains the reported
metrics without the private utterance. This separate user-run example does not
extend the 91-turn automated run or add another agent device pass.

## Automated latency benchmark

The host [benchmark](../../../esp32/tools/stackchan_benchmark.py) uses the existing
firmware and sends a fixed supplied reply after conversation READY. One five-second
ambient-microphone trial is retained in [latency-benchmark.json](latency-benchmark.json).
Oido reports no speech in that input; this measures timing, not recognition quality.
The supplied reply is "This is a manual reply from StackChan."

| Metric | Time | Boundary |
|---|---:|---|
| STT setup + feed + finish | 4,982.2 ms | Firmware counters |
| STT report to conversation READY | 728.3 ms | Host observer, including Ito restoration/control |
| Transcript to supplied-reply dispatch | 1.25 ms | Host observer, no human/LLM wait |
| Reply text to first PCM ready | 584.8 ms | Firmware counter |
| Reply text to first I2S submission | 1,073.1 ms | Firmware counter, includes prebuffer wait |
| Recording-end log to playback-start log | 6,790 ms | One device log clock |
| Listen command to playback-start log | 11,904.3 ms | Host observer, includes five-second recording |

The 3.62-second reply reports zero underruns. PCM readiness occurs within the
text-to-first-I2S interval; these two times must not be added. I2S submission and
the playback callback are not acoustic onset. Device log timing is limited by
the firmware tick; host timing includes USB delivery. The measured post-recording
host interval is 6,793.2 ms. A single trial does not establish percentiles.
The [benchmark guide](../../../esp32/BENCHMARKING.md#stackchan-manual-speech-latency)
defines every metric and the JSON/CSV outputs. The firmware is unchanged.

## Memory

The profile retains 239,948 bytes of internal hot storage and 4,891,328 bytes
of PSRAM workspace. Oido uses 204,720 bytes of the hot reservation and
1,309,152 bytes of PSRAM per recognized turn. This includes mandatory transposed
depthwise weights and streaming state, distinct from reserved capacity. A separate
320,000-byte recording buffer uses ordinary PSRAM heap. Free heap excludes the
reserved inference regions.

The 12 KiB conversation stack and 8 KiB console stack are reserved before
constructors to avoid late contiguous-stack allocation failure. The conversation
worker retains at least 5,760 unused bytes; observed minimum free internal heap
is 4,134 bytes.

| Phase | Internal free bytes | PSRAM free bytes |
|---|---:|---:|
| uploading | 14,006-14,122 | 2,741,548-2,742,984 |
| recognizing | 14,006-14,122 | 2,741,548-2,742,984 |
| restoring | 14,006-14,026 | 2,741,548-2,742,768 |
| idle | 14,006-14,026 | 2,741,548-2,742,768 |
| recording | 11,942-11,942 | 2,740,964-2,741,148 |

The linked image has 91,528 bytes of static internal DIRAM and 92,088 bytes of
external BSS. Oido's 11,296-byte BSS is entirely external. Compared with the
rebuilt local USB profile, static internal storage rises 3,360 bytes and app image
size rises 55,120 bytes. Static sections, free heap, largest blocks and retained
workspace capacity describe different quantities. `MEM` KB values truncate KiB;
SystemInfo and phase readings use bytes. Full ranges, stack watermarks and DMA
readings are retained in JSON, including first/last values to expose drift.
Phase ranges include the observed partial turn 92; completed-turn counts exclude it.

## Failures retained during development

- Candidate 1 recognized a public WAV and returned to Ito echo with zero logged underruns.
- Candidate 2 failed a late 8 KiB console allocation despite sufficient total free heap.
- Candidate 3 reserved the worker/console stacks early and matched four public clips, but microphone RX DMA allocation failed.
- Candidate 4 reduced the worker stack to 12 KiB and captured bounded audio; capture setup reset microphone gain.
- Candidate 5 preserved microphone gain, but the user reported silent post-capture TTS while a cold-boot greeting was audible.
- Candidate 6 checks amplifier standby/reset, PLL, clocks and switching readiness. Its user-stopped run and separate physical acceptance are reported above.

## Provenance and limits

StackChan code: `ddc6ea8ffea07b61296e35824ed30c4e777f7a6a`. App SHA256:
`b78e5d70581f6cdc3d88d6270a796034eef00d218c090ad613050b6f912d15c8`.
Oido is pinned to `c8d60325ba8bffd4bad65a9ac63c713ee64d1aae`; model SHA256:
`9e8b40913f532fb44b716a1f882f38b3b21e220713e417899aba32ace8c35066`. Candidate artifact and input hashes are in JSON.
The private archive is `20261115-oido-manual/validation6` and the matching
candidate artifacts are in `candidate6`. Normal and local USB firmware
build checks also passed. Their image hashes and OTA bounds are recorded in JSON.
The archived generator refuses
completed reports without validation's completion marker. A stopped report instead
requires explicit user-stop metadata and retains its actual completed count.

This manual USB milestone works; the wider production plan is not complete.
The public set includes ten noise variants with shared reference sentences, so
its mixed WER is not a broad quality estimate. Capture overflow counters were
not instrumented, and CPU utilization was not sampled. Exact capture caps are
checked, but zero RX overflows are not claimed.

This is one board. No live simultaneous STT/TTS, wake-word flow, full-duplex echo
cancellation, external reasoning service, or acoustic latency is established here.
Private human utterances are excluded from committed evidence.
