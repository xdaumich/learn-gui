#!/usr/bin/env python3
"""Diagnose WebRTC pipeline layer by layer.

Run this INSTEAD of 'make dev' to isolate the failure point.
Requires OAK cameras connected and no other process holding them.

Usage:
    uv run --project server python scripts/diagnose_webrtc.py
"""

from __future__ import annotations

import asyncio
import fractions
import os
import signal
import subprocess
import sys
import time

# Hard exit on Ctrl+C
signal.signal(signal.SIGINT, lambda *_: os._exit(0))


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


# -------------------------------------------------------
# Layer 0: Check no other process holds OAK USB devices
# -------------------------------------------------------
def check_usb_holders() -> bool:
    section("Layer 0: USB device holders")
    OAK_VENDOR = "03e7"
    try:
        out = subprocess.run(
            ["lsusb", "-d", f"{OAK_VENDOR}:"],
            capture_output=True, text=True,
        ).stdout.strip()
    except FileNotFoundError:
        warn("lsusb not found, skipping holder check")
        return True

    if not out:
        fail("No OAK USB devices detected by lsusb!")
        return False

    import re
    devices = []
    for line in out.splitlines():
        m = re.match(r"Bus (\d+) Device (\d+):", line)
        if m:
            devices.append((m.group(1), m.group(2)))
        print(f"  {line}")

    ok(f"Found {len(devices)} OAK USB device(s)")

    my_pid = os.getpid()
    holders_found = False
    for bus, dev in devices:
        dev_path = f"/dev/bus/usb/{bus}/{dev}"
        try:
            result = subprocess.run(["fuser", dev_path], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                pids = [p.strip().rstrip("m") for p in result.stdout.split()]
                pids = [p for p in pids if p and int(p) != my_pid]
                if pids:
                    fail(f"{dev_path} held by PIDs: {pids}")
                    for pid in pids:
                        try:
                            cmdline = open(f"/proc/{pid}/cmdline").read().replace("\0", " ")
                            info(f"  PID {pid}: {cmdline[:100]}")
                        except Exception:
                            pass
                    holders_found = True
        except FileNotFoundError:
            pass

    if holders_found:
        fail("Other processes are holding OAK cameras! Stop them first.")
        return False

    ok("No other process holds OAK USB devices")
    return True


# -------------------------------------------------------
# Layer 1: DepthAI device discovery
# -------------------------------------------------------
def check_depthai_discovery():
    section("Layer 1: DepthAI device discovery")
    import depthai as dai

    available = dai.Device.getAllAvailableDevices()
    if not available:
        fail("dai.Device.getAllAvailableDevices() returned empty!")
        info("Devices may be stuck in BOOTED state from a previous crash.")
        info("Try: unplug/replug USB, or wait 30s for USB recycle.")
        return None

    ok(f"Found {len(available)} device(s):")
    for d in available:
        state = str(d.state).split(".")[-1] if hasattr(d, "state") else "?"
        info(f"  {d.deviceId} state={state}")

    return available


# -------------------------------------------------------
# Layer 2: Open device + H.264 pipeline
# -------------------------------------------------------
def check_h264_pipeline(device_info):
    section("Layer 2: H.264 pipeline (single camera)")
    import depthai as dai

    info(f"Opening device {device_info.deviceId}...")
    try:
        device = dai.Device(device_info)
    except Exception as e:
        fail(f"Failed to open device: {e}")
        return None, None, None

    model = device.getDeviceName()
    ok(f"Opened device: {model}")

    info("Building H.264 pipeline (640x480 @ 30fps)...")
    pipeline = dai.Pipeline(device)
    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    cam_out = cam.requestOutput((640, 480), dai.ImgFrame.Type.NV12, fps=30)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(30, dai.VideoEncoderProperties.Profile.H264_MAIN)
    try:
        encoder.setKeyframeFrequency(30)
    except Exception:
        pass
    try:
        encoder.setRateControlMode(dai.VideoEncoderProperties.RateControlMode.CBR)
        encoder.setBitrateKbps(700)
        encoder.setNumBFrames(0)
    except Exception:
        pass

    cam_out.link(encoder.input)
    queue = encoder.out.createOutputQueue(maxSize=4, blocking=False)

    info("Starting pipeline...")
    pipeline.start()

    info("Waiting for H.264 packets (up to 5s)...")
    got_idr = False
    got_p = False
    packet_count = 0
    t0 = time.time()

    while time.time() - t0 < 5.0:
        pkt = queue.tryGet()
        if pkt is None:
            time.sleep(0.01)
            continue

        data = bytes(pkt.getData())
        if not data:
            continue

        packet_count += 1

        # Parse NAL types
        nal_types = []
        i = 0
        while i < len(data) - 4:
            if data[i:i+4] == b'\x00\x00\x00\x01':
                nal_type = data[i+4] & 0x1f
                nal_types.append(nal_type)
                i += 5
            elif data[i:i+3] == b'\x00\x00\x01':
                nal_type = data[i+3] & 0x1f
                nal_types.append(nal_type)
                i += 4
            else:
                i += 1

        nal_names = {1: "P-slice", 5: "IDR", 7: "SPS", 8: "PPS", 9: "AUD"}
        nal_str = ", ".join(nal_names.get(t, f"NAL({t})") for t in nal_types)

        if 5 in nal_types:
            got_idr = True
        if 1 in nal_types:
            got_p = True

        if packet_count <= 5 or got_idr and got_p:
            info(f"  pkt #{packet_count}: {len(data)} bytes, NALs: [{nal_str}]")

        if got_idr and got_p and packet_count >= 5:
            break

    if packet_count == 0:
        fail("No H.264 packets received in 5 seconds!")
        fail("The H.264 encoder may not be producing output at 640x480.")
        info("Try changing resolution to 1280x800 (native OV9782)")
        pipeline.stop()
        device.close()
        return None, None, None

    if not got_idr:
        warn(f"Got {packet_count} packets but no IDR (keyframe)!")
    else:
        ok(f"Got {packet_count} H.264 packets (IDR + P-frames)")

    pipeline.stop()
    device.close()
    ok("Pipeline stopped, device closed")
    return packet_count, got_idr, got_p


# -------------------------------------------------------
# Layer 2b: Compare with MJPEG pipeline
# -------------------------------------------------------
def check_mjpeg_pipeline(device_info):
    section("Layer 2b: MJPEG pipeline comparison (same camera)")
    import depthai as dai

    info(f"Re-opening device {device_info.deviceId}...")
    time.sleep(1)  # brief pause for USB recycle

    # Re-discover since device was closed
    available = dai.Device.getAllAvailableDevices()
    target = None
    for d in available:
        if d.deviceId == device_info.deviceId:
            target = d
            break

    if target is None:
        # Try any available device
        if available:
            target = available[0]
            info(f"Original device not re-discovered, using {target.deviceId}")
        else:
            warn("No devices available for MJPEG comparison")
            return

    try:
        device = dai.Device(target)
    except Exception as e:
        warn(f"Failed to re-open device for MJPEG test: {e}")
        return

    pipeline = dai.Pipeline(device)
    cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
    cam_out = cam.requestOutput((1280, 800), dai.ImgFrame.Type.NV12, fps=30)

    encoder = pipeline.create(dai.node.VideoEncoder)
    encoder.setDefaultProfilePreset(30, dai.VideoEncoderProperties.Profile.MJPEG)
    encoder.setQuality(80)

    cam_out.link(encoder.input)
    queue = encoder.out.createOutputQueue(maxSize=4, blocking=False)

    pipeline.start()

    info("Waiting for MJPEG frames (up to 5s)...")
    frame_count = 0
    t0 = time.time()
    while time.time() - t0 < 5.0:
        pkt = queue.tryGet()
        if pkt is None:
            time.sleep(0.01)
            continue
        data = pkt.getData().tobytes()
        if data:
            frame_count += 1
            if frame_count <= 3:
                is_jpeg = data[:2] == b'\xff\xd8'
                info(f"  frame #{frame_count}: {len(data)} bytes, valid_jpeg={is_jpeg}")
            if frame_count >= 10:
                break

    pipeline.stop()
    device.close()

    if frame_count > 0:
        ok(f"MJPEG: got {frame_count} frames — camera hardware works fine")
    else:
        fail("MJPEG also produced no frames — camera hardware issue?")


# -------------------------------------------------------
# Layer 3: aiortc H.264 pack() with real camera data
# -------------------------------------------------------
def check_aiortc_pack():
    section("Layer 3: aiortc H264Encoder.pack() test")
    import av
    from aiortc.codecs.h264 import H264Encoder

    # Synthetic IDR packet (SPS + PPS + IDR)
    data = (
        b'\x00\x00\x00\x01\x09\x10'      # AUD
        b'\x00\x00\x00\x01\x67\x42\x00\x0a\xe8\x40\x40\x04'  # SPS
        b'\x00\x00\x00\x01\x68\xce\x38\x80'  # PPS
        b'\x00\x00\x00\x01\x65' + b'\xbb' * 200  # IDR
    )

    enc = H264Encoder()
    pkt = av.Packet(data)
    pkt.pts = 0
    pkt.time_base = fractions.Fraction(1, 90000)

    payloads, ts = enc.pack(pkt)
    if payloads:
        ok(f"pack() returned {len(payloads)} payload(s), total {sum(len(p) for p in payloads)} bytes")
    else:
        fail("pack() returned empty payloads!")
        return False

    # P-frame
    data2 = b'\x00\x00\x00\x01\x09\x10' + b'\x00\x00\x00\x01\x41' + b'\xaa' * 100
    pkt2 = av.Packet(data2)
    pkt2.pts = 3000
    pkt2.time_base = fractions.Fraction(1, 90000)
    payloads2, ts2 = enc.pack(pkt2)
    if payloads2:
        ok(f"P-frame pack(): {len(payloads2)} payload(s)")
    else:
        fail("P-frame pack() returned empty!")
        return False

    return True


# -------------------------------------------------------
# Layer 4: Full WHEP loopback test
# -------------------------------------------------------
async def check_whep_loopback():
    section("Layer 4: WHEP signaling loopback test")

    import depthai as dai
    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaRelay

    from telemetry_console.camera import _build_h264_pipeline, _discover_device_profiles
    from telemetry_console.webrtc_track import H264Track

    profiles = _discover_device_profiles()
    if not profiles:
        warn("No devices available for WHEP loopback (skipping)")
        return

    profile = profiles[0]
    info(f"Using device: {profile.device_name} ({profile.device_id})")

    device = dai.Device(profile.device_info)
    pipeline, queue = _build_h264_pipeline(
        device=device, width=640, height=480, fps=30, keyframe_interval=30,
    )
    pipeline.start()

    track = H264Track(queue=queue, fps=30)
    relay = MediaRelay()

    # Wait for at least one packet to be available
    info("Waiting for first H.264 packet...")
    t0 = time.time()
    while time.time() - t0 < 5:
        if track._latest is not None:
            ok("H264Track has data available")
            break
        await asyncio.sleep(0.1)
    else:
        fail("H264Track._latest is still None after 5s!")
        track.stop()
        pipeline.stop()
        device.close()
        return

    # Create browser-side PC (recvonly)
    browser_pc = RTCPeerConnection()
    browser_pc.addTransceiver("video", direction="recvonly")
    browser_offer = await browser_pc.createOffer()
    await browser_pc.setLocalDescription(browser_offer)
    offer_sdp = browser_pc.localDescription.sdp
    info(f"Browser offer SDP: {len(offer_sdp)} chars")

    if "m=video" not in offer_sdp:
        fail("Browser offer SDP missing m=video!")
        browser_pc.close()
        track.stop()
        pipeline.stop()
        device.close()
        return

    ok("Browser offer contains m=video")

    # Create server-side PC (the answer path from session_manager.answer)
    server_pc = RTCPeerConnection()
    relayed = relay.subscribe(track)
    server_pc.addTrack(relayed)

    received_frames = []

    @browser_pc.on("track")
    def on_track(track):
        info(f"Browser received track: kind={track.kind}")

        async def read_frames():
            for _ in range(10):
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=3)
                    received_frames.append(frame)
                except Exception as e:
                    warn(f"Frame recv error: {e}")
                    break

        asyncio.ensure_future(read_frames())

    await server_pc.setRemoteDescription(
        RTCSessionDescription(sdp=offer_sdp, type="offer")
    )
    answer = await server_pc.createAnswer()
    await server_pc.setLocalDescription(answer)
    answer_sdp = server_pc.localDescription.sdp

    if not answer_sdp:
        fail("Server answer SDP is empty!")
    else:
        info(f"Server answer SDP: {len(answer_sdp)} chars")
        if "m=video" in answer_sdp:
            ok("Server answer contains m=video")
        else:
            fail("Server answer missing m=video!")

        # Check for ICE candidates
        ice_candidates = [l for l in answer_sdp.splitlines() if l.startswith("a=candidate:")]
        if ice_candidates:
            ok(f"Server answer has {len(ice_candidates)} ICE candidate(s):")
            for c in ice_candidates[:5]:
                info(f"  {c}")
        else:
            fail("Server answer has NO ICE candidates!")
            info("aiortc could not gather any candidates.")
            info("Check: is stun:stun.l.google.com:19302 reachable?")

        # Check H.264 codec in answer
        h264_lines = [l for l in answer_sdp.splitlines() if "H264" in l.upper() or "h264" in l.lower()]
        if h264_lines:
            ok("Answer SDP includes H.264 codec")
            for l in h264_lines[:3]:
                info(f"  {l.strip()}")
        else:
            warn("No H.264 line found in answer SDP")

    # Complete the handshake
    await browser_pc.setRemoteDescription(
        RTCSessionDescription(sdp=answer_sdp, type="answer")
    )

    # Check connection states
    info("Waiting for ICE + DTLS connection (up to 10s)...")
    for i in range(100):
        state = server_pc.connectionState
        b_state = browser_pc.connectionState
        if i % 20 == 0:
            info(f"  server={state}, browser={b_state}")
        if state == "connected" and b_state == "connected":
            ok("Both peers connected!")
            break
        if state == "failed" or b_state == "failed":
            fail(f"Connection FAILED! server={state}, browser={b_state}")
            break
        await asyncio.sleep(0.1)
    else:
        fail(f"Connection timed out. server={server_pc.connectionState}, browser={browser_pc.connectionState}")

    # Wait for frames
    if server_pc.connectionState == "connected":
        info("Waiting for frames to arrive at browser (up to 5s)...")
        t0 = time.time()
        while time.time() - t0 < 5 and len(received_frames) < 5:
            await asyncio.sleep(0.2)

        if received_frames:
            ok(f"Browser received {len(received_frames)} frame(s) via WebRTC!")
            for i, f in enumerate(received_frames[:3]):
                info(f"  frame {i}: type={type(f).__name__}, pts={getattr(f, 'pts', '?')}")
        else:
            fail("Browser received 0 frames despite connected state!")
            info("H.264 data may not be reaching the RTP sender.")

    # Cleanup
    await browser_pc.close()
    await server_pc.close()
    track.stop()
    pipeline.stop()
    device.close()
    ok("Cleanup done")


