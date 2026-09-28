#!/usr/bin/env python3
"""Check the real image receiver using local RTP; no robot connection."""
import socket
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from PySide6.QtCore import QCoreApplication
from operator_gui.video_receiver import MediaWorker

app = QCoreApplication([])
Gst.init(None)
print('PyGObject', gi.__version__, Gst.version_string(), flush=True)
for codec, decoder, encoder, payloader in (
    ('H264', 'avdec_h264', 'x264enc tune=zerolatency speed-preset=ultrafast', 'rtph264pay config-interval=1'),
    ('JPEG', 'jpegdec', 'jpegenc', 'rtpjpegpay'),
):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    worker = MediaWorker()
    errors = []
    worker.error.connect(errors.append)
    sender = None
    try:
        worker.start(dict(sink=None, output='image', decoder=decoder, latency=30,
            info=dict(encoding_name=codec, payload_type=96, ssrc=1234,
                      spec=dict(destination=dict(rtp_port=port)))))
        if errors:
            raise RuntimeError(errors)
        sender = Gst.parse_launch(
            'videotestsrc is-live=true ! video/x-raw,format=I420,width=320,height=240,framerate=15/1 ! '
            f'{encoder} ! {payloader} pt=96 ssrc=1234 ! udpsink host=127.0.0.1 port={port} sync=false')
        sender.set_state(Gst.State.PLAYING)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not errors:
            app.processEvents()
            with worker.lock:
                image = worker.image.copy() if worker.image is not None else None
            if image is not None and not image.isNull():
                assert (image.width(), image.height()) == (320, 240)
                print(f'{codec}: RTP -> {decoder} -> QImage 320x240 OK', flush=True)
                break
            time.sleep(.01)
        else:
            raise RuntimeError(f'{codec}: no image; {errors}')
    finally:
        if sender is not None:
            sender.set_state(Gst.State.NULL)
        worker.stop()
