"""
receive-audio.py
Record audio from a V380 camera microphone and save as WAV.
Reads camera credentials from data.yaml (same format as v380-audio-player).
"""

import socket
import struct
import time
import os
import yaml
import questionary
from Crypto.Cipher import AES
import random
import string


# ─────────────────────────── auth ───────────────────────────

def generate_password(password: str) -> bytes:
    random_key = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    static_key = b'macrovideo+*#!^@'
    pad = 16 - (len(password) % 16)
    padded = password.encode() + bytes([pad] * pad)
    aes1 = AES.new(static_key, AES.MODE_ECB)
    enc1 = aes1.encrypt(padded)
    aes2 = AES.new(random_key.encode(), AES.MODE_ECB)
    enc2 = aes2.encrypt(enc1)
    return random_key.encode() + enc2


# ─────────────────────────── network ────────────────────────

def login(ip: str, port: int, cam_id: int, username: str, password: str):
    sock = socket.socket()
    sock.connect((ip, port))
    sock.settimeout(5)

    pw = generate_password(password)
    buf = bytearray(256)
    struct.pack_into('<i', buf, 0,  1167)
    struct.pack_into('<I', buf, 4,  1022)
    struct.pack_into('<B', buf, 8,  2)
    struct.pack_into('<I', buf, 9,  1)
    struct.pack_into('<I', buf, 13, cam_id)
    buf[49:49 + len(username)] = username.encode()
    buf[81:81 + 32] = bytes(pw)[:32]
    sock.send(bytes(buf))

    resp = sock.recv(256)
    sock.close()

    result  = struct.unpack_from('<i', resp, 4)[0]
    version = struct.unpack_from('<B', resp, 12)[0]
    ticket  = struct.unpack_from('<I', resp, 13)[0]
    return result, version, ticket


def open_stream(ip: str, port: int, cam_id: int, ticket: int):
    sock = socket.socket()
    sock.connect((ip, port))
    sock.settimeout(10)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    buf2 = bytearray(256)
    struct.pack_into('<i', buf2, 0,  301)
    struct.pack_into('<I', buf2, 4,  cam_id)
    struct.pack_into('<H', buf2, 12, 20)
    struct.pack_into('<I', buf2, 14, ticket)
    struct.pack_into('<I', buf2, 22, 0x1001)   # audio enable flag
    struct.pack_into('<I', buf2, 26, 1)         # hi resolution
    sock.send(bytes(buf2))

    resp2 = sock.recv(412)
    v21 = struct.unpack_from('<i', resp2, 4)[0]

    buf3 = bytearray(256)
    struct.pack_into('<i', buf3, 0, 303)
    struct.pack_into('<i', buf3, 4, v21)
    sock.send(bytes(buf3))

    return sock


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Camera closed connection")
        buf += chunk
    return buf


# ─────────────────────────── capture ────────────────────────

def capture(sock: socket.socket, duration: int) -> list[bytes]:
    """Receive 0x16 audio packets for `duration` seconds.
    Returns list of raw 272-byte payloads."""
    payloads = []
    end_time = time.time() + duration
    print(f"  Recording", end='', flush=True)

    while time.time() < end_time:
        try:
            hdr = recv_exact(sock, 12)
        except (ConnectionError, socket.timeout):
            break

        pkt_type = hdr[0]
        subtype  = hdr[1]
        length   = struct.unpack_from('<H', hdr, 7)[0]

        payload = b''
        if 0 < length <= 65535:
            try:
                payload = recv_exact(sock, length)
            except (ConnectionError, socket.timeout):
                break

        if pkt_type == 0x7f and subtype == 0x16:
            payloads.append(payload)
            if len(payloads) % 50 == 0:
                elapsed = duration - (end_time - time.time())
                print(f"\r  Recording {elapsed:.0f}/{duration}s ({len(payloads)} frames)  ",
                      end='', flush=True)

    print()
    return payloads


# ─────────────────────────── decode ─────────────────────────

