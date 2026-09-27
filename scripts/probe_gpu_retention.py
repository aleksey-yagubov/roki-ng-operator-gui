#!/usr/bin/env python3
"""Bounded GPU sample retention probe; no robot, Qt, or pixel downloads."""

import argparse
from collections import deque
import json
import os
from pathlib import Path
import subprocess
import sys
import time


CASES = {
    "vpp-va": "vapostproc disable-passthrough=true ! video/x-raw(memory:VAMemory),format=NV12",
    "vpp-dmabuf": "vapostproc disable-passthrough=true ! video/x-raw(memory:DMABuf),format=DMA_DRM",
    "decode-va": "vah264dec ! video/x-raw(memory:VAMemory),format=NV12",
    "decode-dmabuf": "vah264dec ! video/x-raw(memory:DMABuf),format=DMA_DRM",
    "decode-vpp-va": "vah264dec ! vapostproc disable-passthrough=true ! video/x-raw(memory:VAMemory),format=NV12",
    "decode-gl-import": "vah264dec ! video/x-raw(memory:DMABuf),format=DMA_DRM ! glupload name=upload ! video/x-raw(memory:GLMemory)",
    "decode-gl-rgba": "vah264dec ! video/x-raw(memory:DMABuf),format=DMA_DRM ! glupload name=upload ! glcolorconvert ! video/x-raw(memory:GLMemory),format=RGBA,texture-target=2D",
}


def memory_snapshot():
    status = Path("/proc/self/status").read_text().splitlines()
    result = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
              for line in status if line.startswith(("VmRSS:", "RssAnon:"))}
    clients = {}
    for path in Path("/proc/self/fdinfo").iterdir():
        try:
            fields = dict(line.split(":", 1) for line in path.read_text().splitlines()
                          if ":" in line)
        except OSError:
            continue
        if "drm-client-id" in fields:
            key = fields.get("drm-pdev", "") + ":" + fields["drm-client-id"]
            clients[key.strip()] = {k: v.strip() for k, v in fields.items()
                                    if k.startswith("drm-")}
    result["drm_clients"] = clients
    return result


