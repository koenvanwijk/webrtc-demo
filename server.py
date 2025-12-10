import asyncio
import json
import os
from aiohttp import web

from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
    VideoStreamTrack,
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer
from av import VideoFrame
import numpy as np

pcs = set()

# STUN config – dit is de "STUN SERVER"
stun_config = RTCConfiguration(
    iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
)


class ColorBarsVideoTrack(VideoStreamTrack):
    """
    A video track that generates color bars test pattern.
    """
    def __init__(self):
        super().__init__()
        self.counter = 0

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        
        # Create a color bars test pattern
        width, height = 640, 480
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Create 7 vertical color bars
        bar_width = width // 7
        colors = [
            [255, 255, 255],  # White
            [255, 255, 0],    # Yellow
            [0, 255, 255],    # Cyan
            [0, 255, 0],      # Green
            [255, 0, 255],    # Magenta
            [255, 0, 0],      # Red
            [0, 0, 255],      # Blue
        ]
        
        for i, color in enumerate(colors):
            x_start = i * bar_width
            x_end = x_start + bar_width if i < 6 else width
            img[:, x_start:x_end] = color
        
        # Add a moving indicator
        indicator_pos = (self.counter % width)
        img[:, indicator_pos:indicator_pos+5] = [0, 0, 0]
        
        self.counter += 5
        
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame



async def index(request: web.Request):
    """Serve de demo pagina."""
    return web.FileResponse(os.path.join("static", "index.html"))


async def offer(request: web.Request):
    """Handel de offer van de WEB CLIENT af."""
    params = await request.json()
    print("\n[PYTHON] Received offer from web client")
    print("[PYTHON] Type:", params["type"])
    print("[PYTHON] First 80 chars of SDP:\n", params["sdp"][:80], "...")

    pc = RTCPeerConnection(configuration=stun_config)
    pcs.add(pc)

    @pc.on("icegatheringstatechange")
    async def on_ice_gathering_state_change():
        print("[PYTHON] ICE gathering state:", pc.iceGatheringState)

    @pc.on("iceconnectionstatechange")
    async def on_ice_connection_state_change():
        print("[PYTHON] ICE connection state:", pc.iceConnectionState)
        if pc.iceConnectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        print(f"[PYTHON] Track received: {track.kind}")
        media_sink = MediaBlackhole()
        media_sink.addTrack(track)

    # Add video track to send back to the client
    video_track = ColorBarsVideoTrack()
    pc.addTrack(video_track)
    print("[PYTHON] Added color bars video track to send to WEB CLIENT")

    # Remote description zetten (offer uit de browser)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    await pc.setRemoteDescription(offer)

    print("[PYTHON] Creating answer…")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("[PYTHON] Sending answer back to WEB CLIENT (ICE will continue gathering)")

    response = {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    }
    return web.Response(
        content_type="application/json",
        text=json.dumps(response),
    )


async def on_shutdown(app: web.Application):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    app = web.Application()
    app.on_shutdown.append(on_shutdown)

    # Routes
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_static("/static/", path="static", name="static")

    web.run_app(app, host="0.0.0.0", port=8080)