def write_ima_wav(blocks: list[bytes], filename: str, sample_rate: int = 8000):
    """Write IMA ADPCM blocks as a proper WAV file any player can open."""
    block_size        = len(blocks[0])
    samples_per_block = (block_size - 4) * 2 + 1
    data_size         = len(blocks) * block_size
    fmt_size          = 20

    with open(filename, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', 4 + 8 + fmt_size + 8 + data_size))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<I', fmt_size))
        f.write(struct.pack('<H', 17))            # IMA ADPCM
        f.write(struct.pack('<H', 1))             # mono
        f.write(struct.pack('<I', sample_rate))
        bytes_per_sec = (sample_rate // samples_per_block) * block_size
        f.write(struct.pack('<I', bytes_per_sec))
        f.write(struct.pack('<H', block_size))    # block align
        f.write(struct.pack('<H', 4))             # bits per sample
        f.write(struct.pack('<H', 2))             # cbSize
        f.write(struct.pack('<H', samples_per_block))
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        for b in blocks:
            f.write(b)


def payloads_to_wav(payloads: list[bytes], out_path: str):
    """Strip 20-byte proprietary header from each payload, keep IMA block."""
    # Payload layout (272 bytes):
    #   0-3   sequence counter
    #   4-5   type (0x16)
    #   6-7   header size (20)
    #   8-11  timestamp
    #   12-15 camera id
    #   16-19 IMA ADPCM header (predictor s16 + step_index u8 + reserved u8)
    #   20-271 IMA nibble data
    # → strip first 16 bytes, keep 256-byte IMA block (header + nibbles)

    FRAME_TOTAL = 272
    HEADER_STRIP = 16
    BLOCK_SIZE = FRAME_TOTAL - HEADER_STRIP  # 256

    blocks = []
    for p in payloads:
        if len(p) < FRAME_TOTAL:
            continue
        block = p[HEADER_STRIP:HEADER_STRIP + BLOCK_SIZE]
        step_index = block[2]
        if 0 <= step_index <= 88:   # sanity check
            blocks.append(block)

    if not blocks:
        print("  No valid audio blocks found.")
        return False

    write_ima_wav(blocks, out_path)
    samples_per_block = (BLOCK_SIZE - 4) * 2 + 1
    duration = len(blocks) * samples_per_block / 8000
    print(f"  Decoded {len(blocks)} blocks → {duration:.1f} seconds")
    return True


# ─────────────────────────── main ───────────────────────────

def main():
    # Load cameras from data.yaml
    if not os.path.exists('data.yaml'):
        print("Error: data.yaml not found. Create it with your camera credentials.")
        print("Format:")
        print("  my-camera:")
        print("    ip: 192.168.1.2")
        print("    cam_id: 123456789")
        print("    user: admin")
        print("    pass: password")
        return

    with open('data.yaml') as f:
        cameras = yaml.safe_load(f)

    if not cameras:
        print("Error: data.yaml is empty.")
        return

    # Select camera
    cam_name = questionary.select(
        "Select a camera:",
        choices=list(cameras.keys())
    ).ask()

    if not cam_name:
        return

    cam = cameras[cam_name]
    ip       = cam['ip']
    cam_id   = int(cam['cam_id'])
    username = cam.get('user', 'admin')
    password = cam['pass']

    # Select duration
    duration_str = questionary.select(
        "Recording duration:",
        choices=["5 seconds", "10 seconds", "30 seconds", "60 seconds", "Custom"]
    ).ask()

    if not duration_str:
        return

    if duration_str == "Custom":
        custom = questionary.text("Enter duration in seconds:").ask()
        try:
            duration = int(custom)
        except (ValueError, TypeError):
            print("Invalid duration.")
            return
    else:
        duration = int(duration_str.split()[0])

    # Output filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_wav = f"{cam_name}_{timestamp}.wav"

    print(f"\nConnecting to {cam_name} ({ip})...")

    # Login
    try:
        result, version, ticket = login(ip, 8800, cam_id, username, password)
    except Exception as e:
        print(f"Login failed: {e}")
        return

    if result not in (1001,):
        print(f"Login rejected (result={result}). Check credentials.")
        return

    print(f"  Logged in. Camera version: {version}, ticket: {ticket}")

    # Open stream
    try:
        sock = open_stream(ip, 8800, cam_id, ticket)
    except Exception as e:
        print(f"Stream failed: {e}")
        return

    # Capture
    try:
        payloads = capture(sock, duration)
    finally:
        sock.close()

    print(f"  Captured {len(payloads)} audio frames")

    if not payloads:
        print("No audio received. Check camera and credentials.")
        return

    # Decode and save
    print(f"  Decoding to {out_wav}...")
    if payloads_to_wav(payloads, out_wav):
        print(f"\nSaved: {out_wav}")
        print("Play with VLC or any media player.")


if __name__ == '__main__':
    main()
