#!/usr/bin/env python3
"""Measure the local speech turn with a supplied reply and existing firmware logs."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time

import serial

from stackchan import ROOT, TranscriptionSerial, file_info, git_output, load_pcm16_wav, utc_now

DEFAULT_REPLY = "This is a manual reply from StackChan."


def interval(events, first, last):
    if first not in events or last not in events:
        return None
    value = (events[last] - events[first]) / 1_000_000
    if value < 0:
        raise RuntimeError(f"Invalid event order: {first}, {last}")
    return round(value, 3)


class Trial:
    def __init__(self, number, mode):
        self.number, self.mode = number, mode
        self.events, self.device_ms, self.device_us = {}, {}, {}
        self.turn = None
        self.stt, self.tts, self.capture = {}, {}, {}
        self.transcript_kind = None
        self.finished = False

    def sent(self, command, now):
        if command.startswith(("listen ", "pcm begin ")):
            self.events["input_command"] = now
        elif command == "send":
            self.events["pcm_submit"] = now
        elif command.startswith("text "):
            self.events["reply_sent"] = now

    def check_turn(self, value):
        value = int(value)
        if self.turn is not None and self.turn != value:
            raise RuntimeError(f"Expected turn {self.turn}, received turn {value}")
        self.turn = value

    def observe(self, line, now):
        device = re.search(r"\bI \(\s*(\d+)\)", line)
        if re.match(r"(?:LISTENING|OK pcm begin) turn=", line):
            self.check_turn(re.search(r"turn=(\d+)", line)[1])
            if line.startswith("LISTENING"):
                self.events["listening"] = now
        match = re.fullmatch(r"CAPTURE turn=(\d+) samples=(\d+) duration_ms=(\d+) capped=([01])", line)
        if match:
            self.check_turn(match[1])
            self.capture.update(zip(("samples", "audio_ms", "capped"), map(int, match.groups()[1:])))
            self.events["capture_report"] = now
        if device and "microphone: samples=" in line:
            self.device_ms["capture_end_log"] = int(device[1])
            for key, value in re.findall(r"(samples|peak|clipped|elapsed_ms|cleanup)=(\d+)", line):
                self.capture[key] = int(value)
        if line.startswith("STT turn="):
            fields = dict(re.findall(r"(\w+)=([\d.]+)", line))
            self.check_turn(fields["turn"])
            try:
                self.stt = {key: float(fields[key]) for key in ("setup_ms", "feed_ms", "finish_ms")}
            except (KeyError, ValueError) as error:
                raise RuntimeError("Unsupported STT timing format") from error
            self.events["stt_report"] = now
        match = re.match(r"TURN (\d+) state=restoring ", line)
        if match:
            self.check_turn(match[1])
        if line.startswith("TURN_TIMING "):
            fields = dict(re.findall(r"(\w+)=(\d+)", line))
            self.check_turn(fields.pop("turn"))
            self.device_us.update({key: int(value) for key, value in fields.items() if key.endswith("_us")})
            self.capture["backlog_samples"] = int(fields["backlog_samples"])
        match = re.fullmatch(r"TRANSCRIPT turn=(\d+): (.*)", line)
        if match:
            self.check_turn(match[1])
            self.transcript_kind = "no_speech" if match[2] == "[no speech]" else "text"
            self.events["transcript"] = now
        if line.startswith("CONVERSATION READY"):
            if "transcript" not in self.events:
                raise RuntimeError("Conversation returned without a transcript")
            self.events["conversation_ready"] = now
        if line.startswith("OK text queued") and "reply_sent" in self.events:
            self.events["reply_accepted"] = now
        if "reply_accepted" in self.events:
            if "speaker playing=1" in line and "playback_start_log" not in self.events:
                self.events["playback_start_log"] = now
                if device:
                    self.device_ms["playback_start_log"] = int(device[1])
            elif "speaker playing=0" in line and "playback_start_log" in self.events:
                self.events["playback_end_log"] = now
            if line.startswith(("TIMING text:", "TIMING say:")):
                match = re.search(r"([\d.]+) s audio .*?compute ([\d.]+) ms, RTF ([\d.]+) \| underruns (\d+)", line)
                if not match:
                    raise RuntimeError("Unsupported TTS timing format")
                if "first_utterance_audio_seconds" not in self.tts:
                    self.tts.update(first_utterance_audio_seconds=float(match[1]),
                                    first_utterance_compute_ms=float(match[2]),
                                    first_utterance_compute_rtf=float(match[3]))
                self.tts["utterances"] = self.tts.get("utterances", 0) + 1
                self.tts["underruns"] = self.tts.get("underruns", 0) + int(match[4])
            if line.startswith("I2S_START:"):
                stamp = re.search(r"submit_us=(\d+)", line)
                if stamp:
                    self.device_us.setdefault("first_i2s_us", int(stamp[1]))
                match = re.search(r"text received -> first PCM submission ([\d.]+) ms", line)
                if match:
                    self.tts.setdefault("text_to_first_i2s_ms", float(match[1]))
                elif "text_to_first_i2s_ms" not in self.tts:
                    raise RuntimeError("Firmware did not report text-to-first-I2S timing")
            if line.startswith("TEXT_E2E:"):
                match = re.search(r"text arrived -> first audio chunk ready ([\d.]+) ms", line)
                if match:
                    self.tts.setdefault("text_to_pcm_ready_ms", float(match[1]))
            if line == "READY" or line.startswith("READY "):
                # Boot/status READY lines can be queued ahead of this speech job.
                required = ("first_utterance_audio_seconds", "text_to_first_i2s_ms", "text_to_pcm_ready_ms")
                if all(key in self.tts for key in required) and "playback_end_log" in self.events:
                    self.events["speech_ready"] = now
                    self.finished = True

    def result(self):
        if not self.finished or not self.stt or "conversation_ready" not in self.events:
            raise RuntimeError("Incomplete benchmark trial")
        if self.mode == "microphone" and ("audio_ms" not in self.capture or "capture_end_log" not in self.device_ms):
            raise RuntimeError("Firmware did not report microphone capture timing")
        device_gap = None
        if "capture_end_log" in self.device_ms and "playback_start_log" in self.device_ms:
            device_gap = self.device_ms["playback_start_log"] - self.device_ms["capture_end_log"]
            if device_gap < 0:
                raise RuntimeError("Device clock reset during the trial")
        def device_interval(first, last):
            if not self.device_us.get(first) or not self.device_us.get(last):
                return None
            value = self.device_us[last] - self.device_us[first]
            if value < 0:
                raise RuntimeError(f"Invalid device timestamp order: {first}, {last}")
            return round(value / 1000, 3)
        return {
            "events_device_monotonic_us": self.device_us.copy(),
            "last_input_read_to_first_i2s_device_ms": device_interval("last_input_us", "first_i2s_us"),
            "last_input_read_to_final_transcript_device_ms": device_interval("last_input_us", "final_transcript_us"),
            "last_input_read_to_drained_device_ms": device_interval("last_input_us", "input_drained_us"),
            "final_transcript_to_resume_device_ms": device_interval("final_transcript_us", "resume_done_us"),
            "final_transcript_to_first_i2s_device_ms": device_interval("final_transcript_us", "first_i2s_us"),
            "trial": self.number, "mode": self.mode, "turn": self.turn,
            "transcript_kind": self.transcript_kind, "capture": self.capture,
            "events_host_monotonic_ns": self.events.copy(), "events_device_log_ms": self.device_ms.copy(),
            "stt_setup_ms": self.stt["setup_ms"], "stt_feed_ms": self.stt["feed_ms"],
            "stt_finish_ms": self.stt["finish_ms"], "stt_total_ms": round(sum(self.stt.values()), 3),
            "stt_report_to_conversation_ready_host_ms": interval(self.events, "stt_report", "conversation_ready"),
            "capture_report_to_transcript_host_ms": interval(self.events, "capture_report", "transcript"),
            "pcm_submit_to_transcript_host_ms": interval(self.events, "pcm_submit", "transcript"),
            "upload_host_ms": interval(self.events, "input_command", "pcm_submit"),
            "transcript_to_reply_sent_host_ms": interval(self.events, "transcript", "reply_sent"),
            "reply_sent_to_playback_log_host_ms": interval(self.events, "reply_sent", "playback_start_log"),
            "capture_report_to_playback_log_host_ms": interval(self.events, "capture_report", "playback_start_log"),
            "capture_end_log_to_playback_log_device_ms": device_gap,
            "pcm_submit_to_playback_log_host_ms": interval(self.events, "pcm_submit", "playback_start_log"),
            "input_command_to_playback_log_host_ms": interval(self.events, "input_command", "playback_start_log"),
            "reply_sent_to_speech_ready_host_ms": interval(self.events, "reply_sent", "speech_ready"),
            **{f"tts_{key}": value for key, value in self.tts.items()},
        }


class BenchmarkSerial(TranscriptionSerial):
    trial = None

    def send(self, command):
        if self.trial:
            self.trial.sent(command, time.monotonic_ns())
        super().send(command)

    def line(self, deadline):
        line = super().line(deadline)
        if re.search(r"Guru Meditation|Stack canary|abort\(\)|Task watchdog got triggered", line):
            raise RuntimeError(line)
        if self.trial:
            self.trial.observe(line, time.monotonic_ns())
        return line


def validate(args):
    if args.runs < 1:
        raise ValueError("runs must be greater than zero")
    if args.seconds is not None and not 1 <= args.seconds <= 10:
        raise ValueError("seconds must be 1..10")
    if not args.reply.strip() or any(char in args.reply for char in "\r\n\x00"):
        raise ValueError("reply must be nonempty text on one line")
    try:
        encoded = args.reply.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("This benchmark requires an ASCII English reply") from error
    if len(encoded) > 4090:
        raise ValueError("reply exceeds the USB command limit")
    if args.volume is not None and not 0 <= args.volume <= 100:
        raise ValueError("volume must be 0..100")
    if getattr(args, "first_frames", None) is not None and not 1 <= args.first_frames <= 32:
        raise ValueError("first-frames must be 1..32")
    return load_pcm16_wav(args.wav.expanduser()) if args.wav else None


def summary(rows):
    result = {}
    for key in rows[0] if rows else ():
        if key.endswith("_ms"):
            values = [row[key] for row in rows if isinstance(row[key], (int, float))]
            if values:
                result[key] = {"n": len(values), "min": min(values),
                               "median": round(statistics.median(values), 3), "max": max(values)}
    return result


def benchmark(args):
    pcm = validate(args)
    seconds = args.seconds if args.seconds is not None else 5
    session = args.log_root.expanduser().resolve() / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session.mkdir(parents=True, mode=0o700)
    reply = args.reply.encode("ascii")
    results = {
        "schema_version": 2, "started_utc": utc_now(), "requested_runs": args.runs,
        "responder": {"mode": "fixed_supplied_text", "llm_called": False,
                      "reply_bytes": len(reply), "reply_sha256": hashlib.sha256(reply).hexdigest()},
        "input": {"mode": "wav_upload" if pcm is not None else "microphone", "capture_seconds": seconds if pcm is None else None,
                  "wav": file_info(args.wav)}, "firmware": file_info(args.firmware),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_revision": git_output("rev-parse", "HEAD").decode().strip(),
        "source_dirty": bool(git_output("status", "--porcelain")), "port": args.port, "volume_requested": args.volume,
        "first_frames_requested": getattr(args, "first_frames", None),
        "python_version": sys.version, "pyserial_version": serial.__version__,
        "trials": [], "limits": [
            "No LLM is timed; supplied reply is sent automatically after conversation READY.",
            "Firmware text-to-first-I2S timing excludes DMA and acoustic latency.",
            "Playback logs mark the callback after the first successful I2S write, not acoustic onset.",
            "Host intervals include USB/log delivery and scheduling; device log intervals have millisecond log resolution.",
            "Last input timestamp marks completion of the final RX read, not measured acoustic end of speech.",
            "Streaming STT compute overlaps capture; summed STT stages are not post-capture latency.",
            "Capture ends at the configured cap, not detected end of speech. Boot time is excluded from trials.",
            "TTS compute/audio fields describe the first utterance; underruns sum all reply utterances.",
            "Private serial/command logs can contain speech and reply text; metric rows omit transcript text.",
        ],
    }
    def save():
        results["completed_runs"] = len(results["trials"])
        results["summary_ms"] = summary(results["trials"])
        (session / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        rows = results["trials"]
        if rows:
            columns = [key for key in rows[0] if not isinstance(rows[0][key], dict)]
            with (session / "trials.csv").open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
                writer.writerows({key: row[key] for key in columns} for row in rows)
    print(f"Private benchmark logs: {session}", flush=True)
    connection = serial.Serial(baudrate=115200, timeout=0.1, write_timeout=2, exclusive=True)
    connection.dtr = connection.rts = False
    connection.port = args.port
    channel = None
    save()
    try:
        with (session / "serial.log").open("w") as log, (session / "commands.log").open("w") as commands:
            connection.open()
            channel = BenchmarkSerial(connection, log, commands)
            channel.ready()
            if args.volume is not None:
                channel.send(f"volume {args.volume}")
                channel.wait(lambda line: line == f"OK volume {args.volume}", 2)
            if getattr(args, "first_frames", None) is not None:
                channel.send(f"first {args.first_frames}")
                channel.wait(lambda line: line.startswith(f"OK first chunk {args.first_frames} frames"), 5)
            for number in range(1, args.runs + 1):
                trial = channel.trial = Trial(number, results["input"]["mode"])
                if pcm is None:
                    print(f"Trial {number}: recording {seconds} seconds, then a supplied reply", flush=True)
                    channel.send(f"listen {seconds}")
                    channel.wait(lambda line: line.startswith("CONVERSATION READY"), seconds + 120)
                    if trial.capture.get("samples") != seconds * 16000:
                        raise RuntimeError("Microphone sample count does not match the requested duration")
                else:
                    channel.transcribe(pcm)
                channel.send("text " + args.reply)
                deadline = time.monotonic() + 120
                while not trial.finished:
                    channel.line(deadline)
                row = trial.result()
                results["trials"].append(row)
                save()
                gap = row["capture_end_log_to_playback_log_device_ms"]
                if row["last_input_read_to_first_i2s_device_ms"] is not None:
                    print(f"Trial {number}: last RX read -> first I2S {row['last_input_read_to_first_i2s_device_ms']:.1f} ms; "
                          f"STT tail {row['last_input_read_to_final_transcript_device_ms']:.1f} ms; "
                          f"restore {row['final_transcript_to_resume_device_ms']:.1f} ms", flush=True)
                print(f"Trial {number}: STT {row['stt_total_ms']:.1f} ms; "
                      f"Ito restore/control {row['stt_report_to_conversation_ready_host_ms']:.1f} ms observed; "
                      f"text -> first I2S {row['tts_text_to_first_i2s_ms']:.1f} ms; "
                      f"capture-end -> playback log {gap if gap is not None else 'n/a'} ms; "
                      f"underruns {row['tts_underruns']}", flush=True)
                channel.trial = None
            results["exit_reason"] = "complete"
    except BaseException as error:
        results["exit_reason"] = "interrupt" if isinstance(error, KeyboardInterrupt) else "error"
        results["error"] = str(error)
        if channel is not None:
            try:
                channel.send("cancel")
            except (OSError, ValueError):
                pass
        raise
    finally:
        connection.close()
        results["ended_utc"] = utc_now()
        save()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--seconds", type=int, help="Microphone recording length, 1..10; default 5")
    source.add_argument("--wav", type=Path, help="Use a fixed mono PCM16 16 kHz WAV instead of capture")
    parser.add_argument("--runs", type=int, default=1, help="Default one turn; more runs are explicit")
    parser.add_argument("--reply", default=DEFAULT_REPLY, help="Supplied English reply replacing the manual LLM step")
    parser.add_argument("--first-frames", type=int, help="Probe the first TTS chunk, 1..32; 32 disables the startup ramp")
    parser.add_argument("--volume", type=int)
    parser.add_argument("--firmware", type=Path)
    parser.add_argument("--log-root", type=Path, default=ROOT / "esp32/logs/stackchan-benchmark")
    args = parser.parse_args()
    try:
        return benchmark(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
