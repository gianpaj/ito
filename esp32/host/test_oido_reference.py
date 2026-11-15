#!/usr/bin/env python3
"""Validate pinned Oido greedy streaming references in two bounded, reusable arenas."""
import argparse
import ctypes as C
import hashlib
import json
import os
import sys
import subprocess
import tempfile
import wave
from pathlib import Path

PIN = "c8d60325ba8bffd4bad65a9ac63c713ee64d1aae"
MODEL_SHA = "9e8b40913f532fb44b716a1f882f38b3b21e220713e417899aba32ace8c35066"
FIXTURES = {
    "b05": ("66c6582b36f92d2e62e2103dccb999a55c01eb237c6e5aa60fa0ed3548233854",
            "this is best done in these spring when disturbed plants can recover"),
    "b14": ("d32a966cb9aeb13f4c33da901a05b4fb07cc76434e42246c3800f98766804851",
            "as for the isaurus has he returned to submarine cabn"),
    "b16": ("2b138df7e2bdf5c54c99c7a6b9878efffdd112eb3591ac4cb21c42950eb91ed8",
            "for ne was so absorbed in business that he had notred the whole baily question and left them in at a durkness"),
}
FLAGS = ["-O2", "-std=c11", "-D_DEFAULT_SOURCE", "-ffp-contract=off", "-shared", "-fPIC"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing pinned Oido checkout; no downloads are performed")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--patch", type=Path, help="Exact applied upstream safety patch; also inject each allocation failure")
    args = parser.parse_args()
    root = args.source.resolve()
    assert subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip() == PIN
    difference = subprocess.check_output(["git", "-C", str(root), "diff", "HEAD", "--", "esp32/components/tinyasr"])
    patch_sha = None
    if args.patch:
        patch_bytes = args.patch.read_bytes()
        assert difference == patch_bytes, "Source changes must exactly match the supplied safety patch"
        patch_sha = hashlib.sha256(patch_bytes).hexdigest()
    else:
        assert not difference, "Pass --patch for the applied upstream safety patch"
    component = root / "esp32/components/tinyasr"
    blob = (root / "models/oido_v2b.tnm").read_bytes()
    assert hashlib.sha256(blob).hexdigest() == MODEL_SHA
    reference_clips = json.loads((root / "esp32/bench/clips_det.json").read_text())
    with tempfile.TemporaryDirectory(prefix="oido-reference-") as temporary:
        library_path = Path(temporary) / "oido.dylib"
        sources = ["tinyasr.c", "kernels.c", "tinyasr_lm.c", "tasr_nemo.c", "tasr_seg.c"]
        subprocess.run(["cc", *FLAGS, f"-I{component}", f"-I{component / 'include'}", "-o", str(library_path),
                        *[str(component / source) for source in sources], "-lm"], check=True)
        library = C.CDLL(str(library_path))
        signatures = {
            "tasr_nemo_load": ([C.c_void_p, C.c_size_t], C.c_void_p),
            "tasr_nemo_stream_new": ([C.c_void_p, C.c_int, C.c_int, C.c_void_p], C.c_void_p),
            "tasr_nemo_stream_feed": ([C.c_void_p, C.c_void_p, C.c_int], C.c_int),
            "tasr_nemo_stream_finish": ([C.c_void_p, C.c_char_p, C.c_int], C.c_int),
            "tasr_nemo_stream_free": ([C.c_void_p], None), "tasr_nemo_free": ([C.c_void_p], None),
        }
        for name, (parameters, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = parameters, result
        capacities = [4891328, 239948]  # index 0 PSRAM, index 1 internal hot reservation
        storage = [C.create_string_buffer(size + 15) for size in capacities]
        bases = [(C.addressof(memory) + 15) & ~15 for memory in storage]
        offsets, high_water, live = [0, 0], [0, 0], {}
        fault = {"calls": 0, "fail_at": 0}
        callback_errors = []

        @C.CFUNCTYPE(C.c_void_p, C.c_size_t, C.c_int)
        def allocate(size, kind):
            fault["calls"] += 1
            if fault["calls"] == fault["fail_at"]:
                return None
            selected = kind
            offset = (offsets[selected] + 15) & ~15
            if offset + size > capacities[selected]:
                selected = 0
                offset = (offsets[0] + 15) & ~15
            # Upstream dereferences some allocations without NULL checks. A capacity
            # violation is a test failure, not a supported recoverable engine path.
            if offset + size > capacities[selected]:
                print("Borrowed workspace exhausted", file=sys.stderr, flush=True)
                os._exit(1)
            pointer = bases[selected] + offset
            offsets[selected] = offset + size
            high_water[selected] = max(high_water[selected], offsets[selected])
            live[pointer] = size
            C.memset(pointer, 0, size)
            return pointer

        @C.CFUNCTYPE(None, C.c_void_p)
        def release(pointer):
            if pointer:
                if pointer not in live:
                    callback_errors.append("Free outside live engine allocations")
                else:
                    del live[pointer]

        C.c_void_p.in_dll(library, "tasr_alloc").value = C.cast(allocate, C.c_void_p).value
        C.c_void_p.in_dll(library, "tasr_free").value = C.cast(release, C.c_void_p).value
        model_buffer = C.create_string_buffer(blob)
        records = []
        for fixture, (wav_hash, expected) in FIXTURES.items():
            wav_path = root / f"docs/demo/examples/{fixture}.wav"
            assert hashlib.sha256(wav_path.read_bytes()).hexdigest() == wav_hash
            with wave.open(str(wav_path)) as audio:
                assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
                samples = audio.getnframes()
                pcm = C.create_string_buffer(audio.readframes(samples))
            for cycle in range(3):
                assert not live
                for base, capacity in zip(bases, capacities):
                    C.memset(base, 0xA5, capacity)
                offsets[:] = [0, 0]
                fault["calls"] = 0
                model = library.tasr_nemo_load(model_buffer, len(blob))
                assert model
                stream = library.tasr_nemo_stream_new(model, 0, 0, None)
                assert stream
                for start in range(0, samples, 320):
                    library.tasr_nemo_stream_feed(stream, C.addressof(pcm) + start * 2, min(320, samples - start))
                text = C.create_string_buffer(4096)
                library.tasr_nemo_stream_finish(stream, text, len(text))
                transcript = text.value.decode()
                assert transcript == expected, (fixture, cycle, transcript)
                library.tasr_nemo_stream_free(stream)
                library.tasr_nemo_free(model)
                assert not live and not callback_errors
            metadata = next(clip for clip in reference_clips if clip["path"].endswith(f"/{fixture}.wav"))
            records.append({"fixture": fixture, "source_path": f"docs/demo/examples/{fixture}.wav", "sha256": wav_hash,
                            "samples": samples, "sample_rate_hz": 16000, "corpus_id": metadata["id"],
                            "reference": metadata["ref"], "greedy_streaming_host_transcript": expected,
                            "cycles": 3, "all_cycles_match": True})
        allocation_sites = fault["calls"]
        oom_cases = 0
        if args.patch:
            for fail_at in range(1, allocation_sites + 1):
                assert not live
                offsets[:] = [0, 0]
                fault.update(calls=0, fail_at=fail_at)
                model = library.tasr_nemo_load(model_buffer, len(blob))
                if model:
                    stream = library.tasr_nemo_stream_new(model, 0, 0, None)
                    assert not stream, ("Injected allocation failure was not rejected", fail_at)
                    library.tasr_nemo_free(model)
                assert not live and not callback_errors, ("Partial allocation leaked", fail_at)
                oom_cases += 1
        report = {"schema_version": 1, "upstream_revision": PIN, "model_sha256": MODEL_SHA, "safety_patch_sha256": patch_sha,
                  "allocation_failure_cases": oom_cases,
                  "engine": "Oido v2b, greedy, no LM, flash-backed model, no optional acoustic-weight relocation",
                  "flags": FLAGS, "host_pointer_bytes": C.sizeof(C.c_void_p),
                  "borrowed_psram_bytes": capacities[0], "borrowed_hot_bytes": capacities[1],
                  "bump_high_water_psram_bytes": high_water[0], "bump_high_water_hot_bytes": high_water[1],
                  "after_free_tracked_allocations": len(live), "feed_block_samples": 320,
                  "scope": "Host scalar C reference and bounded allocator fit; target PIE/libm/DMA/capture not tested",
                  "fixtures": records}
        output = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(output)
        else:
            print(output, end="")


if __name__ == "__main__":
    main()
