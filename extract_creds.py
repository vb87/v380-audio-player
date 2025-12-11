# Encrypted password and username are delimited by 0.
from pathlib import Path
from Crypto.Cipher import AES
from questionary import path as q_path


def count(packet: bytes):
    counter = 0
    for b in packet:
        if b != 0:
            counter += 1
        else:
            return counter


def decrypt(key: str, data: bytes):
    aes = AES.new(  # pyright: ignore[reportUnknownMemberType]
        key.encode(), AES.MODE_ECB
    )

    def unpad(date: bytes):
        return date[0 : -date[-1]]

    msg = aes.decrypt(data)
    print("\nDecrypting with key (utf-8): \t" + key + f"(Len: {len(key)})")
    print("Decrypting data(hex):\t\t" + data.hex() + f"(Len: {len(data)})")
    print(
        "Decrypted data(hex):  \t\t"
        + unpad(msg).hex()
        + f"(Len: {len(unpad(msg))})"
        + "\n"
    )
    return unpad(msg)


def decryptPacket(packet: bytes):

    randomKey2: str = packet[81:97].decode("utf-8")

    username_length = count(packet[49:])
    if username_length is None:
        raise ValueError("Inavalid packet")
    username = packet[49 : 49 + username_length].decode("utf-8")

    orig_encrypt_length = count(packet[97:])
    if orig_encrypt_length is None:
        raise ValueError("Inavalid packet")
    orig_encrypt = packet[97 : 97 + orig_encrypt_length]

    decrypted = decrypt(randomKey2, orig_encrypt)

    finalDecrypted = decrypt("macrovideo+*#!^@", decrypted).decode("utf-8")

    result = {"username": username, "password": finalDecrypted}
    return result, randomKey2, orig_encrypt


def main():
    while True:
        while True:
            path = q_path("Enter path to binary file (content starts with 8F 04)").ask()
            if path is None:
                return
            resolved_path = Path(path.strip("'\""))
            if resolved_path.exists() and resolved_path.is_file():
                break
            print("It should be a file!")
        with resolved_path.open("rb") as f:
            file_bytes = f.read()
        if file_bytes.startswith(b"\x8f\x04"):
            break
        print("Invalid file!")
    data, _, _ = decryptPacket(file_bytes)
    print(f"User: {data.get('username')}")
    print(f"Pass: {data.get('password')}")


if __name__ == "__main__":
    main()
