# StackChan original-face speech results

Measured on 15 November 2026 on a physical StackChan. English text, normalization,
phonemization and synthesis run on the robot. The original face animates during
speaker playback. Motors and microphone power remain off.

[results.json](results.json) contains per-utterance timings, exact audio lengths,
memory snapshots, configuration and checksums. [measurements.log](measurements.log)
contains the measurement lines from the serial session.

## Performance

| Case | Utterances | Audio seconds | Compute seconds | Compute RTF | Underruns |
|---|---:|---:|---:|---:|---:|
| greeting | 1 | 2.4875 | 2.5263 | 1.01560 | 0 |
| numbers_quiet | 1 | 6.9250 | 7.0375 | 1.01625 | 0 |
| numbers_spoken | 1 | 6.9250 | 7.1159 | 1.02757 | 0 |
| paragraph | 26 | 196.0125 | 202.9019 | 1.03515 | 0 |
| greeting_after_reentry | 1 | 2.4875 | 2.5253 | 1.01520 | 0 |

The paragraph contains 4,704,300 samples at 24 kHz. Its
226.805-second observer wall time includes frontend work,
planned start delays, pauses between utterances and polling. Compute RTF is
compute time divided by audio duration; below 1 is faster than real time.
The strict below-1 target does not pass, so `degraded=1` remains enabled.
The paragraph plays with zero underruns using the bounded streaming scheduler.

The greeting's text-arrival-to-first-I2S-submission latency is 828.3 ms, and
829.5 ms after launcher re-entry. These exclude DMA and acoustic latency.
Cancel flushes in 19.8 ms. Queued sentences do not restart, and a following
numbers request succeeds.

Exact durations come from host-reference sample counts after token equality is
checked. The earlier aggregate RTF of 1.0352138 uses rounded logged durations;
exact sample counts give 1.0351478. Individual firmware RTF
values use their internal precision and are retained in the JSON.

## Memory

| Measurement | Value |
|---|---:|
| Physical flash / quad PSRAM | 16 MiB / 8 MiB |
| Hot arena in internal SRAM | 239,948 B |
| Bulk arena in PSRAM | 1,579,920 B |
| Linker static DIRAM | 108,163 B |
| Internal free after early hot reservation | 85,190 B |
| Internal free before / after avatar creation | 66,886 / 66,422 B |
| First boot warm internal free / minimum | 13,202 / 5,358 B |
| Internal free / minimum after re-entry | 13,242 / 5,414 B |
| PSRAM free after quiet-text scratch allocation | 2,418-2,419 KiB |
| Highest logged PSRAM / internal usage | 5,691 / 372 KiB |
| Logged allocator PSRAM / internal totals | 8,107 / 377 KiB |

The `MEM` lines truncate to KiB. `SystemInfo` reports bytes. Heap totals exclude
reserved regions and static external BSS, so they differ from physical capacity.
The linker remainder of 233,597 B is not a runtime free-heap reading or a
contiguous allocation guarantee. Warm internal free memory stays at 13,202 B
through the paragraph. The quiet-text test keeps an intentional PSRAM scratch
ring, accounting for its lower free-PSRAM reading.

The hot arena is reserved at IDF CORE priority 106, before C++ constructors and
DMA-pool subdivision. Ordinary UI allocation prefers PSRAM. DMA and task stacks
request internal memory. The LCD uses an eight-row DMA buffer; the USB console's
4 KiB text buffer is external BSS. The unused UART0 driver is not allocated.

## Correctness and behavior

- Both boot self-tests match host PCM `363d7d98`, 134,100 samples each.
- Quiet numbers match host tokens and PCM `c4472e58`. Spoken PCM hashes use random
  seeds and are recorded without comparison; they are not failed comparisons.
- All 26 paragraph utterances match host frontend tokens.
- The user confirms clear speech, mouth movement during playback, mouth closure
  afterward and stationary motors.
- Home returns to the launcher. AI.AGENT restores the face, passes another
  self-test and speaks a greeting with zero underruns.
- The failed-full split verdict and its counters are preserved. Row split remains
  active. There are no unexpected resets during the measured requests.
- Three touch-poll timeouts during initial calibration skip samples. The physical
  Home/re-entry check passes.
- Normal/local firmware builds pass with IDF 5.5.4. Runtime host tests cover seven
  cancellation/ownership scenarios. Frontend tests cover 2,337 singles and 169 streams.

## Reproduction and provenance

StackChan code: `f799097c265d8c3c5c7980704c4a14dfcd0f6218`. Ito runtime:
`b7412446a19e88bce34021d95c47d2bb81b2a953`. Hardware runs at 240 MHz, with QIO flash and quad
PSRAM at 80 MHz, a 32 KiB data cache and a 100 Hz FreeRTOS tick. The selected
profile uses female int4 weights, 8-bit activations, 32-frame chunks, six PCM
buffers and row split with GDMA/prefetch. Default volume is 35; spoken checks use 50.

[The StackChan guide](https://github.com/gianpaj/StackChan/blob/feat/local-ito/firmware/LOCAL_ITO.md)
contains build, boot and monitor commands. Exact test text is in the JSON.
`textq` is the deterministic numbers check; `text` is the speaker path.
Models and complete device backups remain outside Git.

App SHA256: `a5690f3955fe2f3b0ce360cbd7d0d2bdb31c3eda55dbb30a8146e99be59a0a1e`.
Raw serial SHA256: `9c4fed36711b3a55a55ae95d94fa5d1a330ebc9b76014d89935474ee79695fd6`.
The complete serial log, metadata, individual results, test commands, linker map,
ELF, SDK configuration and build logs are archived privately with checksums under
`original-ito-candidate-3/validation-artifacts` in the device backup. This archive
survives build-directory cleanup. The committed measurement trace omits device
identifiers, application logs and private filesystem paths.

This is one board, one complete paragraph run and one human listener. Acoustic
latency, cold power cycling, microphone/conversation and factory cloud/motor
functional regression are not measured here. Flash recovery is checked by a full
factory-image write/verify and a native-image rollback/boot check.
