import audioop
import queue
import socket
import struct
import threading
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from Crypto.Cipher import AES
from questionary import Choice, checkbox, select

from hex import PacketGen
from storage import Storage

if TYPE_CHECKING:
    from Crypto.Cipher._mode_ecb import EcbMode

PORTNUM = 8800

# From libhsMediaLibrary.so -> HSLiveDataV2Transmitter::updateLoginHandle
MAGIC_1 = 0x618123462C14795C
MAGIC_2 = 0x82800DF0


class Camera:
    def __init__(self):
        self.connection_alive = True

    def generate_magic_key(self, handle_bytes: bytes):
        # pad to 16-bytes
        key = bytearray(handle_bytes.ljust(16, b"\x00")[:16])

        # unsigned long long (8 bytes) (little endian)
        key[4:12] = struct.pack("<Q", MAGIC_1)

        # unsigned int (4 bytes) (little endian)
        key[12:16] = struct.pack("<I", MAGIC_2)

        return bytes(key)

    def listen_to_camera(self, sock: socket.socket):
        "Continuously receive data from socket until server closes connection"

        while self.connection_alive:
            try:
                data = sock.recv(1024)
                print("RECEIVED:", data.hex())
                if not data:
                    print("\n[!] Connection closed by camera.")
                    self.connection_alive = False
                    break
            except Exception:
                break

    def precompute_payloads(
        self, wav_path: str, cipher: Optional["EcbMode"], encrypt: bool = True
    ) -> tuple[list[bytes], float]:
        """
        Reads WAV, Encodes to ADPCM, Swaps Nibbles, Adds Internal Header, and Encrypts.
        Returns a list of ENCRYPTED PAYLOADS (excluding the transport header).
        """
        print("[*] Pre-computing and encrypting audio...")
        payloads: list[bytes] = []

        try:
            wav = wave.open(wav_path, "rb")
        except Exception:
            print("Error: input.wav not found")
            return [], 0

        current_index = 0

        # we want 252 bytes of data, it's in 2-byte format,
        # and there's one extra byte for the predictor
        samples_per_chunk = 252 * 2 + 1

        # 8khz sample rate
        packet_duration = samples_per_chunk / 8000.0

        state = None

        while True:
            raw_bytes = wav.readframes(samples_per_chunk)
            if len(raw_bytes) < samples_per_chunk * 2:
                break

            # signed short (little endian)
            # take first 16-bit int and use as predictor
            val_pred = struct.unpack("<h", raw_bytes[:2])[0]
            state = (val_pred, current_index)

            # width = 2 -> every sample is in 2-byte format i.e. 16-bits wide.
            # we also trim the predictor byte, works WITH the predictor byte included
            # but both produce the same output
            adpcm_data, new_state = audioop.lin2adpcm(raw_bytes[2:], 2, state)

            # Clamp index to 0-88 just in case
            current_index = new_state[1]
            current_index = max(0, min(88, current_index))

            # nibble swap (0xab -> 0xba)
            swapped_adpcm = bytearray()
            for byte in adpcm_data:
                swapped_adpcm.append(((byte & 0x0F) << 4) | ((byte & 0xF0) >> 4))

            # little-endian: signed short + 2 signed chars
            internal_header = struct.pack("<hbb", val_pred, current_index, 0)

            # 4-byte header + 252 bytes audio = 256-byte payload
            raw_payload = internal_header + swapped_adpcm[:252]

            if len(raw_payload) < 256:
                raw_payload += b"\x00" * (256 - len(raw_payload))

            encrypted_payload = (
                cipher.encrypt(raw_payload)
                if encrypt and cipher is not None
                else raw_payload
            )

            payloads.append(encrypted_payload)

        print(f"[*] Ready. Loaded {len(payloads)} chunks.")
        return payloads, packet_duration

    def play_audio(self, cam_info: dict[str, Any], audio_file: Path):
        cam_id = cam_info.get("cam_id")
        cam_ip_addr = cam_info.get("ip")
        user = cam_info.get("user")
        passwd = cam_info.get("pass")

        if cam_id is None:
            raise ValueError("One of the cameras is missing 'cam_id'")

        if cam_ip_addr is None:
            raise ValueError("One of the cameras is missing 'cam_ip_addr'")

        if user is None:
            raise ValueError("One of the cameras is missing 'user'")

        if passwd is None:
            raise ValueError("One of the cameras is missing 'passwd'")

        packet_gen = PacketGen(cam_id, user, passwd)

        print("[1] Connecting to fetch Handle...")
        socket_1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            socket_1.connect((cam_ip_addr, PORTNUM))
            socket_1.send(packet_gen.get_login())
            response = socket_1.recv(1024)
            print("RECEIVED:", response.hex())
            socket_1.close()
        except Exception as e:
            print(f"Error connecting: {e}")
            return

        if not response.startswith(b"\x90\x04"):
            print(f"Error: Expected 90 04, got {response.hex()[:10]}")
            return

        handle_id_bytes = response[13:17]
        version = response[12]
        print(f"CAMERA VERSION: {version}")
        # From HSLiveDataV2Transmitter::updateAesKey
        encrypt_data = True if version > 30 else False

        self.logger.info(f"Handle: {handle_id_bytes.hex()}")

        aes_key = None
        cipher = None
        if encrypt_data:
            aes_key = self.generate_magic_key(handle_id_bytes)
            print(f"AES Key: {aes_key.hex()}")
            cipher = AES.new(  # pyright: ignore[reportUnknownMemberType]
                aes_key, AES.MODE_ECB
            )
        encrypted_chunks, packet_duration = self.precompute_payloads(
            str(audio_file.resolve()), cipher, encrypt=encrypt_data
        )

        if not encrypted_chunks:
            print("No audio packets generated.")
            return

        print("[2] Connecting to Stream Audio...")
        socket_2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_2.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            socket_2.connect((cam_ip_addr, PORTNUM))
        except Exception as e:
            print(f"Stream connect failed: {e}")
            return

        threading.Thread(
            target=self.listen_to_camera, args=(socket_2,), daemon=True
        ).start()

        handshake = packet_gen.get_audio_handshake(handle_id_bytes)
        handshake[8:12] = handle_id_bytes

        print("[>] Sending Audio Handshake...")
        socket_2.send(handshake)

        time.sleep(0.5)

        if not self.connection_alive:
            print("[!] Camera rejected handshake.")
            return

        print(
            f"[TX] Streaming Loop Started (Duration: {packet_duration}s per chunk)..."
        )

        try:
            start_time = time.time()

            total_packets_sent = 0
            audio_index = 0
            total_chunks = len(encrypted_chunks)

            while self.connection_alive:
                current_payload = encrypted_chunks[audio_index]

                header = packet_gen.get_audio_payload_header(total_packets_sent)

                # 16-byte header + 256-byte data = 272-byte payload
                packet = header + current_payload

                socket_2.send(packet)

                total_packets_sent += 1
                audio_index = (audio_index + 1) % total_chunks

                target_time = start_time + (total_packets_sent * packet_duration)
                sleep_duration = target_time - time.time()

                if sleep_duration > 0:
                    time.sleep(sleep_duration)
                else:
                    pass

        except KeyboardInterrupt:
            print("Stopping...")

        print("Done sending.")
        time.sleep(1)
        socket_2.close()


