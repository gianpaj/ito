# Agent Note: Oido references and allocation failures

Status: implemented — Pinned host references and allocation-failure checks pass.

## Problem

Recognizer correctness and memory reuse need fixed inputs. Microphone speech
varies between trials, and a permissive upstream parser assumes a trusted model
and successful allocation at several initialization sites.

## Decision

The host tests compile the pinned upstream C engine and verify the exact v2b
model hash. Greedy streaming uses chunk 8 and left context 64, with no language
model or weight relocation. Two zeroed, aligned, bounded monotonic arenas model
the Ito lease. Full overwrites between runs expose retained pointers. The
StackChan dependency patch checks every required model/stream allocation; tests
inject each of the 59 failures and verify earlier allocations are released.

Three original public WAVs provide exact host transcript references. Twenty
public clips add noise and varied speech for device comparison. The fixture
preparer decodes pinned MP3 files to mono PCM16 at 16 kHz and records both source
and decoded hashes. Clips longer than ten seconds are excluded without trimming.
Audio/model files remain outside Git. Sanitized manifests retain source URLs,
reference text, host output, hashes, duration and WER calculation.

## Alternatives considered

Microphone-only trials cannot distinguish model variation from input variation.
Comparing with upstream beam/LM transcripts would test a different decoder.
Treating total free memory as an arena-fit result would miss kind-specific
capacity and alignment. Host scalar output remains a reference rather than a
claim of bit identity across target math libraries.

## Consequences

The host ABI uses 64-bit pointers, so its 211,488-byte hot and 1,309,440-byte
PSRAM peaks do not replace native measurements. The twenty-clip host WER is
63/321 words, 19.63%, on a mixed adverse-condition set. It is not a clean-speech
accuracy figure. Three original clips pass repeated full-arena overwrites.
The [manifests](../../../../results/stackchan/2026-11-15-local-stt-ito/oido-public-fixtures.json)
and tests preserve failures as well as successful examples. Target capture,
stack/DMA budgets and physical audio remain device acceptance checks.
