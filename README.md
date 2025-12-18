# WebRTC Demo: Interactive Network Visualization & Diagnostics

A comprehensive WebRTC demo showing the complete connection flow between a web browser and Python (aiortc) with detailed sequence diagrams, network topology visualization, and NAT detection.

## Features

- **Interactive 5-Column Sequence Diagram**: Visual representation of the complete WebRTC flow
  - WEB CLIENT, SIGNALING SERVER, STUN SERVER, TURN SERVER, PYTHON WEBRTC
  - Animated arrows showing message flow with timing
  - Real-time activation as connection progresses

- **Network Topology Visualization**: Shows actual network layout
  - Browser and Python server with their local/public IPs (dynamically detected)
  - NAT routers with detected types
  - Visual representation of why connections succeed or fail

- **ICE Candidate Analysis**: Deep dive into WebRTC negotiation
  - Lists all local and remote candidates with types (host, srflx, relay)
  - Shows the actual selected candidate pair used for connection
  - Explains connection path (direct P2P, STUN-assisted, or TURN relay)

- **Server-Side NAT Detection**: Python server detects its own NAT type on startup
  - Uses STUN to discover public IP
  - Detects NAT presence and candidate types
  - Results displayed in browser

- **Real-time Timeline Log**: Shows exact timing (in ms) of each step
  - Delta timestamps from connection start
  - Color-coded by component
  - Tracks ICE gathering, signaling, and connection states

- **Video Streaming**: Color bars test pattern from Python to browser

- **Internationalization**: Supports English and Dutch languages

## Architecture

```
┌─────────────┐        ┌──────────────┐        ┌─────────────┐
│ WEB CLIENT  │◄──────►│  SIGNALING   │◄──────►│   PYTHON    │
│  (Browser)  │  HTTP  │    SERVER    │  Local │   WEBRTC    │
└─────────────┘        └──────────────┘        └─────────────┘
      │                                                │
      │                                                │
      ├──────────────► STUN SERVER ◄──────────────────┤
      │             (stun.l.google.com)                │
      │                                                │
      └──────────────► TURN SERVERS ◄─────────────────┘
                  (openrelay, numb.viagenie)
```

