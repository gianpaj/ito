# Agent Note: Fixed audio over the USB console

Status: implemented — WAV validation and acknowledged upload tests pass.

## Problem

Microphone speech is difficult to reproduce when testing a recognizer and shared
speech memory. The existing USB monitor carries text commands and private logs.

## Decision

`esp32/tools/stackchan.py transcribe` validates mono PCM16 WAV at 16 kHz, with
1..160000 samples, before opening the serial port. It sends little-endian PCM
as hex in 256-sample commands, checking each cumulative acknowledgement before
sending more. Turn IDs bind the final transcript to the upload. Optional
`--echo` requests Ito speech after recognition restores the speech runtime.

Session logs, uploaded PCM commands, transcripts and image/audio/model hashes
stay in a private session directory. They are not suitable for committing when
using personal audio. One process owns the serial port. A failure or interrupt
requests cancellation and closes the port. Device processing remains on-board.

## Alternatives considered

Raw unframed binary would conflict with the existing console parser. Sending
an entire recording at once can overflow native USB buffering. Acknowledged
hex chunks use the existing bounded parser with a small, testable protocol.
Real microphone tests remain required but cannot replace fixed input for
host/device recognition comparisons.

## Consequences

Hex doubles transfer bytes and adds USB round trips. Upload time is separate
from recognition timing. Tests exercise byte-exact chunk reconstruction,
fragmented UTF-8 output, wrong acknowledgements/turns, device errors, deadlines
and invalid/truncated/overlong WAV files. A successful host test does not prove
firmware recognition or microphone quality.
