# Four user-run offline voice benchmarks

Four runs on one StackChan measure **1,465.7 ms average** and **1,474.2 ms sample
p95** from the final microphone read to first I2S submission. All four are below
1,500 ms for this fixed reply. The replies report zero output underruns.

Oido STT and Ito TTS run on the ESP32-S3 with 8 MB PSRAM and the original face.
The computer supplies fixed reply text over USB after recognition completes.
There is no LLM call. These measurements exclude boot, DMA and acoustic onset.

## Average and sample p95

| Device-timed interval | Average | p95 |
|---|---:|---:|
| Final microphone read to first I2S | 1,465.7 ms | 1,474.2 ms |
| Final microphone read to final transcript | 526.7 ms | 538.0 ms |
| Final transcript to completed Ito restoration | 28.3 ms | 30.9 ms |
| Final transcript to first I2S | 939.0 ms | 941.0 ms |
| Supplied reply text to first I2S | 907.8 ms | 908.0 ms |
| Supplied reply text to first PCM ready | 661.6 ms | 661.8 ms |

The average is the arithmetic mean of the unrounded saved measurements. p95
uses nearest rank, sorted sample number `ceil(0.95 × n)`. With four samples,
that is the maximum. This small descriptive p95 does not establish a population
percentile or predict other replies, voices or devices. First PCM readiness is
inside text-to-first-I2S time and must not be added to it.

| Run UTC | Final read to first I2S | STT tail | Ito restoration | Text to first I2S | Underruns |
|---|---:|---:|---:|---:|---:|
| 17:59:53 | 1,444.7 ms | 505.3 ms | 28.1 ms | 908.0 ms | 0 |
| 18:00:31 | 1,474.2 ms | 534.6 ms | 28.8 ms | 907.9 ms | 0 |
| 18:01:28 | 1,469.7 ms | 528.7 ms | 30.9 ms | 907.5 ms | 0 |
| 18:12:12 | 1,474.1 ms | 538.0 ms | 25.5 ms | 907.6 ms | 0 |

## Reproduce the workload

From this Ito checkout, with the conversation firmware installed and the monitor
closed:

```sh
python esp32/tools/stackchan_benchmark.py \
  --port /dev/cu.usbmodem1101 \
  --seconds 5 \
  --volume 100 \
  --reply "I'm doing well Gianfranco. How's the weather in Madrid?"
```

The user runs this command four times on 15 November 2026. Each run captures
80,000 samples at 16 kHz without clipping and reports successful cleanup.
The first returns no speech; the other three return text. Input transcripts
remain private, and recognition accuracy is not scored.

This 55-byte reply produces two TTS utterances. First-audio timings describe
the first utterance; underruns cover both. It is a different workload from the
38-byte single-sentence [development baseline](../2026-11-15-streaming-latency/README.md),
so the samples are kept separate. The first-audio target is reply-dependent.

## Provenance and limits

The first three runs precede the green listening-LED update, and the fourth
follows it. Their boot ELF hash prefixes match the retained pre-LED and LED
image manifests. The benchmark does not receive `--firmware`, so these are
archive matches rather than benchmark-recorded full image hashes.

The [sanitized data](results.json) retain all four device timestamp sets, tool
revisions/hashes, source-results hashes, matched image provenance and summary
statistics. Raw serial logs and human transcripts remain outside Git. No
additional device runs are made to produce this report.

Recording ends at a fixed five-second cap, not detected speech end. The final
RX-read and first I2S markers are software endpoints. LLM latency, acoustic
latency, automatic endpointing and broader accuracy remain unmeasured.
