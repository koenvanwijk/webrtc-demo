"""
Tests for the WebRTC demo server.

These tests cover:
- HTTP endpoints (index, offer)
- ColorBarsVideoTrack video generation
- NAT detection logic
- Server lifecycle and cleanup
"""

import asyncio
import json
import pytest
from fractions import Fraction
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import numpy as np

# Import server components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    ColorBarsVideoTrack,
    index,
    offer,
    on_shutdown,
    pcs,
    detect_nat_type,
)


class TestColorBarsVideoTrack:
    """Tests for the ColorBarsVideoTrack class."""

    @pytest.fixture
    def video_track(self):
        """Create a fresh video track for each test."""
        return ColorBarsVideoTrack()

    def test_init(self, video_track):
        """Test that video track initializes correctly."""
        assert video_track.counter == 0

    @pytest.mark.asyncio
    async def test_recv_returns_frame(self, video_track):
        """Test that recv() returns a valid video frame."""
        # Mock the next_timestamp method - time_base must be a Fraction
        video_track.next_timestamp = AsyncMock(return_value=(0, Fraction(1, 30)))

        frame = await video_track.recv()

        assert frame is not None
        assert frame.width == 640
        assert frame.height == 480

    @pytest.mark.asyncio
    async def test_recv_increments_counter(self, video_track):
        """Test that counter increments with each frame."""
        video_track.next_timestamp = AsyncMock(return_value=(0, Fraction(1, 30)))

        initial_counter = video_track.counter
        await video_track.recv()

        assert video_track.counter == initial_counter + 5

    @pytest.mark.asyncio
    async def test_recv_creates_color_bars(self, video_track):
        """Test that the frame contains the expected color bars pattern."""
        video_track.next_timestamp = AsyncMock(return_value=(0, Fraction(1, 30)))

        frame = await video_track.recv()

        # Convert frame to numpy array for inspection
        img = frame.to_ndarray(format="rgb24")

        # Check dimensions
        assert img.shape == (480, 640, 3)

        # Check that we have different colors (not all black or white)
        unique_colors = len(np.unique(img.reshape(-1, 3), axis=0))
        assert unique_colors >= 7  # At least 7 color bars + black indicator

    @pytest.mark.asyncio
    async def test_recv_moving_indicator(self, video_track):
        """Test that the moving indicator changes position."""
        video_track.next_timestamp = AsyncMock(return_value=(0, Fraction(1, 30)))

        # Get first frame
        frame1 = await video_track.recv()
        img1 = frame1.to_ndarray(format="rgb24")

        # Get second frame
        video_track.next_timestamp = AsyncMock(return_value=(1, Fraction(1, 30)))
        frame2 = await video_track.recv()
        img2 = frame2.to_ndarray(format="rgb24")

        # Frames should be different due to moving indicator
        assert not np.array_equal(img1, img2)


class TestIndexEndpoint:
    """Tests for the index endpoint."""

    @pytest.mark.asyncio
    async def test_index_returns_file_response(self):
        """Test that index returns a FileResponse."""
        from aiohttp import web

        mock_request = Mock(spec=web.Request)

        # The function returns a FileResponse pointing to static/index.html
        with patch('os.path.join', return_value='static/index.html'):
            response = await index(mock_request)

        assert isinstance(response, web.FileResponse)


class TestOfferEndpoint:
    """Tests for the offer endpoint."""

    @pytest.fixture
    def sample_sdp_offer(self):
        """Return a minimal valid SDP offer."""
        return {
            "type": "offer",
            "sdp": """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=mid:0
a=recvonly
a=rtcp-mux
a=rtpmap:96 VP8/90000
"""
        }

    @pytest.mark.asyncio
    async def test_offer_requires_json_body(self):
        """Test that offer endpoint requires a JSON body."""
        from aiohttp import web

        mock_request = Mock(spec=web.Request)
        mock_request.json = AsyncMock(side_effect=json.JSONDecodeError("", "", 0))

        with pytest.raises(json.JSONDecodeError):
            await offer(mock_request)

    @pytest.mark.asyncio
    async def test_offer_requires_sdp_field(self, sample_sdp_offer):
        """Test that offer endpoint requires sdp field."""
        from aiohttp import web

        mock_request = Mock(spec=web.Request)
        mock_request.json = AsyncMock(return_value={"type": "offer"})  # Missing sdp

        with pytest.raises(KeyError):
            await offer(mock_request)

    @pytest.mark.asyncio
    async def test_offer_requires_type_field(self, sample_sdp_offer):
        """Test that offer endpoint requires type field."""
        from aiohttp import web

        mock_request = Mock(spec=web.Request)
        mock_request.json = AsyncMock(return_value={"sdp": "v=0..."})  # Missing type

        with pytest.raises(KeyError):
            await offer(mock_request)


