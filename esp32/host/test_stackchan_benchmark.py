#!/usr/bin/env python3
"""Test timing boundaries and the actual benchmark protocol without hardware."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stackchan_benchmark as bench

MIC = 'I (20000) microphone: samples=80000 peak=7340 clipped=0 elapsed_ms=5007 cleanup=1'
CAPTURE = 'CAPTURE turn=3 samples=80000 duration_ms=5000 capped=1'
STT = 'STT turn=3 hot=204720 psram=1309152 allocations=59 frames=63 setup_ms=722.7 feed_ms=3758.2 finish_ms=442.5'
TTS = 'TIMING text: 20 tokens, style 0, 1.27 s audio | first chunk 576.7 ms (begin 2.3 ms) | compute 1397.3 ms, RTF 1.096 | underruns 0 (start delay planned 826 ms)'
I2S = 'I2S_START: engine begin -> first PCM submission 825.0 ms, text received -> first PCM submission 833.5 ms (successful I2S API call; DMA and acoustic latency excluded)'
PCM = 'TEXT_E2E: text arrived -> first audio chunk ready 585.2 ms (front end + queue 8.4 ms, engine 576.7 ms)'
PRIVATE = 'personal speech must not be in numeric results'


def complete(trial):
    for ms, line in [
        (10728, 'OK text queued (17 bytes)'), (10729, 'READY'),
        (11561, 'I (26460) local_ito: speaker playing=1'),
        (12850, 'I (27750) local_ito: speaker playing=0'),
        (12851, TTS), (12852, I2S), (12853, PCM), (12854, 'READY'),
    ]:
        trial.observe(line, ms * 1000000)


class FakeSerial:
    def __init__(self):
        self.pending = bytearray()
        self.sent = []
        self.closed = False
    @property
    def in_waiting(self): return len(self.pending)
    def open(self): pass
    def close(self): self.closed = True
    def write(self, data):
        cmd = data.decode().strip()
        self.sent.append(cmd)
        if cmd == 'status':
            lines = ['CONVERSATION turn=0 state=idle', 'READY']
        elif cmd.startswith('listen '):
            lines = ['LISTENING turn=3 rate=16000 max_samples=80000; send finishes, cancel discards',
                     MIC, CAPTURE, STT, 'TURN 3 state=restoring internal_free=13994',
                     'TRANSCRIPT turn=3: ' + PRIVATE, 'CONVERSATION READY: reply']
        elif cmd.startswith('text '):
            lines = ['OK text queued (17 bytes)', 'READY', 'I (26460) local_ito: speaker playing=1',
                     'I (27750) local_ito: speaker playing=0', TTS, I2S, PCM, 'READY']
        elif cmd == 'cancel': lines = ['CANCELLED turn=3']
        else: raise AssertionError(cmd)
        self.pending.extend(('\n'.join(lines) + '\n').encode())
        return len(data)
    def read(self, count):
        out = self.pending[:min(count, 17)]
        del self.pending[:len(out)]
        return bytes(out)


class Tests(unittest.TestCase):
    def args(self, directory):
        return argparse.Namespace(port='fake', seconds=5, wav=None, runs=1, reply='A manual reply.',
                                  volume=None, firmware=None, log_root=Path(directory))

    def recording_trial(self):
        t = bench.Trial(1, 'microphone')
        t.sent('listen 5', 0)
        for ms, line in [(100, 'LISTENING turn=3 rate=16000 max_samples=80000'),
                         (5100, MIC), (5101, CAPTURE), (10025, STT),
                         (10725, 'TRANSCRIPT turn=3: ' + PRIVATE), (10726, 'CONVERSATION READY')]:
            t.observe(line, ms * 1000000)
        t.sent('text A manual reply.', 10727 * 1000000)
        return t

    def test_clock_boundaries_and_privacy(self):
        t = self.recording_trial()
        t.observe('OK text queued (17 bytes)', 10728 * 1000000)
        t.observe('READY', 10729 * 1000000)
        self.assertFalse(t.finished)
        complete(t)
        row = t.result()
        self.assertEqual(row['stt_total_ms'], 4923.4)
        self.assertEqual(row['tts_text_to_first_i2s_ms'], 833.5)
        self.assertEqual(row['reply_sent_to_playback_log_host_ms'], 834)
        self.assertEqual(row['capture_end_log_to_playback_log_device_ms'], 6460)
        self.assertEqual(row['stt_report_to_conversation_ready_host_ms'], 701)
        self.assertEqual(row['capture']['peak'], 7340)
        self.assertNotIn(PRIVATE, json.dumps(row))
        self.assertEqual(bench.summary([row])['tts_text_to_first_i2s_ms']['n'], 1)

    def test_wrong_turn_and_missing_metrics(self):
        t = self.recording_trial()
        with self.assertRaisesRegex(RuntimeError, 'Expected turn'):
            t.observe(STT.replace('turn=3', 'turn=4'), 11000 * 1000000)
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            t.result()
        t.observe('CONVERSATION READY', 11000 * 1000000)
        t.observe('OK text queued', 11001 * 1000000)
        t.observe(TTS, 11002 * 1000000)
        t.observe('READY', 11003 * 1000000)
        self.assertFalse(t.finished)

    def test_wav_has_no_capture_timing(self):
        t = bench.Trial(1, 'wav_upload')
        t.sent('pcm begin 80000', 0)
        t.observe('OK pcm begin turn=3 samples=80000', 1)
        t.sent('send', 100 * 1000000)
        t.observe(STT, 10025 * 1000000)
        t.observe('TRANSCRIPT turn=3: ' + PRIVATE, 10725 * 1000000)
        t.observe('CONVERSATION READY', 10726 * 1000000)
        t.sent('text A manual reply.', 10727 * 1000000)
        complete(t)
        row = t.result()
        self.assertIsNone(row['capture_end_log_to_playback_log_device_ms'])
        self.assertEqual(row['upload_host_ms'], 100)
        self.assertEqual(row['pcm_submit_to_transcript_host_ms'], 10625)

    def test_multiple_reply_utterances_preserve_first_audio_timing(self):
        t = self.recording_trial()
        complete(t)
        t.finished = False
        t.observe(TTS.replace("TIMING text:", "TIMING say:").replace("underruns 0", "underruns 1"), 13000 * 1000000)
        t.observe("I2S_START: engine begin -> first PCM submission 900.0 ms", 13001 * 1000000)
        t.observe("I (29000) local_ito: speaker playing=0", 13002 * 1000000)
        t.observe("READY", 13003 * 1000000)
        row = t.result()
        self.assertEqual(row["tts_text_to_first_i2s_ms"], 833.5)
        self.assertEqual(row["tts_utterances"], 2)
        self.assertEqual(row["tts_underruns"], 1)

    def test_validation_before_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            for field, value in [('runs', 0), ('seconds', 0), ('seconds', 11), ('volume', 101),
                                 ('reply', ''), ('reply', 'hello\nreboot'), ('reply', 'a' * 4091), ('reply', 'café')]:
                args = self.args(directory)
                setattr(args, field, value)
                with self.assertRaises(ValueError): bench.validate(args)

    def test_actual_one_trial_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            port = FakeSerial()
            with patch.object(bench.serial, 'Serial', return_value=port), redirect_stdout(io.StringIO()):
                self.assertEqual(bench.benchmark(self.args(directory)), 0)
            session = next(Path(directory).iterdir())
            data = json.loads((session / 'results.json').read_text())
            self.assertEqual(data['completed_runs'], 1)
            self.assertEqual(data['exit_reason'], 'complete')
            self.assertFalse(data['responder']['llm_called'])
            self.assertEqual(sum(cmd.startswith('listen ') for cmd in port.sent), 1)
            self.assertEqual(sum(cmd.startswith('text ') for cmd in port.sent), 1)
            self.assertEqual(data['trials'][0]['tts_text_to_first_i2s_ms'], 833.5)
            self.assertNotIn(PRIVATE, (session / 'results.json').read_text())
            self.assertIn(PRIVATE, (session / 'serial.log').read_text())
            self.assertTrue((session / 'trials.csv').is_file())
            self.assertTrue(port.closed)


if __name__ == '__main__': unittest.main()
