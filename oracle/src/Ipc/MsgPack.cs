using System;
using System.Collections.Generic;
using System.Text;

namespace SsOracle.Ipc
{
    /// <summary>
    /// Minimal MessagePack writer (the subset the oracle emits: nil, bool, ints, float32/64, str, bin, array, map).
    /// Reuses one growable buffer; not thread-safe. Keeps us free of MessagePack-CSharp and its dependencies
    /// inside Unity's Mono (DESIGN §3.1.1 IPC: hand-written only as far as needed).
    /// </summary>
    internal sealed class MsgPackWriter
    {
        private byte[] buf;
        private int pos;

        public MsgPackWriter(int capacity = 32 * 1024) => buf = new byte[capacity];

        public int Length => pos;
        public byte[] Buffer => buf;
        public void Reset() => pos = 0;

        public byte[] ToArray()
        {
            var copy = new byte[pos];
            System.Buffer.BlockCopy(buf, 0, copy, 0, pos);
            return copy;
        }

        private void Ensure(int n)
        {
            if (pos + n <= buf.Length) return;
            var next = new byte[Math.Max(buf.Length * 2, pos + n)];
            System.Buffer.BlockCopy(buf, 0, next, 0, pos);
            buf = next;
        }

        private void Byte(byte b) { Ensure(1); buf[pos++] = b; }

        private void BigEndian(ulong v, int bytes)
        {
            Ensure(bytes);
            for (var i = bytes - 1; i >= 0; i--)
                buf[pos++] = (byte)(v >> (8 * i));
        }

        public void Nil() => Byte(0xc0);
        public void Bool(bool v) => Byte(v ? (byte)0xc3 : (byte)0xc2);

        public void Int(long v)
        {
            if (v >= 0) { UInt((ulong)v); return; }
            if (v >= -32) { Byte((byte)(0xe0 | (v + 32))); return; }
            if (v >= sbyte.MinValue) { Byte(0xd0); BigEndian((ulong)(byte)(sbyte)v, 1); return; }
            if (v >= short.MinValue) { Byte(0xd1); BigEndian((ulong)(ushort)(short)v, 2); return; }
            if (v >= int.MinValue) { Byte(0xd2); BigEndian((uint)(int)v, 4); return; }
            Byte(0xd3); BigEndian((ulong)v, 8);
        }

        public void UInt(ulong v)
        {
            if (v < 128) { Byte((byte)v); return; }
            if (v <= byte.MaxValue) { Byte(0xcc); BigEndian(v, 1); return; }
            if (v <= ushort.MaxValue) { Byte(0xcd); BigEndian(v, 2); return; }
            if (v <= uint.MaxValue) { Byte(0xce); BigEndian(v, 4); return; }
            Byte(0xcf); BigEndian(v, 8);
        }

        public unsafe void Float(float v)
        {
            Byte(0xca);
            BigEndian(*(uint*)&v, 4);
        }

        public unsafe void Double(double v)
        {
            Byte(0xcb);
            BigEndian(*(ulong*)&v, 8);
        }

        public void Str(string s)
        {
            if (s == null) { Nil(); return; }
            var n = Encoding.UTF8.GetByteCount(s);
            if (n < 32) Byte((byte)(0xa0 | n));
            else if (n <= byte.MaxValue) { Byte(0xd9); BigEndian((ulong)n, 1); }
            else if (n <= ushort.MaxValue) { Byte(0xda); BigEndian((ulong)n, 2); }
            else { Byte(0xdb); BigEndian((ulong)n, 4); }
            Ensure(n);
            pos += Encoding.UTF8.GetBytes(s, 0, s.Length, buf, pos);
        }

        public void Bin(byte[] data, int offset, int count)
        {
            if (count <= byte.MaxValue) { Byte(0xc4); BigEndian((ulong)count, 1); }
            else if (count <= ushort.MaxValue) { Byte(0xc5); BigEndian((ulong)count, 2); }
            else { Byte(0xc6); BigEndian((ulong)count, 4); }
            Ensure(count);
            System.Buffer.BlockCopy(data, offset, buf, pos, count);
            pos += count;
        }

        public void ArrayHeader(int n)
        {
            if (n < 16) Byte((byte)(0x90 | n));
            else if (n <= ushort.MaxValue) { Byte(0xdc); BigEndian((ulong)n, 2); }
            else { Byte(0xdd); BigEndian((ulong)n, 4); }
        }

        public void MapHeader(int n)
        {
            if (n < 16) Byte((byte)(0x80 | n));
            else if (n <= ushort.MaxValue) { Byte(0xde); BigEndian((ulong)n, 2); }
            else { Byte(0xdf); BigEndian((ulong)n, 4); }
        }

