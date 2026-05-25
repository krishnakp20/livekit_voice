"""Quick checks before running the agent worker (WebRTC / LiveKit connectivity)."""
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

url = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
parsed = urlparse(url.replace("wss://", "http://").replace("ws://", "http://"))
host = parsed.hostname or "127.0.0.1"
port = parsed.port or 7880

print("VBots worker network check")
print(f"  LIVEKIT_URL={url}")
print(f"  TCP target={host}:{port}")

ok = True
try:
    s = socket.create_connection((host, port), timeout=5)
    s.close()
    print("  TCP 7880 (signaling): OK")
except OSError as e:
    print(f"  TCP 7880 (signaling): FAIL ({e})")
    ok = False

print()
print("WebRTC (audio) also needs UDP 50000-60000 open on the LiveKit SERVER")
print("and infra/livekit.yaml must set rtc.node_ip to the server LAN IP (e.g. 192.168.10.30)")
print()
if not ok:
    print("Fix signaling first, then restart worker with: python worker/agent.py start")
    sys.exit(1)
print("Signaling OK. If you still see wait_pc_connection timed out:")
print("  1. On LiveKit host: set node_ip in livekit.yaml, restart LiveKit")
print("  2. Open firewall UDP 50000-60000")
print("  3. Or run worker ON the LiveKit server with LIVEKIT_URL=ws://127.0.0.1:7880")
