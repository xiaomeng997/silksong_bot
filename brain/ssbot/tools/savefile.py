"""Read Silksong save files offline (user*.dat, restoreData*.dat, shared.dat).

Format (m0:N33, TeamCherry.SharedUtils.Encryption): a BinaryFormatter-serialized string whose value is
Base64(AES-256-ECB-PKCS7(UTF-8 JSON)) under a fixed key. Read-only on purpose: the bot never writes saves.

  python -m ssbot.tools.savefile <file> [key ...]   print the JSON, or only the given top-level/playerData keys
"""
import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_KEY = b"UKu52ePUBwetZ9wNX88o54dnfKRu0T1l"  # TeamCherry.SharedUtils.Encryption._keyArray
_RECORD_STRING = 0x06  # BinaryFormatter BinaryObjectString record


def _binaryformatter_string(data: bytes) -> str:
    """Extract the single string a BinaryFormatter stream holds (header, then a BinaryObjectString)."""
    i = data.index(bytes([_RECORD_STRING]), 17)  # after SerializationHeaderRecord (17 bytes)
    i += 1 + 4  # record type + object id
    length, shift = 0, 0
    while True:  # 7-bit encoded length prefix
        b = data[i]
        i += 1
        length |= (b & 0x7F) << shift
        if not b & 0x80:
            break
        shift += 7
    return data[i:i + length].decode("utf-8")


def decode_bytes(data: bytes) -> dict:
    if data[:1] == b"{":  # useSaveEncryption off: plain JSON
        return json.loads(data)
    encrypted = base64.b64decode(_binaryformatter_string(data))
    decryptor = Cipher(algorithms.AES(_KEY), modes.ECB()).decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return json.loads((unpadder.update(padded) + unpadder.finalize()).decode("utf-8"))


def decode(path: str | Path) -> dict:
    return decode_bytes(Path(path).read_bytes())


def main(argv: list[str]) -> None:
    obj = decode(argv[0])
    keys = argv[1:]
    if not keys:
        print(json.dumps(obj, ensure_ascii=False, indent=1))
        return
    pd = obj.get("playerData", {}) if isinstance(obj, dict) else {}
    for k in keys:
        print(k, "=", json.dumps(obj.get(k, pd.get(k, "<missing>")), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
