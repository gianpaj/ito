# Local conversation latency

The final image measures **1,648.1 ms from the last microphone read to first I2S
submission**, compared with the batch baseline's 6,800 ms device-log interval.
Final transcript to first I2S is **1,109.4 ms**. The stricter 1,500 ms input-end
target is missed by 148.1 ms. A fixed supplied reply replaces the LLM.

## Measured stages

| Final five-second microphone turn | Time |
|---|---:|
| Last RX read to drained input | 234.8 ms |
| Last RX read to final transcript | 538.7 ms |
| Final transcript to completed Ito restoration | 31.1 ms |
| Supplied reply text to first PCM | 587.1 ms |
| Supplied reply text to first I2S | 1,075.6 ms |
| Final transcript to first I2S | 1,109.4 ms |
| Last RX read to first I2S | 1,648.1 ms |

First PCM is inside text-to-first-I2S time; do not add them. The device
microsecond markers share one clock. The last RX read is a software input
boundary. Audible onset and actual speech-end detection are unmeasured.

## Bounded native checks

| Configuration | Capture-end to playback log | Last RX read to first I2S | Underruns |
|---|---:|---:|---:|
| Accepted batch baseline | 6,800 ms | unavailable | 0 |
| Streaming, eight frames, retained weights | 1,820 ms | invalid marker format | 0 |
| Streaming, four frames, retained layout | 2,520 ms | 2,538.9 ms | 0 |
| Streaming, six frames, cached initialization | 1,660 ms | 1,662.3 ms | 0 |
| Six frames, cached initialization and upstream weight preload | 1,640 ms | 1,648.1 ms | 0 |

These are four ambient microphone timing turns, one per candidate. They return
no speech and do not measure live speech accuracy or latency percentiles.
The input length and 38-byte supplied reply stay fixed. Legacy log endpoints
have coarser resolution and exclude some capture cleanup. The first streaming
candidate exposes unsupported 64-bit nano-printf formatting; its independent
device-log interval remains valid. Later images use exact integer-valued
double formatting and the host rejects malformed markers.

Four-frame recognition falls behind capture. Six frames reduce its final
partial chunk but still leave queued input. Preserving weights removes about
460 ms of copying. Caching 14,416 bytes of immutable trig tables reduces the
remaining restoration to about 31 ms. TTS startup buffering stays unchanged.

One public b05 WAV completes recognition with the same transcript as the
eight-frame host reference. Its supplied longer reply contains **7.05 seconds
of audio**, starts I2S after **1,148.6 ms** and reports **zero underruns**.
Live six-frame and batch eight-frame decoding differ by one word on the host
fixture, so this does not establish general six-frame recognition quality.

A fixture upload first fails before recognition because queued boot status
output interleaves with its acknowledgement. A bounded 200 ms quiet drain fixes
host readiness; the single retry completes. This failed upload is separate
from completed inference turns. No soak or repeated stability loop runs.

## Memory and provenance

| Final image measurement | Bytes |
|---|---:|
| Application image | 2,051,648 |
| Linked static DIRAM | 91,515 |
| Reserved shared hot arena | 239,948 |
| Reserved PSRAM pool, including retained Ito weights | 4,891,328 |
| Scratch-only PSRAM lease | 1,695,168 |
| Native six-frame Oido hot use | 193,456 |
| Native six-frame Oido PSRAM use | 1,273,120 |
| Optional Ito trig-table cache outside the lease | 14,416 |
| Free internal heap during capture / idle | 11,622 / 13,758 |
| Free PSRAM during capture / idle | 2,727,656 / 2,728,056 |
| Unused recognition-worker stack / capacity | 5,936 / 12,288 |
| Unused control stack after fixture / capacity | 6,620 / 8,192 |

Static sections, reserved regions and free heap are separate accounting views.
They must not be added together as a no-model footprint. Native runtime logs
report peak PSRAM use of 5,726 / 8,102 KiB and internal use of 390 / 393 KiB,
including boot diagnostics. The control stack sample follows the batch fixture;
capture-specific control-stack high-water was not recorded. No new task stack
is allocated for capture.

The flashed image is built from StackChan `ca36a65` and Ito `d11f910`.
Its SHA-256 is
`dbb885505894c97381c6d8835c6039e6ab5a8138250d88888851af8ac02b844c`.
Only the app partition is flashed. Model bytes, NVS, assets and partition-table
bytes are preserved. Source/image/tool/model/patch hashes and numeric clock
events are retained in [results.json](results.json). Private logs, PCM uploads,
ELF/maps, rollback image and checksums stay outside Git.

Focused host checks cover actual runtime ownership, cached/ordinary golden PCM,
adapter sessions, controller cleanup and USB timing/readiness. ASan/UBSan passes
for the affected C/C++ harnesses. Native boot golden comparisons pass. Fresh
battery/button, cancellation and recovery rehearsals remain outside this slice.

## Remaining target

The current tail and restoration leave approximately 927 ms for reply dispatch
and TTS startup within a 1,500 ms software-endpoint budget. TTS takes 1,076 ms.
The next slice needs a measured TTS startup below about 900 ms while preserving
gapless longer replies. Automatic speech endpointing and acoustic latency need
their own budget. Ito still reports `degraded=1`; neither an LLM nor networking
is installed by this work.
