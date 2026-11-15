# Agent Note: Manual speech-turn latency

Status: implemented — Host timing tests and one native five-second benchmark pass.

## Problem

Separate STT and TTS timing lines do not describe the complete manual turn.
Manual typing adds arbitrary delay. A timing summary printed after playback
cannot be timestamped as though it were the first audio event.

## Decision

A host benchmark runs one turn by default through the existing USB interface.
It sends a supplied reply immediately after the transcript and conversation
READY, preserving the manual responder boundary without invoking an LLM.
The firmware remains unchanged. Explicit runs can repeat the same case.

Firmware counters supply STT stages, first PCM readiness and text-to-first-I2S
time. A single host monotonic clock supplies observer intervals. Device log
capture-end/playback-start timestamps supply a separate device-clock interval.
Durations from different clocks are not combined into an exact total. Acoustic
onset and detected end of speech remain unmeasured. Canonical commands and metric
definitions are in [Benchmarking](../../../../esp32/BENCHMARKING.md#stackchan-manual-speech-latency).

## Alternatives considered

Timing manual console entry includes human delay and cannot isolate the model
pipeline. Treating arrival of the delayed I2S summary as first audio overstates
latency. Adding new firmware markers would require a build/flash cycle when the
existing stage counters and playback callback already support this benchmark.
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
retains the tool/image hashes and exact measurement boundaries. No firmware
change or additional repeated device pass is needed for this slice.
