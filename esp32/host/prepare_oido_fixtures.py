#!/usr/bin/env python3
"""Decode pinned public Oido samples and save greedy host references without hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import wave

PIN = "c8d60325ba8bffd4bad65a9ac63c713ee64d1aae"
MODEL_SHA = "9e8b40913f532fb44b716a1f882f38b3b21e220713e417899aba32ace8c35066"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wer(reference, hypothesis):
    ref = re.findall(r"[a-z0-9']+", reference.lower())
    hyp = re.findall(r"[a-z0-9']+", hypothesis.lower())
    row = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, 1):
        current = [i]
        for j, other in enumerate(hyp, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (word != other)))
        row = current
    return row[-1], len(ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--archive", type=Path, required=True, help="Private output directory for decoded WAV files")
    parser.add_argument("--output", type=Path, required=True, help="Sanitized metadata JSON")
    args = parser.parse_args()
    root = args.source.resolve()
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    assert revision == PIN
    model = root / "models/oido_v2b.tnm"
    assert sha(model) == MODEL_SHA
    records = json.loads((root / "docs/samples/results.json").read_text())
    selected = sorted((record for record in records if record["dur"] <= 10), key=lambda record: (record["group"] != "real", record["mp3"]))
    skipped = [record["mp3"] for record in records if record["dur"] > 10]
    clips = json.loads((root / "esp32/bench/clips_det.json").read_text())
    entries = []
    for record in selected:
        entries.append({"source": "docs/" + record["mp3"], "group": record["group"],
                        "corpus_id": record["sent"], "condition": record["cond"], "label": record["label"], "reference": record["ref"]})
    for name in ("b05", "b14", "b16"):
        clip = next(clip for clip in clips if clip["path"].endswith("/" + name + ".wav"))
        entries.append({"source": f"docs/demo/examples/{name}.wav", "group": "demo", "corpus_id": clip["id"],
                        "condition": "unmodified", "label": "Common Voice" if name == "b05" else "LibriSpeech", "reference": clip["ref"]})
    assert len(entries) == 20
    args.archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    for entry in entries:
        source = root / entry["source"]
        wav = args.archive / (source.stem + ".wav")
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                        "-map_metadata", "-1", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                        "-fflags", "+bitexact", "-flags:a", "+bitexact", str(wav)], check=True)
        wav.chmod(0o600)
        with wave.open(str(wav)) as audio:
            assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
            samples = audio.getnframes()
            assert 0 < samples <= 160000
            pcm = audio.readframes(samples)
        entry.update(file=wav.name, source_sha256=sha(source), wav_sha256=sha(wav), pcm_sha256=hashlib.sha256(pcm).hexdigest(),
                     samples=samples, sample_rate_hz=16000, seconds=samples / 16000,
                     source_url=f"https://github.com/lokutor-ai/oido/blob/{PIN}/{entry['source']}")
    component = root / "esp32/components/tinyasr"
    flags = ["-O2", "-std=c11", "-D_DEFAULT_SOURCE", "-ffp-contract=off"]
    with tempfile.TemporaryDirectory(prefix="oido-public-reference-") as temporary:
        executable = Path(temporary) / "tasr_cli"
        subprocess.run(["cc", *flags, f"-I{component}", f"-I{component / 'include'}", "-o", str(executable),
                        str(root / "esp32/host/tasr_cli.c"), *[str(component / source) for source in
                        ("tinyasr.c", "kernels.c", "tinyasr_lm.c", "tasr_nemo.c", "tasr_seg.c")], "-lm"], check=True)
        run = subprocess.run([str(executable), str(model), "--nstream", *[str(args.archive / entry["file"]) for entry in entries]],
                             capture_output=True, text=True, check=True)
    hypotheses = dict(line.split("\t", 1) for line in run.stdout.splitlines())
    errors = words = 0
    for entry in entries:
        hypothesis = hypotheses[str(args.archive / entry["file"])]
        edit_count, word_count = wer(entry["reference"], hypothesis)
        entry.update(host_greedy_transcript=hypothesis, host_word_errors=edit_count, reference_words=word_count,
                     host_wer=edit_count / word_count)
        errors += edit_count
        words += word_count
    report = {"schema_version": 1, "upstream_revision": revision, "model_sha256": MODEL_SHA,
              "mode": "greedy streaming, chunk 8 / left 64, no LM, flash-backed model, no acoustic weight copies",
              "host_build_flags": flags, "source_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "-C", str(root), "diff", "HEAD"])).hexdigest(),
              "ffmpeg_version": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
              "wer_normalization": "lowercase [a-z0-9']+ words, Levenshtein edits divided by reference words",
              "scope": "Host scalar reference from MP3-decoded or original public audio; not board recognition or microphone validation",
              "selection": "All 7 real recordings and 10 <=10s room variants, plus 3 public demo WAVs; longer recordings skipped without trimming",
              "skipped_over_10s_sources": skipped, "clips": entries, "host_total_word_errors": errors,
              "total_reference_words": words, "host_aggregate_wer": errors / words}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Prepared {len(entries)} public fixtures; host WER {errors}/{words} = {errors / words:.4f}")


if __name__ == "__main__":
    main()
