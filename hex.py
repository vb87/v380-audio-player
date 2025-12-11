import struct
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import string
import random

# From com.macrovideo.sdk.media.LoginHelper
v380_key = "macrovideo+*#!^@"


def encrypt(key: str, data: bytes):
    aes = AES.new(  # pyright: ignore[reportUnknownMemberType]
        key.encode(), AES.MODE_ECB
    )
    msg = aes.encrypt(pad(data, 16))
    return msg


class PacketGen:
    def __init__(self, cam_id: int, user: str, passwd: str):
        self.cam_id = cam_id
        salt_chars = list(string.ascii_letters + string.digits)
        salt = "".join([random.choice(salt_chars) for _ in range(16)])
        self.salt_hex = bytes(salt, encoding="ascii").hex()

        encrypted_pass = encrypt(v380_key, passwd.encode())
        self.encrypted_pass = encrypt(salt, encrypted_pass).hex()

        self.cam_hex = struct.pack("<L", cam_id).hex()
        date = "2025-12-08 19:44:29"  # doesn't actually matter when

        self.date_hex = bytes(date, encoding="ascii").hex()
        self.user_hex = bytes(user, encoding="ascii").ljust(32, b"\x00").hex()

    def get_login(self):
        login_hex_str = "8f040000780000001f0a000000"
        login_hex_str += f"{self.cam_hex}{self.date_hex}00000000000000000000000000"
        login_hex_str += f"{self.user_hex}{self.salt_hex}{self.encrypted_pass}"

        return bytes.fromhex(login_hex_str).ljust(512, b"\x00")

    def get_audio_handshake(self, handle_bytes: bytes):
        if len(handle_bytes) != 4:
            raise ValueError("Handle bytes must be length 4")
        # Header code from HSLiveDataV2Transmitter::sendSpeakAudioToDevice
        handshake = bytearray.fromhex(f"79010000{self.cam_hex}").ljust(85, b"\x00")
        handshake[8:12] = handle_bytes
        return handshake

    def get_audio_payload_header(self, packet_sent: int):
        # unsigned char
        seq_byte = struct.pack("B", (packet_sent + 1) % 256)
        # Header code from HSLiveDataV2Transmitter::sendSpeakAudioToDevice
        header_prefix = bytes.fromhex("b40000000100160000000000000001")
        return header_prefix + seq_byte