def thread_wrapper(
    target_func: Callable[[Any], None],
    args: tuple[Any],
    err_queue: queue.Queue[Exception],
    cam_name: str,
):
    try:
        target_func(*args)
    except Exception as e:
        e.camera_name = cam_name  # pyright: ignore[reportAttributeAccessIssue]
        err_queue.put(e)


def main():
    storage = Storage()
    cams = storage.load()
    if cams is None:
        print("data.yaml is empty. Please fill it up first.")
        return
    choices: Optional[list[str]] = checkbox("Select a camera:", choices=cams).ask()
    if not choices:
        return

    audio_folder = Path("audio")
    audio_folder.mkdir(exist_ok=True)
    files = [Choice(x.name, x) for x in audio_folder.glob("*.wav")]
    input_wav: Optional[Path] = select("Select an audio file:", files).ask()
    if input_wav is None:
        return
    error_queue: queue.Queue[Exception] = queue.Queue()
    threads: list[threading.Thread] = []

    print(f"Streams started on {len(choices)} cameras. Press Ctrl+C to stop.")

    for c in choices:
        cam_obj = Camera(c)
        url = cams.get(c)

        t = threading.Thread(
            target=thread_wrapper,
            args=(cam_obj.play_audio, (url, input_wav), error_queue, c),
        )

        t.daemon = True
        t.start()
        threads.append(t)

    try:
        while True:
            if not any(t.is_alive() for t in threads) and error_queue.empty():
                print("All audio streams finished.")
                break

            try:
                exc = error_queue.get_nowait()

                name = getattr(exc, "camera_name", "Unknown")
                print(f"Error on camera '{name}': {exc}")

                raise exc
            except queue.Empty:
                pass

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    main()
