"""
Comprehensive test suite for WebRTC demo server.
Tests server endpoints, video track generation, and NAT detection.
"""
import pytest
import asyncio
import json
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from unittest.mock import Mock, patch, MagicMock
import numpy as np

# Import server components
import server
from server import (
    index,
    offer,
    ColorBarsVideoTrack,
    detect_nat_type,
    on_shutdown,
)


class TestColorBarsVideoTrack:
    """Test the ColorBarsVideoTrack class."""

    @pytest.mark.asyncio
    async def test_video_track_initialization(self):
        """Test that video track initializes correctly."""
        track = ColorBarsVideoTrack()
        assert track.counter == 0
        assert track.kind == "video"

    @pytest.mark.asyncio
    async def test_video_frame_generation(self):
        """Test that video frames are generated correctly."""
        track = ColorBarsVideoTrack()

        # Generate a frame
        frame = await track.recv()

        # Verify frame properties
        assert frame is not None
        assert frame.width == 640
        assert frame.height == 480
        assert frame.format.name == "rgb24"

    @pytest.mark.asyncio
    async def test_video_counter_increments(self):
        """Test that the counter increments with each frame."""
        track = ColorBarsVideoTrack()
        initial_counter = track.counter

        await track.recv()
        assert track.counter == initial_counter + 5

        await track.recv()
        assert track.counter == initial_counter + 10


class TestServerEndpoints(AioHTTPTestCase):
    """Test HTTP endpoints of the WebRTC server."""

    async def get_application(self):
        """Create the test application."""
        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_post("/offer", offer)
        app.router.add_static("/static/", path="static", name="static")
        return app

    async def test_index_endpoint(self):
        """Test that the index endpoint serves the HTML file."""
        resp = await self.client.request("GET", "/")
        assert resp.status == 200
        text = await resp.text()
        assert "WebRTC" in text or "html" in text.lower()

    async def test_offer_endpoint_with_valid_offer(self):
        """Test the offer endpoint with a valid WebRTC offer."""
        # Create a minimal SDP offer
        sdp_offer = """v=0
o=- 123456789 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=msid-semantic: WMS
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:testpassword1234567890
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=mid:0
a=sendrecv
a=rtcp-mux
a=rtpmap:96 VP8/90000
"""

        payload = {
            "sdp": sdp_offer,
            "type": "offer"
        }

        resp = await self.client.request(
            "POST",
            "/offer",
            json=payload
        )

        assert resp.status == 200
        data = await resp.json()

        # Verify response structure
        assert "sdp" in data
        assert "type" in data
        assert data["type"] == "answer"

        # Verify NAT info is included
        assert "nat_info" in data

    async def test_static_files_served(self):
        """Test that static files are served correctly."""
        resp = await self.client.request("GET", "/static/index.html")
        assert resp.status == 200


class TestNATDetection:
    """Test NAT detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_nat_type_structure(self):
        """Test that NAT detection returns expected structure."""
        # Run NAT detection
        await detect_nat_type()

        # Verify server_nat_info is populated
        assert server.server_nat_info is not None
        assert "local_ip" in server.server_nat_info
        assert "public_ip" in server.server_nat_info
        assert "nat_type" in server.server_nat_info
        assert "nat_category" in server.server_nat_info

    @pytest.mark.asyncio
    async def test_nat_detection_has_valid_local_ip(self):
        """Test that NAT detection finds a valid local IP."""
        await detect_nat_type()

        local_ip = server.server_nat_info.get("local_ip")
        assert local_ip is not None
        assert local_ip != "Unknown"

        # Basic IP format validation
        parts = local_ip.split(".")
        assert len(parts) == 4


class TestServerStartupShutdown:
    """Test server lifecycle management."""

    @pytest.mark.asyncio
    async def test_on_shutdown_clears_connections(self):
        """Test that shutdown properly closes all peer connections."""
        # Create actual async close function
        async def async_close():
            pass

        # Create mock peer connections with async close methods
        mock_pc1 = Mock()
        mock_pc1.close = async_close
        mock_pc2 = Mock()
        mock_pc2.close = async_close

        server.pcs.add(mock_pc1)
        server.pcs.add(mock_pc2)

        # Create mock app
        app = web.Application()

        # Run shutdown
        await on_shutdown(app)

        # Verify connections were closed and cleared
        assert len(server.pcs) == 0


class TestVideoGeneration:
    """Test video frame generation details."""

    @pytest.mark.asyncio
    async def test_color_bars_pattern(self):
        """Test that color bars are generated with correct colors."""
        track = ColorBarsVideoTrack()
        frame = await track.recv()

        # Convert frame to numpy array for analysis
        arr = frame.to_ndarray(format="rgb24")

        # Verify dimensions
        assert arr.shape == (480, 640, 3)

        # Check a pixel from the middle of the first bar (avoid indicator)
        # First bar should be white [255, 255, 255]
        # Bar width is 640 // 7 = 91, so pixel at x=45 should be in first white bar
        middle_of_first_bar = arr[0, 45]
        assert np.array_equal(middle_of_first_bar, [255, 255, 255])

    @pytest.mark.asyncio
    async def test_moving_indicator(self):
        """Test that the moving indicator changes position."""
        track = ColorBarsVideoTrack()

        # Get first frame
        frame1 = await track.recv()
        arr1 = frame1.to_ndarray(format="rgb24")

        # Get second frame
        frame2 = await track.recv()
        arr2 = frame2.to_ndarray(format="rgb24")

        # Frames should be different due to moving indicator
        assert not np.array_equal(arr1, arr2)


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset server state before each test."""
    server.pcs.clear()
    server.server_nat_info = None
    yield
    server.pcs.clear()
    server.server_nat_info = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