def probe(args):
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gst, GstVideo
    Gst.init(None)
    source = ("videotestsrc is-live=true pattern=ball ! "
              f"video/x-raw,format=NV12,width={args.width},height={args.height},framerate=60/1 ! ")
    if args.case.startswith("decode-"):
        source += "vah264enc b-frames=0 key-int-max=60 ! h264parse ! "
    pipeline_text = source + CASES[args.case] + (
        " ! tee name=t t. ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 "
        "leaky=downstream ! fakevideosink name=live sync=false signal-handoffs=true "
        "t. ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! "
        "appsink name=history sync=false max-buffers=2 enable-last-sample=false emit-signals=true"
    )
    result = {"case": args.case, "pipeline": pipeline_text, "gst": Gst.version_string(),
              "capacity": args.capacity, "errors": [], "warnings": [], "phases": []}
    pipeline = Gst.parse_launch(pipeline_text)
    sink = pipeline.get_by_name("history")

    def propose_allocation(_sink, query):
        # DMA-BUF consumers must accept layout/stride information, not assume packed pixels.
        query.add_allocation_meta(GstVideo.video_meta_api_get_type(), None)
        return True

    sink.connect("propose-allocation", propose_allocation)
    live_count = [0]

    def live_frame(*_):
        live_count[0] += 1

    pipeline.get_by_name("live").connect("handoff", live_frame)
    bus = pipeline.get_bus()
    history = deque(maxlen=args.capacity)
    first_sample = None
    first_pts = None
    last_arrival = None
    parent_type = Gst.parent_buffer_meta_api_get_type()
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            result["errors"].append("PLAYING failed")
        for phase, duration in (("warmup", 2.0), ("retain", args.seconds), ("released", 2.0)):
            if phase == "released":
                history.clear()
                first_sample = None
            start = time.monotonic()
            count = 0
            previous_live = live_count[0]
            max_gap = 0.0
            while time.monotonic() - start < duration:
                message = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
                if message:
                    if message.type == Gst.MessageType.ERROR:
                        error, debug = message.parse_error()
                        result["errors"].append(f"{error}: {debug}")
                        break
                    warning, debug = message.parse_warning()
                    result["warnings"].append(f"{warning}: {debug}")
                sample = sink.emit("try-pull-sample", 100 * Gst.MSECOND)
                now = time.monotonic()
                if sample is None:
                    if last_arrival is not None:
                        max_gap = max(max_gap, now - last_arrival)
                    continue
                if last_arrival is not None:
                    max_gap = max(max_gap, now - last_arrival)
                last_arrival = now
                count += 1
                if "caps" not in result:
                    buffer = sample.get_buffer()
                    result["caps"] = sample.get_caps().to_string()
                    result["buffer_size"] = buffer.get_size()
                    result["allocators"] = [buffer.peek_memory(i).allocator.name
                                             for i in range(buffer.n_memory())]
                    result["parent_buffer_meta_count"] = buffer.get_n_meta(parent_type)
                    upload = pipeline.get_by_name("upload")
                    if upload:
                        result["glupload_output_caps"] = upload.get_static_pad("src").get_current_caps().to_string()
                    buffer = None
                if phase == "retain":
                    if first_sample is None:
                        first_sample = sample
                        first_pts = sample.get_buffer().pts
                    history.append(sample)
                    if count == args.capacity * 2:
                        result["memory_after_two_cache_lengths"] = memory_snapshot()
                sample = None
            elapsed = time.monotonic() - start
            details = {"phase": phase, "samples": count,
                       "live_frames": live_count[0] - previous_live,
                       "seconds": elapsed, "fps": count / elapsed,
                       "max_gap_seconds": max_gap, "retained": len(history),
                       "memory": memory_snapshot()}
            if history:
                details["distinct_buffers"] = len({hash(s.get_buffer()) for s in history})
                details["distinct_memory_handles"] = len({hash(s.get_buffer().peek_memory(0))
                                                           for s in history})
                details["retained_nominal_bytes"] = sum(s.get_buffer().get_size() for s in history)
                details["oldest_pinned_pts_unchanged"] = first_sample.get_buffer().pts == first_pts
            result["phases"].append(details)
            print(f"{args.case} {phase}: {count / elapsed:.1f} fps, "
                  f"live={details['live_frames']}, held={len(history)}, "
                  f"max_gap={max_gap:.3f}s", flush=True)
            if result["errors"]:
                break
    finally:
        history.clear()
        first_sample = None
        pipeline.set_state(Gst.State.NULL)
    result["ok"] = (not result["errors"] and len(result["phases"]) == 3
                    and all(p["fps"] > 54 and p["max_gap_seconds"] < 0.5
                            for p in result["phases"][1:])
                    and result["phases"][1]["retained"] == args.capacity)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--capacity", type=int, default=120)
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=650)
    parser.add_argument("--seconds", type=float, default=6.0, help="Retention phase duration")
    parser.add_argument("--output", type=Path, default=Path("artifacts/gpu-retention"))
    args = parser.parse_args()
    if args.capacity < 1 or args.seconds <= args.capacity / 60:
        parser.error("Capacity must be positive; retention must exceed capacity / 60 seconds")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.case:
        try:
            result = probe(args)
        except Exception as exc:
            result = {"case": args.case, "ok": False, "exception": repr(exc)}
        (args.output / f"{args.case}.json").write_text(json.dumps(result, indent=2) + "\n")
        if not result["ok"]:
            print(json.dumps(result, indent=2), flush=True)
        return 0 if result["ok"] else 1
    results = []
    for name in CASES:
        command = [sys.executable, __file__, "--case", name, "--capacity", str(args.capacity),
                   "--width", str(args.width), "--height", str(args.height),
                   "--seconds", str(args.seconds),
                   "--output", str(args.output)]
        try:
            child = subprocess.run(command, text=True, capture_output=True, timeout=args.seconds + 20,
                                   env={**os.environ, "GST_GL_PLATFORM": "egl", "GST_GL_WINDOW": "wayland"})
            output = child.stdout + child.stderr
            code = child.returncode
        except subprocess.TimeoutExpired:
            output, code = "Timed out\n", -1
        print(output, end="", flush=True)
        (args.output / f"{name}.log").write_text(output)
        results.append({"case": name, "exit_code": code})
    (args.output / "suite.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(r["exit_code"] != 0 for r in results))


if __name__ == "__main__":
    sys.exit(main())
