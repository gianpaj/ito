# StackChan memory sharing results

The touch-free profile and reserved speech-workspace lifecycle run on the robot.
The original face remains. Oido has not run on this ESP32; its budget below comes
from a separate host allocation probe.

## Oido budget

Oido v2b with flash-backed weights, greedy decoding and no optional language
model peaks at 1,520,880 requested engine bytes on the host. Budget 2.2-2.5 MiB
for a trial with a 10-second ring, separate utterance storage and overhead.
Its 5,931,424-byte model file is flash storage, not mandatory PSRAM residency.
The [allocation report](oido-memory-report.md), [probe](oido-memory-probe.py) and
[measurements](oido-memory-measured.json) record exact exclusions and sources.
Quad-PSRAM speed, real microphone audio, accuracy and flash layout remain gates.

## Touch-free profile

| Measurement | Original profile | Touch-free profile |
|---|---:|---:|
| App image | 2,867,152 B | 1,988,128 B |
| Static DIRAM | 108,163 B | 87,835 B |
| Warm free internal RAM | 13,202 B | about 34,415 B |
| Post-face free PSRAM | 8,271,288 B | 8,295,108 B |

Menus, Home/status widgets, touch input and periodic touch reads are excluded.
Panel identification and PMIC polling remain. Local and normal builds pass.
The user confirms mouth movement during speech, closure afterward and no tap
response. Golden speech passes, greeting underruns are zero, and cancel flushes
in 18.6 ms. [Stage 1 data](stage1-results.json) and its
[trace](stage1-measurements.log) retain the measurements.
Native power/reset code is unchanged; physical off/on and battery tests were
not repeated.

## Shared memory

Ito reserves one 4,891,328-byte PSRAM pool and its 239,948-byte internal hot arena.
After a successful stop, another engine can borrow both ranges exclusively.
They remain allocated and do not appear as free heap. Resume reloads weights
and reconstructs engine state in place. The pool includes all six full-capacity
PCM buffers. Quiet-text scratch is separate and is freed on stop.

| Final profile measurement | Value |
|---|---:|
| Borrowable PSRAM pool while stopped | 4.665 MiB |
| Borrowable internal arena while stopped | 234.32 KiB |
| Additional free PSRAM during the loop | 3,087,580-3,088,108 B |
| Additional free internal RAM during the loop | 30,223-30,247 B |
| Largest free internal block | 19,456 B |
| Control task stack / minimum unused | 8,192 / 3,016 B |
| Weight reload time across 100 resumes | 447-448 ms |
| Probe-return to resume-complete interval | 710-730 ms, median 720 ms |

The last interval uses device log timestamps and includes USB polling. It is
not a direct API-call timer. Borrowable and heap-free capacities are disjoint;
the stopped PSRAM budget is about 7.61 MiB combined. Frontend state/stack,
worker stacks, queues, codec DMA and kernel resources remain resident.
The larger USB control stack uses about 4 KiB of the internal-RAM saving.

## Device checks

All 100 stop/borrow/full-overwrite/return/resume loops pass. Every resume restores
PSRAM-backed weights without recalibration. Five loops interrupt actual playback.
Eleven explicit golden commands produce 33 passing cases after workspace reuse:
dual/single-core 8-bit PCM `363d7d98` and dual-core 16-bit PCM `a8c2df73`.
Quiet numbers match `c4472e58`. There are no unexpected resets during the loop.

The final long-diagnostic check times out three stop requests, rejects borrowing
after each timeout, then completes the fourth request on the same connection.
Resume, three golden cases and a zero-underrun greeting pass afterward.
The recovery greeting reaches first I2S submission in 821.4 ms from text arrival.
Its compute RTF is about 1.001; `degraded=1` remains correct. DMA/acoustic latency
and CPU utilization are not measured.

The inference pool is never reallocated during the loop. Global heap readings
vary by 24 B internally and 528 B in PSRAM, and the largest free PSRAM block
varies from 2,752,512 to 3,080,192 B. These include the live face and allocator;
this report does not claim exact zero global heap drift. The reserved workspace
removes large-allocation reacquisition from the handoff.

[Stage 2 JSON](stage2-results.json) contains every cycle. The
[loop trace](stage2-measurements.log) and [recovery trace](recovery-measurements.log)
are sanitized serial extracts. Actual Oido capture/inference and native Tailscale
remain unimplemented. The microphone and motors stay off in this USB profile.

## Failures and verification limits

A 4 KiB control task overflowed during model layout on the first resume. The
8 KiB internal stack passes and reports remaining capacity. Separate heap-block
reacquisition also failed despite 7.98 MB free; the reported largest block was
3 MiB. The retained pool replaces that allocation strategy.

The first 100-cycle harness completed its loop, then its footer allowed only two
stop retries during the long diagnostic. That footer expectation failed. A
separate same-connection test proves three timeouts followed by successful stop,
borrow, resume and golden output. The report reconstructs cycle data from the
serial trace; unsaved host elapsed samples are not presented as measurements.

Host tests execute production lifecycle, allocation and checkpoint functions.
They cover bounds/alignment, failed startup/rebind, exact leases, timeout/error
ownership, DMA taint and concurrent stale-epoch rejection. ASan/UBSan pass.
A separate real portable-engine test overwrites both pools and reproduces golden
PCM across four runs. Host ABI pool sizes differ from native sizes. Neither host
test proves every IDF/espeak internal allocation failure.

## Provenance and use

Device code is StackChan `b115340` with Ito
`4b4b37fb02d014eebc01d4c5afb973b514db7d2b`, ESP-IDF 5.5.4, 240 MHz and quad PSRAM
at 80 MHz. The app is 1,992,304 bytes, SHA256
`2dca08fbc08099bfde6e7fe9fa1feaa4d822b6a22e1a30d864cdb37e9f4dfbb3`.
Model, assets, partition table and NVS layout are unchanged. App writes and
verification target only `0x20000`. Private images, ELF/map, configurations,
complete logs, failed candidates and validation scripts are retained outside
build directories with a checksum manifest. No private audio is recorded.

The [StackChan guide](https://github.com/gianpaj/StackChan/blob/feat/local-ito/firmware/LOCAL_ITO.md)
describes `memory`, `tts stop`, `tts probe`, `tts resume`, normal text commands
and recovery. USB is released after validation and the firmware is ready for text.