class TestNATDetection:
    """Tests for NAT detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_nat_type_sets_server_nat_info(self):
        """Test that detect_nat_type sets the global server_nat_info."""
        import server

        # Mock socket to avoid network calls
        mock_socket = Mock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 12345)

        # Mock aioice Connection
        mock_connection = AsyncMock()
        mock_candidate_host = Mock()
        mock_candidate_host.type = "host"
        mock_candidate_host.host = "192.168.1.100"
        mock_candidate_host.port = 12345

        mock_candidate_srflx = Mock()
        mock_candidate_srflx.type = "srflx"
        mock_candidate_srflx.host = "203.0.113.1"
        mock_candidate_srflx.port = 54321

        mock_connection.local_candidates = [mock_candidate_host, mock_candidate_srflx]
        mock_connection.gather_candidates = AsyncMock()
        mock_connection.close = AsyncMock()

        with patch('socket.socket', return_value=mock_socket):
            with patch('aioice.Connection', return_value=mock_connection):
                await detect_nat_type()

        assert server.server_nat_info is not None
        assert server.server_nat_info["local_ip"] == "192.168.1.100"
        assert server.server_nat_info["public_ip"] == "203.0.113.1"
        assert server.server_nat_info["has_srflx"] == True

    @pytest.mark.asyncio
    async def test_detect_nat_type_handles_no_srflx(self):
        """Test NAT detection when no srflx candidate is found."""
        import server

        mock_socket = Mock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 12345)

        mock_connection = AsyncMock()
        mock_candidate_host = Mock()
        mock_candidate_host.type = "host"
        mock_candidate_host.host = "192.168.1.100"
        mock_candidate_host.port = 12345

        mock_connection.local_candidates = [mock_candidate_host]
        mock_connection.gather_candidates = AsyncMock()
        mock_connection.close = AsyncMock()

        with patch('socket.socket', return_value=mock_socket):
            with patch('aioice.Connection', return_value=mock_connection):
                await detect_nat_type()

        assert server.server_nat_info["nat_type"] == "No NAT detected - Same network as browser"
        assert server.server_nat_info["nat_category"] == "none"

    @pytest.mark.asyncio
    async def test_detect_nat_type_handles_errors(self):
        """Test that NAT detection handles errors gracefully."""
        import server

        with patch('socket.socket', side_effect=Exception("Network error")):
            await detect_nat_type()

        assert server.server_nat_info is not None
        assert "error" in server.server_nat_info
        assert server.server_nat_info["nat_category"] == "error"


class TestServerLifecycle:
    """Tests for server startup and shutdown."""

    @pytest.mark.asyncio
    async def test_on_shutdown_closes_peer_connections(self):
        """Test that on_shutdown closes all peer connections."""
        from aiohttp import web

        # Create mock peer connections
        mock_pc1 = AsyncMock()
        mock_pc1.close = AsyncMock()
        mock_pc2 = AsyncMock()
        mock_pc2.close = AsyncMock()

        # Add to global set
        pcs.add(mock_pc1)
        pcs.add(mock_pc2)

        mock_app = Mock(spec=web.Application)

        await on_shutdown(mock_app)

        mock_pc1.close.assert_called_once()
        mock_pc2.close.assert_called_once()
        assert len(pcs) == 0

    @pytest.mark.asyncio
    async def test_on_shutdown_handles_empty_pcs(self):
        """Test that on_shutdown works with no peer connections."""
        from aiohttp import web

        pcs.clear()
        mock_app = Mock(spec=web.Application)

        # Should not raise
        await on_shutdown(mock_app)

        assert len(pcs) == 0


class TestSTUNConfiguration:
    """Tests for STUN/TURN server configuration."""

    def test_stun_config_has_google_stun(self):
        """Test that config includes Google STUN server."""
        from server import stun_config

        urls = []
        for server in stun_config.iceServers:
            urls.extend(server.urls)

        assert any("stun.l.google.com" in url for url in urls)

    def test_stun_config_has_turn_servers(self):
        """Test that config includes TURN servers."""
        from server import stun_config

        urls = []
        for server in stun_config.iceServers:
            urls.extend(server.urls)

        turn_urls = [url for url in urls if url.startswith("turn:") or url.startswith("turns:")]
        assert len(turn_urls) >= 2  # At least 2 TURN URLs


class TestIntegration:
    """Integration tests using aiohttp test client."""

    @pytest.fixture
    def app(self):
        """Create test application."""
        from aiohttp import web
        import server

        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_post("/offer", offer)
        app.on_shutdown.append(on_shutdown)

        # Set up NAT info for tests
        server.server_nat_info = {
            "local_ip": "127.0.0.1",
            "public_ip": "Not detected",
            "nat_type": "Test environment",
            "nat_category": "none",
            "has_srflx": False,
        }

        return app

    @pytest.mark.asyncio
    async def test_index_serves_html(self, app):
        """Test that index endpoint serves HTML file."""
        from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            # Content type should be HTML
            assert "text/html" in resp.content_type


# Fixtures for pytest-aiohttp
@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