        /// <summary>Reserve a 3-byte map16 header now and patch the count later (for maps built incrementally).</summary>
        public int BeginMap16()
        {
            Byte(0xde);
            var at = pos;
            BigEndian(0, 2);
            return at;
        }

        public void EndMap16(int at, int count)
        {
            buf[at] = (byte)(count >> 8);
            buf[at + 1] = (byte)count;
        }

        /// <summary>Same as BeginMap16 for arrays.</summary>
        public int BeginArray16()
        {
            Byte(0xdc);
            var at = pos;
            BigEndian(0, 2);
            return at;
        }

        public void EndArray16(int at, int count) => EndMap16(at, count);

        // Convenience for key/value pairs in maps.
        public void Key(string k) => Str(k);
        public void Vec2(float x, float y) { ArrayHeader(2); Float(x); Float(y); }
        public void Vec3(float x, float y, float z) { ArrayHeader(3); Float(x); Float(y); Float(z); }
    }

    /// <summary>Minimal MessagePack reader for the small messages the brain sends (ACTION, RPC_REQ, HELLO).</summary>
    internal sealed class MsgPackReader
    {
        private readonly byte[] buf;
        private int pos;
        private readonly int end;

        public MsgPackReader(byte[] data, int offset, int count)
        {
            buf = data;
            pos = offset;
            end = offset + count;
        }

        private byte Next()
        {
            if (pos >= end) throw new FormatException("msgpack: unexpected end");
            return buf[pos++];
        }

        private ulong BigEndian(int bytes)
        {
            ulong v = 0;
            for (var i = 0; i < bytes; i++) v = (v << 8) | Next();
            return v;
        }

        /// <summary>Read any value as a plain .NET object: null, bool, long, ulong, double, string, byte[], List, Dictionary.</summary>
        public unsafe object Read()
        {
            var b = Next();
            if (b <= 0x7f) return (long)b;
            if (b >= 0xe0) return (long)(sbyte)b;
            if ((b & 0xf0) == 0x80) return ReadMap(b & 0x0f);
            if ((b & 0xf0) == 0x90) return ReadArray(b & 0x0f);
            if ((b & 0xe0) == 0xa0) return ReadStr(b & 0x1f);
            switch (b)
            {
                case 0xc0: return null;
                case 0xc2: return false;
                case 0xc3: return true;
                case 0xc4: return ReadBin((int)BigEndian(1));
                case 0xc5: return ReadBin((int)BigEndian(2));
                case 0xc6: return ReadBin((int)BigEndian(4));
                case 0xca: { var u = (uint)BigEndian(4); return (double)*(float*)&u; }
                case 0xcb: { var u = BigEndian(8); return *(double*)&u; }
                case 0xcc: return (long)BigEndian(1);
                case 0xcd: return (long)BigEndian(2);
                case 0xce: return (long)BigEndian(4);
                case 0xcf: return BigEndian(8);
                case 0xd0: return (long)(sbyte)BigEndian(1);
                case 0xd1: return (long)(short)BigEndian(2);
                case 0xd2: return (long)(int)BigEndian(4);
                case 0xd3: return (long)BigEndian(8);
                case 0xd9: return ReadStr((int)BigEndian(1));
                case 0xda: return ReadStr((int)BigEndian(2));
                case 0xdb: return ReadStr((int)BigEndian(4));
                case 0xdc: return ReadArray((int)BigEndian(2));
                case 0xdd: return ReadArray((int)BigEndian(4));
                case 0xde: return ReadMap((int)BigEndian(2));
                case 0xdf: return ReadMap((int)BigEndian(4));
                default: throw new FormatException($"msgpack: unsupported type 0x{b:x2}");
            }
        }

        private string ReadStr(int n)
        {
            if (pos + n > end) throw new FormatException("msgpack: string past end");
            var s = Encoding.UTF8.GetString(buf, pos, n);
            pos += n;
            return s;
        }

        private byte[] ReadBin(int n)
        {
            if (pos + n > end) throw new FormatException("msgpack: bin past end");
            var b = new byte[n];
            System.Buffer.BlockCopy(buf, pos, b, 0, n);
            pos += n;
            return b;
        }

        private List<object> ReadArray(int n)
        {
            var list = new List<object>(n);
            for (var i = 0; i < n; i++) list.Add(Read());
            return list;
        }

        private Dictionary<string, object> ReadMap(int n)
        {
            var map = new Dictionary<string, object>(n);
            for (var i = 0; i < n; i++)
            {
                var k = Read();
                map[Convert.ToString(k)] = Read();
            }
            return map;
        }
    }
}
