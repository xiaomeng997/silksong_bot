"""Oracle IPC v1 framing (DESIGN §4.6), mirror of oracle/src/Ipc/Protocol.cs.

u32 length (bytes after this field) | u8 msg_type | u8 schema_ver | u16 flags | u32 seq | msgpack payload
"""
import struct
from enum import IntEnum

BASE_PORT = 47017
SCHEMA_VERSION = 1
HEADER = struct.Struct("<IBBHI")  # length, type, schema, flags, seq
MAX_MESSAGE = 16 << 20

# Bit order of the ACTION `buttons` mask; must equal KeyboardInjector.ButtonNames (checked against HELLO).
BUTTONS = (
    "jump", "attack", "dash", "bind", "clawline", "needolin", "quickcast", "taunt",
    "inventory", "map", "tools", "journal", "quests", "quickmap", "pause", "enter",
    "paneleft", "paneright", "up", "down", "left", "right",
)
BIT = {name: i for i, name in enumerate(BUTTONS)}

# ACTION flags (the optional 5th element; ActionScheduler.FlagExclusive). EXCLUSIVE: from the ACTION's frame no key
# outside its mask is down (others released at once, below their minimum press if need be, queued edges dropped):
# the pause loop and quit sequence send it so no planner key reaches the pause menu. HELLO "action_flags" lists the
# flags an oracle knows; an older oracle reads four elements and ignores the fifth.
ACTION_EXCLUSIVE = 1


class MsgType(IntEnum):
    HELLO = 1
    STATE = 2
    TERRAIN = 3
    PROGRESS = 4
    ACTION = 5
    RPC_REQ = 6
    RPC_RES = 7


def port(instance: int = 0) -> int:
    return BASE_PORT + instance


def mask(*names: str) -> int:
    m = 0
    for n in names:
        m |= 1 << BIT[n]
    return m


def names(m: int) -> list[str]:
    return [n for i, n in enumerate(BUTTONS) if m & (1 << i)]


def encode(msg_type: MsgType, seq: int, payload: bytes, flags: int = 0) -> bytes:
    return HEADER.pack(HEADER.size - 4 + len(payload), msg_type, SCHEMA_VERSION, flags, seq & 0xFFFFFFFF) + payload
