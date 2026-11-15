#!/usr/bin/env python3
"""Measure upstream Oido engine allocations without a board or model copies to RAM."""
import argparse
import ctypes as C
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

PIN = "c8d60325ba8bffd4bad65a9ac63c713ee64d1aae"
FLAGS = ["-O2", "-std=c11", "-D_DEFAULT_SOURCE", "-ffp-contract=off", "-shared", "-fPIC"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Existing Oido checkout at the recorded revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != PIN:
        parser.error(f"Expected upstream revision {PIN}")
    subprocess.run(["git", "-C", str(source), "diff", "--quiet", "HEAD", "--", "esp32/components/tinyasr"], check=True)
    component = source / "esp32/components/tinyasr"
    model_path = source / "models/oido_v2b.tnm"
    model = model_path.read_bytes()
    compiler = subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]
    with tempfile.TemporaryDirectory(prefix="oido-memory-probe-") as temp:
        library_path = Path(temp) / "libtinyasr.dylib"
        units = ["tinyasr.c", "kernels.c", "tinyasr_lm.c", "tasr_nemo.c", "tasr_seg.c"]
        subprocess.run(["cc", *FLAGS, f"-I{component / 'include'}", f"-I{component}",
                        "-o", str(library_path), *[str(component / unit) for unit in units], "-lm"], check=True)
        library = C.CDLL(str(library_path))
        libc = C.CDLL(None)
        libc.posix_memalign.argtypes = [C.POINTER(C.c_void_p), C.c_size_t, C.c_size_t]
        libc.posix_memalign.restype = C.c_int
        libc.free.argtypes = [C.c_void_p]
        active = {}
        state = {"peak_total_bytes": 0, "peak_by_kind_bytes": [0, 0]}

        def totals():
            return [sum(size for size, kind in active.values() if kind == index) for index in range(2)]

        @C.CFUNCTYPE(C.c_void_p, C.c_size_t, C.c_int)
        def allocate(size, kind):
            pointer = C.c_void_p()
            if libc.posix_memalign(C.byref(pointer), 16, max(size, 16)):
                return None
            C.memset(pointer, 0, size)
            active[pointer.value] = (size, kind)
            current = totals()
            state["peak_total_bytes"] = max(state["peak_total_bytes"], sum(current))
            state["peak_by_kind_bytes"] = [max(old, new) for old, new in zip(state["peak_by_kind_bytes"], current)]
            return pointer.value

        @C.CFUNCTYPE(None, C.c_void_p)
        def release(pointer):
            if pointer:
                del active[pointer]
                libc.free(pointer)

        C.c_void_p.in_dll(library, "tasr_alloc").value = C.cast(allocate, C.c_void_p).value
        C.c_void_p.in_dll(library, "tasr_free").value = C.cast(release, C.c_void_p).value
        signatures = {
            "tasr_nemo_load": ([C.c_void_p, C.c_size_t], C.c_void_p),
            "tasr_nemo_place_weights": ([C.c_void_p, C.c_size_t], C.c_size_t),
            "tasr_nemo_stream_new": ([C.c_void_p, C.c_int, C.c_int, C.c_void_p], C.c_void_p),
            "tasr_nemo_stream_feed": ([C.c_void_p, C.c_void_p, C.c_int], C.c_int),
            "tasr_nemo_stream_finish": ([C.c_void_p, C.c_char_p, C.c_int], C.c_int),
            "tasr_nemo_stream_free": ([C.c_void_p], None),
            "tasr_nemo_free": ([C.c_void_p], None),
        }
        for name, (parameters, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes, function.restype = parameters, result
        blob = C.create_string_buffer(model)
        recognizer = library.tasr_nemo_load(blob, len(model))
        assert recognizer
        loaded = totals()
        moved = library.tasr_nemo_place_weights(recognizer, 0)
        assert moved == 0
        stream = library.tasr_nemo_stream_new(recognizer, 0, 0, None)
        assert stream
        initialized = totals()
        pcm = (C.c_int16 * 160000)()
        library.tasr_nemo_stream_feed(stream, pcm, len(pcm))
        transcript = C.create_string_buffer(4096)
        library.tasr_nemo_stream_finish(stream, transcript, len(transcript))
        finished = totals()
        library.tasr_nemo_stream_free(stream)
        library.tasr_nemo_free(recognizer)
        assert not active
        report = {
            "schema_version": 1,
            "measurement": "host requested-allocation bytes; not ESP32 heap telemetry",
            "upstream_revision": revision,
            "model": {"file": model_path.name, "bytes": len(model), "sha256": hashlib.sha256(model).hexdigest()},
            "host": {"system": platform.system(), "machine": platform.machine(), "pointer_bytes": C.sizeof(C.c_void_p), "compiler": compiler},
            "build": {"flags": FLAGS, "translation_units": units, "esp_platform": False, "workers": "serial default"},
            "configuration": {"language_model": False, "acoustic_weight_copy_budget_bytes": 0, "acoustic_weights_copied_bytes": moved,
                              "chunk_frames": 8, "left_context_frames": 64, "input_sample_rate_hz": 16000, "input_seconds": 10, "input": "silence"},
            "kind_meanings": {"0": "PSRAM suitable", "1": "internal preferred, PSRAM fallback allowed by upstream firmware"},
            "model_live_by_kind_bytes": loaded,
            "stream_live_by_kind_bytes": initialized,
            "after_feed_finish_live_by_kind_bytes": finished,
            **state,
            "after_free_bytes": sum(totals()), "after_free_blocks": len(active),
            "capture_ring_10s_pcm16_bytes": 320000,
            "peak_plus_capture_ring_bytes": state["peak_total_bytes"] + 320000,
            "peak_plus_ring_and_separate_10s_utterance_bytes": state["peak_total_bytes"] + 640000,
            "exclusions": ["allocator headers and alignment padding", "ESP32 tasks, drivers, DMA and static BSS", "host model image standing in for flash mmap", "Python and host library runtime memory"],
        }
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
