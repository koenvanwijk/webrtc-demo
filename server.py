import asyncio
import json
import os
import socket
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
import aioice

pcs = set()
server_nat_info = None  # Store NAT detection results

# STUN/TURN config – dit is de "STUN SERVER"
# For SSH tunnel scenarios, we need TURN to relay traffic
stun_config = RTCConfiguration(
    iceServers=[
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        # Free TURN servers for testing
        RTCIceServer(
            urls=[
                "turn:openrelay.metered.ca:80",
                "turn:openrelay.metered.ca:443",
                "turns:openrelay.metered.ca:443"
            ],
            username="openrelayproject",
            credential="openrelayproject"
        ),
        RTCIceServer(
            urls=[
                "turn:numb.viagenie.ca",
            ],
            username="webrtc@live.com",
            credential="muazkh"
        ),
    ]
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



async def detect_nat_type():
    """Detect NAT type by testing with STUN servers."""
    global server_nat_info
    
    try:
        print("\n[NAT DETECTION] Starting NAT type detection on server...")
        
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Create ICE connection to gather candidates
        connection = aioice.Connection(ice_controlling=True, stun_server=("stun.l.google.com", 19302))
        
        # Gather candidates
        await connection.gather_candidates()
        
        candidates = connection.local_candidates
        print(f"[NAT DETECTION] Gathered {len(candidates)} candidates")
        
        # Analyze candidates
        has_host = False
        has_srflx = False
        public_ip = None
        
        for candidate in candidates:
            print(f"[NAT DETECTION] Candidate: {candidate.type} {candidate.host}:{candidate.port}")
            if candidate.type == "host":
                has_host = True
            elif candidate.type == "srflx":
                has_srflx = True
                public_ip = candidate.host
        
        # Determine NAT type
        if has_host and not has_srflx:
            nat_type = "No NAT detected - Same network as browser"
            nat_category = "none"
        elif has_host and has_srflx:
            # Have both local and public IP - behind NAT
            # Can't fully determine without more complex tests
            nat_type = "Behind NAT (type will be determined by connection test)"
            nat_category = "unknown"
        else:
            nat_type = "Unknown network configuration"
            nat_category = "unknown"
        
        server_nat_info = {
            "local_ip": local_ip,
            "public_ip": public_ip or "Not detected",
            "nat_type": nat_type,
            "nat_category": nat_category,
            "has_srflx": has_srflx,
        }
        
        print(f"[NAT DETECTION] Local IP: {local_ip}")
        print(f"[NAT DETECTION] Public IP: {public_ip or 'Not detected'}")
        print(f"[NAT DETECTION] NAT Type: {nat_type}")
        
        await connection.close()
        
    except Exception as e:
        print(f"[NAT DETECTION] Error: {e}")
        import traceback
        traceback.print_exc()
        server_nat_info = {
            "local_ip": "Unknown",
            "public_ip": "Detection failed",
            "error": str(e),
            "nat_type": "NAT detection failed - check server logs",
            "nat_category": "error"
        }


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

    @pc.on("icecandidate")
    def on_ice_candidate(candidate):
        if candidate:
            print(f"[PYTHON] ICE candidate: {candidate.candidate}")
        else:
            print("[PYTHON] ICE candidate gathering complete (null candidate)")

    @pc.on("iceconnectionstatechange")
    async def on_ice_connection_state_change():
        print(f"[PYTHON] ICE connection state: {pc.iceConnectionState}")
        if pc.iceConnectionState == "connected":
            print("[PYTHON] ✓ ICE CONNECTION ESTABLISHED!")
        elif pc.iceConnectionState == "completed":
            print("[PYTHON] ✓ ICE CONNECTION COMPLETED!")
        elif pc.iceConnectionState in ("failed", "closed", "disconnected"):
            print(f"[PYTHON] ✗ Connection issue - state: {pc.iceConnectionState}")
            # Don't close immediately on disconnected, give it time to reconnect
            if pc.iceConnectionState in ("failed", "closed"):
                print("[PYTHON] Closing peer connection")
                await pc.close()
                pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        print(f"[PYTHON] Track received: {track.kind}")
        # Echo the received track back to the client
        pc.addTrack(track)
        print(f"[PYTHON] Echoing {track.kind} track back to WEB CLIENT")

    # Optionally add color bars (comment out if you only want the echo)
    # video_track = ColorBarsVideoTrack()
    # pc.addTrack(video_track)
    # print("[PYTHON] Added color bars video track to send to WEB CLIENT")

    # Remote description zetten (offer uit de browser)
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    await pc.setRemoteDescription(offer)

    print("[PYTHON] Creating answer…")
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print("[PYTHON] Waiting for ICE gathering to complete...")
    # In aiortc, ICE gathering happens in the background
    # We need to wait longer for TURN server candidates
    await asyncio.sleep(5.0)  # Give it 5 seconds to gather TURN candidates
    
    print("[PYTHON] ICE gathering complete, sending answer back to WEB CLIENT")
    if pc.localDescription:
        candidate_count = pc.localDescription.sdp.count('a=candidate')
        print(f"[PYTHON] Local description has {candidate_count} candidates")
        if candidate_count == 0:
            print("[PYTHON] WARNING: No ICE candidates in SDP! Connection will likely fail.")

    response = {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "nat_info": server_nat_info,  # Include NAT detection results
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
    # Enable aiortc logging for debugging
    import logging
    import sys
    logging.basicConfig(level=logging.INFO)
    
    # Get port from command line argument or use default
    port = 8085
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            sys.exit(1)
    
    print(f"Starting server on http://0.0.0.0:{port}")
    print(f"Open http://<server-ip>:{port} in your browser to test WebRTC")
    
    async def startup():
        """Run NAT detection on startup."""
        await detect_nat_type()
    
    app = web.Application()
    app.on_startup.append(lambda _: startup())
    app.on_shutdown.append(on_shutdown)

    # Routes
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    app.router.add_static("/static/", path="static", name="static")
    
    web.run_app(app, host="0.0.0.0", port=port)