# -------------------------------------------------------
# Layer 5: Network / ICE candidate check
# -------------------------------------------------------
def check_network():
    section("Layer 5: Network / ICE candidate analysis")

    import socket

    # Get all local IPs
    info("Local network interfaces:")
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    info(f"  {iface}: {addr['addr']}")
    except ImportError:
        # Fallback: use socket
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
            info(f"  hostname={hostname}, ip={ip}")
        except Exception:
            pass

        # Also try getting all IPs
        try:
            result = subprocess.run(
                ["ip", "-4", "addr", "show"],
                capture_output=True, text=True,
            )
            for line in result.stdout.splitlines():
                if "inet " in line:
                    info(f"  {line.strip()}")
        except Exception:
            pass

    # Check STUN reachability
    info("\nSTUN server reachability:")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        sock.connect(("stun.l.google.com", 19302))
        local_ip = sock.getsockname()[0]
        ok(f"Can reach STUN server (local IP via STUN: {local_ip})")
        sock.close()
    except Exception as e:
        warn(f"Cannot reach STUN server: {e}")
        info("This is OK for LAN — host candidates will still work.")


# -------------------------------------------------------
# Main
# -------------------------------------------------------
def main():
    print("\n" + "=" * 60)
    print("  WebRTC Pipeline Diagnostic")
    print("  Run this INSTEAD of 'make dev' to isolate failures")
    print("=" * 60)

    os.chdir(os.path.join(os.path.dirname(__file__), ".."))

    if not check_usb_holders():
        print("\n*** Fix USB holder issue first, then re-run ***")
        return 1

    devices = check_depthai_discovery()
    if not devices:
        return 1

    h264_count, got_idr, got_p = check_h264_pipeline(devices[0])
    if h264_count is None or h264_count == 0:
        info("\nRe-checking with MJPEG to confirm camera hardware is OK...")
        time.sleep(2)  # wait for USB recycle
        # Re-discover
        import depthai as dai
        devices2 = dai.Device.getAllAvailableDevices()
        if devices2:
            check_mjpeg_pipeline(devices2[0])

        print("\n*** H.264 pipeline failed. See details above. ***")
        return 1

    if not check_aiortc_pack():
        return 1

    check_network()

    print("\n" + "-" * 60)
    info("Running full WHEP loopback test (camera → aiortc → recv)...")
    print("-" * 60)

    # Need to wait for USB device to recycle after Layer 2 test closed it
    info("Waiting 2s for USB device recycle...")
    time.sleep(2)

    asyncio.run(check_whep_loopback())

    section("Summary")
    info("If all layers passed, the WebRTC pipeline code is correct.")
    info("If video still doesn't appear in the browser, check:")
    info("  1. Browser console for WebRTC/ICE errors")
    info("  2. VITE_API_BASE_URL points to this machine's routable IP")
    info("  3. UDP ports are not blocked by firewall (iptables/nftables)")
    info("  4. No other process grabbed cameras between diag and make dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
