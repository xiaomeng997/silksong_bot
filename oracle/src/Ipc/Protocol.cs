using System;

namespace SsOracle.Ipc
{
    /// <summary>
    /// Oracle IPC v1 (DESIGN §4.6). TCP 127.0.0.1:(47017 + instance), TCP_NODELAY, little-endian framing:
    ///   u32 length (bytes after this field) | u8 msg_type | u8 schema_ver | u16 flags | u32 seq | msgpack payload
    /// flags bit0 = zstd (never set by the oracle; the brain compresses when recording).
    /// </summary>
    internal static class Protocol
    {
        public const int BasePort = 47017;
        public const byte SchemaVersion = 1;
        public const int HeaderBytes = 8;             // after the length field
        public const int MaxMessageBytes = 16 << 20;

        public enum MsgType : byte
        {
            Hello = 1,     // both directions, once per connection
            State = 2,     // oracle -> brain, every frame (FrameLabel)
            Terrain = 3,   // oracle -> brain, per scene / variant
            Progress = 4,  // oracle -> brain, on change, <= 2 Hz
            Action = 5,    // brain -> oracle, [target_frame u64, buttons u32, hold_frames u8, ack_seq u32]
            RpcReq = 6,    // brain -> oracle, {id, name, args}
            RpcRes = 7,    // oracle -> brain, {id, ok, result | error}
        }

        public static int Port(string instance) =>
            BasePort + (int.TryParse(instance, out var n) ? n : 0);

        /// <summary>Writes the 12-byte frame prefix into dst[0..12).</summary>
        public static void WritePrefix(byte[] dst, int payloadLength, MsgType type, uint seq, ushort flags = 0)
        {
            var length = (uint)(HeaderBytes + payloadLength);
            dst[0] = (byte)length; dst[1] = (byte)(length >> 8); dst[2] = (byte)(length >> 16); dst[3] = (byte)(length >> 24);
            dst[4] = (byte)type;
            dst[5] = SchemaVersion;
            dst[6] = (byte)flags; dst[7] = (byte)(flags >> 8);
            dst[8] = (byte)seq; dst[9] = (byte)(seq >> 8); dst[10] = (byte)(seq >> 16); dst[11] = (byte)(seq >> 24);
        }

        /// <summary>Wraps a payload into a complete frame.</summary>
        public static byte[] Frame(MsgType type, uint seq, byte[] payload, int payloadLength)
        {
            var frame = new byte[4 + HeaderBytes + payloadLength];
            WritePrefix(frame, payloadLength, type, seq);
            Buffer.BlockCopy(payload, 0, frame, 4 + HeaderBytes, payloadLength);
            return frame;
        }
    }
}
