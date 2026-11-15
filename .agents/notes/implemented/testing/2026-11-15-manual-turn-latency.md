# Agent Note: Manual speech-turn latency

Status: implemented — Host timing tests and the native batch baseline and streaming timing parser pass.

## Problem

Separate STT and TTS timing lines do not describe the complete manual turn.
Manual typing adds arbitrary delay. A timing summary printed after playback
cannot be timestamped as though it were the first audio event.

## Decision

A host benchmark runs one turn by default through the existing USB interface.
It sends a supplied reply immediately after the transcript and conversation
READY, preserving the manual responder boundary without invoking an LLM.
Explicit runs can repeat the same case. Streaming firmware supplies device
monotonic timestamps for the final RX read, drained PCM, final transcript and
completed restoration. Ito reports the absolute first successful I2S submission
time after playback. These timestamps share one clock.

Firmware counters supply STT stages, first PCM readiness and text-to-first-I2S
time. A single host monotonic clock supplies observer intervals. Device log
capture-end/playback-start timestamps supply a separate device-clock interval.
Durations from different clocks are not combined into an exact total. Completion of the last RX read is a software input boundary. Acoustic
onset and detected end of speech remain unmeasured. Canonical commands and metric
definitions are in [Benchmarking](../../../../esp32/BENCHMARKING.md#stackchan-manual-speech-latency).

## Alternatives considered

Timing manual console entry includes human delay and cannot isolate the model
pipeline. Treating arrival of the delayed I2S summary as first audio overstates
latency. Existing stage counters and playback callbacks support the batch baseline.
Streaming overlaps computation with recording, so device microsecond markers
separate the remaining tail from work already performed during capture.
Acoustic loopback can measure a different endpoint but is outside this small slice.

## Consequences

Private sessions retain JSON, CSV, raw logs and input/image/tool hashes. Numeric
rows omit transcript text. A stopped or failed trial is not included as a complete
result. Boot is excluded, model setup and restoration remain visible, and no
LLM latency is invented. Protocol tests cover turn correlation, delayed summary
arrival, stale READY lines, multipart replies and missing metrics. Default runs
stay small; additional runs require an explicit argument.

One native five-second ambient-input trial measures STT at 4,982.2 ms, observed
restoration/control at 728.3 ms and supplied reply text to first I2S submission
at 1,073.1 ms. Device capture-end to playback-start logs span 6,790 ms, with zero
output underruns. This trial returns no speech and makes no accuracy claim.
The [result](../../../../results/stackchan/2026-11-15-manual-oido/latency-benchmark.json)
retains the tool/image hashes and exact measurement boundaries. The batch baseline is independent of later streaming measurements.

The [streaming results](../../../../results/stackchan/2026-11-15-streaming-latency/README.md)
record four ambient microphone probes and one completed public fixture turn.
The final image measures 1,648.1 ms from the last RX read to first I2S and
1,109.4 ms from final transcript to first I2S. It misses the strict 1,500 ms
input-end target by 148.1 ms. The 7.05-second supplied fixture reply has zero
underruns, as do the microphone replies. A failed upload before recognition is
recorded separately. TTS scheduling remains unchanged; startup is the remaining
measured bottleneck. These bounded checks do not establish a latency percentile.
