"""Entry point: python -m voip_overlay [options]"""
from __future__ import annotations

import argparse
import queue
import signal
import sys
import threading
import time

from .audio import FileSource, LoopbackCapture, Segmenter, SAMPLE_RATE, list_output_devices


def parse_args():
    p = argparse.ArgumentParser(description="Live translated VOIP captions overlay")
    a = p.add_argument
    a("--list-devices", action="store_true", help="list output devices and exit")
    a("--audio-device", help="substring of the output device to listen to (default: system default)")
    a("--file", help="feed a wav/flac file instead of live audio (testing)")
    a("--model", default="small", help="whisper model: tiny/base/small/medium/large-v3 (default small)")
    a("--compute-device", default="cpu",
      help="cpu (default; leaves the GPU to the game) or cuda (NVIDIA only)")
    a("--compute-type", default="auto", help="auto picks int8 on CPU, float16 on GPU")
    a("--cpu-threads", type=int, default=4,
      help="CPU threads Whisper may use (default 4; lower = less impact on the game)")
    a("--task", default="translate", choices=["translate", "transcribe"],
      help="translate -> English, transcribe -> original language")
    a("--language", help="force source language code (e.g. ru) instead of auto-detect")
    a("--only-lang", help="comma-separated language codes to show, e.g. 'es'; everything else "
                          "(English teammates, noise) is ignored")
    a("--lang-prob", type=float, default=0.5,
      help="min language-detection confidence for --only-lang (default 0.5)")
    a("--names",help="comma-separated names assigned to speakers in order of first appearance")
    a("--threshold", type=float, default=0.45,
      help="speaker similarity threshold; higher = splits voices more readily (default 0.45)")
    a("--no-speakers", action="store_true", help="disable speaker identification")
    a("--lines", type=int, default=4, help="max caption lines on screen")
    a("--ttl", type=float, default=8.0, help="seconds a line stays visible")
    a("--font-size", type=int, default=18)
    a("--width", type=float, default=0.6, help="overlay width as a fraction of the screen")
    a("--position", choices=["top", "bottom"], default="top")
    a("--panel", action="store_true",
      help="show a normal scrolling transcript window instead of the overlay (for a 2nd monitor)")
    a("--screen", type=int, help="monitor number to use (listed at startup; default primary)")
    a("--log", help="append the transcript to this file")
    a("--prefetch", action="store_true", help="download/load the models, then exit (used by setup)")
    a("--headless",action="store_true", help="no overlay window, print to console only")
    return p.parse_args()


def main():
    args = parse_args()
    if args.list_devices:
        for name in list_output_devices():
            print(name)
        return

    print("[init] loading models (first run downloads them)...")
    from .transcriber import Transcriber
    only = [c.strip() for c in args.only_lang.split(",")] if args.only_lang else None
    stt = Transcriber(args.model, args.compute_device, args.compute_type, args.task,
                      args.language, only, args.lang_prob, args.cpu_threads)
    tracker = None
    if not args.no_speakers:
        from .speakers import SpeakerTracker
        names = [n.strip() for n in args.names.split(",")] if args.names else None
        tracker = SpeakerTracker(threshold=args.threshold, names=names)
    print("[init] ready")
    if args.prefetch:
        print("[init] models downloaded and working")
        return

    audio_q: queue.Queue = queue.Queue()
    seg_q: queue.Queue = queue.Queue()
    source = (FileSource(audio_q, args.file) if args.file
              else LoopbackCapture(audio_q, args.audio_device))

    emit = None  # set below once the UI (if any) exists
    log = open(args.log, "a", encoding="utf-8") if args.log else None

    def segment_loop():
        seg = Segmenter()
        while True:
            for utt in seg.feed(audio_q.get()):
                seg_q.put(utt)

    def process_loop():
        while True:
            utt = seg_q.get()
            if seg_q.qsize() > 4:  # fell behind: drop stale audio rather than lag forever
                continue
            t0 = time.perf_counter()
            text, lang = stt(utt)
            if not text:
                continue
            spk = tracker.identify(utt) if tracker else None
            idx, name = (spk.idx, spk.name) if spk else (0, "Voice")
            dt = time.perf_counter() - t0
            line = f"{name} [{lang}] {text}"
            print(f"{line}   ({len(utt) / SAMPLE_RATE:.1f}s audio, {dt:.2f}s)")
            if log:
                log.write(time.strftime("%H:%M:%S ") + line + "\n")
                log.flush()
            if emit:
                emit(idx, name, lang, text)

    target = "en" if args.task == "translate" else ""

    if args.headless:
        source.start()
        threading.Thread(target=segment_loop, daemon=True).start()
        if args.file:
            threading.Thread(target=process_loop, daemon=True).start()
            source.join()
            while not seg_q.empty() or not audio_q.empty():
                time.sleep(0.2)
            time.sleep(3)
        else:
            process_loop()
        return

    from PyQt6.QtWidgets import QApplication
    from .ui import Bridge, Overlay, Panel
    app = QApplication(sys.argv)
    if args.panel:
        overlay = Panel(args.font_size, target, args.screen)
    else:
        overlay = Overlay(args.lines, args.ttl, args.font_size, args.width, args.position,
                          target, args.screen)
    bridge = Bridge()
    bridge.line.connect(overlay.add_line)
    emit = bridge.line.emit

    signal.signal(signal.SIGINT, lambda *_: app.quit())  # Ctrl+C in console quits
    source.start()
    threading.Thread(target=segment_loop, daemon=True).start()
    threading.Thread(target=process_loop, daemon=True).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