## Installation

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/koenvanwijk/webrtc-demo.git
   cd webrtc-demo
   ```

2. Create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Demo

1. Activate the virtual environment (if not already active):
   ```bash
   source .venv/bin/activate
   ```

2. Start the server:
   ```bash
   python server.py
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:8085
   ```

4. Click **"Start WebRTC flow"** and watch the visualization.

## Testing

### Setup for Testing

1. Install test dependencies:
   ```bash
   pip install -r requirements-test.txt
   ```

### Running Python Tests

Run all tests:
```bash
pytest
```

Run with verbose output:
```bash
pytest -v
```

Run a specific test file:
```bash
pytest tests/test_server.py
```

Run a specific test class or function:
```bash
pytest tests/test_server.py::TestColorBarsVideoTrack
pytest tests/test_server.py::TestColorBarsVideoTrack::test_recv_returns_frame
```

### Running JavaScript Tests

Open `tests/test_client.html` in a browser to run the client-side tests. These tests verify:

- ICE candidate parsing
- Translation system
- Network analysis logic
- WebRTC API availability
- MediaStream handling

## Files

- `server.py` - Python WebRTC server with signaling endpoints
- `static/index.html` - Web client with interactive diagram
- `requirements.txt` - Python dependencies

## How It Works

### 1. Server Startup & NAT Detection
- Python server starts and performs NAT detection
- Uses STUN to discover local and public IPs
- Detects presence of NAT and candidate types
- Results stored and sent to browser with answer

### 2. ICE Gathering (Web Client)
- Browser contacts STUN server to discover public IP
- Gathers host (local), srflx (STUN), and relay (TURN) candidates
- Waits up to 10 seconds for gathering to complete
- Displays all candidates in real-time

### 3. Offer Exchange
- Web client creates SDP offer with ICE candidates
- Sends offer to signaling server via HTTP POST
- Signaling server forwards to Python WebRTC peer

### 4. ICE Gathering (Python)
- Python peer contacts STUN server
- Gathers its own ICE candidates
- Waits up to 5 seconds for gathering
- Includes NAT detection results in answer

### 5. Answer Exchange
- Python creates SDP answer with ICE candidates + NAT info
- Sends back through signaling server
- Web client receives and applies answer
- Browser displays Python's NAT detection results

### 6. ICE Connection & Analysis
- Both peers try all candidate pairs
- Browser uses getStats() to see which pair succeeded
- Connection established when compatible pair found
- Analysis shows actual selected candidates and connection type

## Understanding the Visualizations

### ICE Candidate Types
- **host**: Local IP address (direct connection, same network)
- **srflx**: Server reflexive (public IP discovered via STUN)
- **relay**: TURN relay address (fallback when NAT blocks direct connection)

### NAT Types Explained
- **No NAT / Same Network**: Direct connection possible, no traversal needed
- **Full Cone / Port-Restricted NAT**: Allows P2P with STUN assistance
- **Symmetric NAT**: Blocks unsolicited inbound, requires TURN relay
- **Behind NAT (unknown)**: Detected but type determined by connection test

### Connection Paths
1. **Direct P2P (host → host)**: Both on same network, optimal
2. **STUN-assisted P2P (srflx → srflx)**: NAT traversal via public IPs
3. **TURN relay (relay)**: Symmetric NAT blocked direct, using relay server

## SSH Tunnel Limitations

**Important:** If you're accessing this demo through an SSH tunnel (e.g., `ssh -L 8085:localhost:8085 remote-server`), the WebRTC connection will likely **fail** because:

1. The browser is on your local machine (e.g., 192.168.90.x)
2. The Python server is on a remote machine (e.g., 192.168.86.x)
3. ICE candidates contain local network addresses
4. Peers can't reach each other's local IPs

### Solutions for SSH Tunnel Scenarios

#### Option 1: Run Locally
Run both the server and browser on the same machine:
```bash
python server.py
# Open http://localhost:8085 locally
```

#### Option 2: Use TURN Server (Relay)
The demo includes free TURN servers but they may not work reliably with aiortc. For production, use:
- **Twilio TURN** (paid, reliable)
- **Coturn** (self-hosted, free)
- **xirsys** (paid service)

#### Option 3: SSH Tunnel Both Directions
Make sure the Python server can reach the browser's network or vice versa.

## Troubleshooting

### Connection Failed - Different Networks
**Symptom**: ICE state goes to "failed", analysis shows "No Compatible Path"

**Diagnosis**:
- Check Network Topology section - are browser and server on different networks?
- Check ICE Candidate Analysis - do you have overlapping networks or relay candidates?

**Solutions**:
1. Use same network for both peers (recommended for testing)
2. Configure reliable TURN server (required for production across different networks)
3. If using SSH tunnel: signaling works, but media needs TURN relay

### Connection Failed - Same Network
**Symptom**: Both on same network but connection fails

**Diagnosis**:
- Check for firewall blocking UDP traffic
- Verify host candidates are being generated
- Check browser console for errors

**Solutions**:
1. Disable firewall temporarily to test
2. Check that UDP ports are not blocked
3. Ensure both peers have network connectivity

### No Video
- Check camera permissions in browser
- Verify Python server is sending video track (check server console)
- Python sends color bars test pattern (doesn't require camera)
- Check browser console for errors
- Note: Camera is optional - the demo works without local camera access

### Camera Access Issues
- Camera access requires HTTPS or localhost
- When accessing from another machine over HTTP, camera will be unavailable
- The demo continues without local video and still receives video from Python

## Technologies

### Backend
- **aiortc** - WebRTC implementation for Python
- **aiohttp** - Async HTTP server for signaling
- **aioice** - ICE implementation and NAT detection
- **av (PyAV)** - Video frame handling
- **numpy** - Test pattern generation

### Frontend
- **WebRTC API** - Browser native WebRTC support
- **RTCPeerConnection** - Peer connection management
- **getStats()** - Detailed connection statistics and selected candidate pairs
- Pure JavaScript - No frameworks required

### Testing
- **pytest** - Python test framework
- **pytest-asyncio** - Async test support
- **pytest-aiohttp** - aiohttp test client

## License

MIT
