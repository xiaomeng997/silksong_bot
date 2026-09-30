using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;

namespace SsOracle.Progress
{
    /// <summary>
    /// Reads every primitive, enum and string field of PlayerData (~1300, m0 §2.7) into typed shadow arrays,
    /// one chunk at a time, without boxing: each chunk is a DynamicMethod doing plain ldfld/stelem, so a chunk of
    /// 64 fields costs about a microsecond. Falls back to FieldInfo.GetValue (boxing) if IL emission fails.
    /// Integers, bools and enums are stored as long, float/double as double, strings by reference.
    /// </summary>
    internal sealed class PlayerDataScanner
    {
        public enum Kind : byte { Bool, Int, UInt, Enum, Float, Double, String }

        public struct Slot
        {
            public string Name;
            public Kind Kind;
            public int Idx;        // index into the long, double or string arrays
            public Type EnumType;
        }

        private delegate void Reader(PlayerData pd, long[] l, double[] d, string[] s);

        public readonly Slot[] Slots;
        public readonly int ChunkCount;
        public readonly bool Emitted;
        private readonly int[] chunkStart;
        private readonly Reader[] readers;

        // Current read (L, D, S) and last committed values (PL, PD, PS).
        private readonly long[] l, pl;
        private readonly double[] d, pdbl;
        private readonly string[] s, ps;

        public PlayerDataScanner(int chunkSize)
        {
            var fields = new List<FieldInfo>();
            foreach (var f in typeof(PlayerData).GetFields(BindingFlags.Instance | BindingFlags.Public))
            {
                var t = f.FieldType;
                if (t.IsPrimitive || t.IsEnum || t == typeof(string)) fields.Add(f);
            }
            // Declaration order, so a chunk groups related fields and the output reads like the save file.
            fields.Sort((a, b) => a.MetadataToken.CompareTo(b.MetadataToken));

            Slots = new Slot[fields.Count];
            int nl = 0, nd = 0, ns = 0;
            for (var i = 0; i < fields.Count; i++)
            {
                var t = fields[i].FieldType;
                var slot = new Slot { Name = fields[i].Name, Kind = KindOf(t) };
                if (t.IsEnum) slot.EnumType = t;
                switch (slot.Kind)
                {
                    case Kind.Float:
                    case Kind.Double: slot.Idx = nd++; break;
                    case Kind.String: slot.Idx = ns++; break;
                    default: slot.Idx = nl++; break;
                }
                Slots[i] = slot;
            }
            l = new long[nl]; pl = new long[nl];
            d = new double[nd]; pdbl = new double[nd];
            s = new string[ns]; ps = new string[ns];

            ChunkCount = Math.Max(1, (fields.Count + chunkSize - 1) / chunkSize);
            chunkStart = new int[ChunkCount + 1];
            readers = new Reader[ChunkCount];
            Emitted = true;
            for (var c = 0; c < ChunkCount; c++)
            {
                var from = c * chunkSize;
                var to = Math.Min(fields.Count, from + chunkSize);
                chunkStart[c] = from;
                try
                {
                    readers[c] = EmitReader(fields, from, to);
                }
                catch (Exception e)
                {
                    if (Emitted) Core.Plugin.Log.LogWarning("ProgressExporter: IL reader failed, using reflection: " + e.Message);
                    Emitted = false;
                    readers[c] = ReflectionReader(fields, from, to);
                }
            }
            chunkStart[ChunkCount] = fields.Count;
        }

        private static Kind KindOf(Type t)
        {
            if (t == typeof(string)) return Kind.String;
            if (t.IsEnum) return Kind.Enum;
            if (t == typeof(bool)) return Kind.Bool;
            if (t == typeof(float)) return Kind.Float;
            if (t == typeof(double)) return Kind.Double;
            if (t == typeof(ulong) || t == typeof(uint) || t == typeof(ushort) || t == typeof(byte) || t == typeof(char)) return Kind.UInt;
            return Kind.Int;
        }

        private static bool Unsigned(Type t)
        {
            if (t.IsEnum) t = Enum.GetUnderlyingType(t);
            return t == typeof(bool) || t == typeof(byte) || t == typeof(ushort) || t == typeof(char) || t == typeof(uint) || t == typeof(ulong);
        }

        private Reader EmitReader(List<FieldInfo> fields, int from, int to)
        {
            var dm = new DynamicMethod("SsOracle_PlayerDataChunk" + from, typeof(void),
                new[] { typeof(PlayerData), typeof(long[]), typeof(double[]), typeof(string[]) }, typeof(PlayerDataScanner).Module, true);
            var il = dm.GetILGenerator();
            for (var i = from; i < to; i++)
            {
                var f = fields[i];
                var slot = Slots[i];
                switch (slot.Kind)
                {
                    case Kind.Float:
                    case Kind.Double:
                        il.Emit(OpCodes.Ldarg_2);
                        il.Emit(OpCodes.Ldc_I4, slot.Idx);
                        il.Emit(OpCodes.Ldarg_0);
                        il.Emit(OpCodes.Ldfld, f);
                        il.Emit(OpCodes.Conv_R8);
                        il.Emit(OpCodes.Stelem_R8);
                        break;
                    case Kind.String:
                        il.Emit(OpCodes.Ldarg_3);
                        il.Emit(OpCodes.Ldc_I4, slot.Idx);
                        il.Emit(OpCodes.Ldarg_0);
                        il.Emit(OpCodes.Ldfld, f);
                        il.Emit(OpCodes.Stelem_Ref);
                        break;
                    default:
                        il.Emit(OpCodes.Ldarg_1);
                        il.Emit(OpCodes.Ldc_I4, slot.Idx);
                        il.Emit(OpCodes.Ldarg_0);
                        il.Emit(OpCodes.Ldfld, f);
                        var t = f.FieldType.IsEnum ? Enum.GetUnderlyingType(f.FieldType) : f.FieldType;
                        if (t != typeof(long) && t != typeof(ulong)) il.Emit(Unsigned(t) ? OpCodes.Conv_U8 : OpCodes.Conv_I8);
                        il.Emit(OpCodes.Stelem_I8);
                        break;
                }
            }
            il.Emit(OpCodes.Ret);
            return (Reader)dm.CreateDelegate(typeof(Reader));
        }

        private Reader ReflectionReader(List<FieldInfo> fields, int from, int to)
        {
            var fs = fields.GetRange(from, to - from).ToArray();
            var slots = new Slot[fs.Length];
            Array.Copy(Slots, from, slots, 0, fs.Length);
            return (pd, L, D, S) =>
            {
                for (var i = 0; i < fs.Length; i++)
                {
                    var v = fs[i].GetValue(pd);
                    var slot = slots[i];
                    switch (slot.Kind)
                    {
                        case Kind.Float:
                        case Kind.Double: D[slot.Idx] = Convert.ToDouble(v); break;
                        case Kind.String: S[slot.Idx] = (string)v; break;
                        case Kind.Bool: L[slot.Idx] = (bool)v ? 1 : 0; break;
                        case Kind.Enum:
                        case Kind.UInt:
                            L[slot.Idx] = Unsigned(fs[i].FieldType) ? unchecked((long)Convert.ToUInt64(v)) : Convert.ToInt64(v);
                            break;
                        default: L[slot.Idx] = Convert.ToInt64(v); break;
                    }
                }
            };
        }

        /// <summary>
        /// JIT every chunk reader now (about 10 ms for all of them), at plugin load, instead of inside the first
        /// full snapshot. Uses a field-only PlayerData: no constructor runs, nothing in the game sees it.
        /// </summary>
        public void Warm()
        {
            var dummy = (PlayerData)System.Runtime.Serialization.FormatterServices.GetUninitializedObject(typeof(PlayerData));
            for (var c = 0; c < ChunkCount; c++) readers[c](dummy, l, d, s);
            // The diff loop and the writer are JIT-compiled here too (the first ScanChunk otherwise costs ~0.5 ms).
            ScanChunk(dummy, 0, new List<int>());
            var w = new Ipc.MsgPackWriter(256);
            for (var i = 0; i < Slots.Length; i++)
            {
                w.Reset();
                WriteValue(w, i);
            }
            // Nothing is committed: the first full snapshot (ReadAll) sets the baseline.
            Array.Clear(l, 0, l.Length);
            Array.Clear(d, 0, d.Length);
            Array.Clear(s, 0, s.Length);
            Array.Clear(pl, 0, pl.Length);
            Array.Clear(pdbl, 0, pdbl.Length);
            Array.Clear(ps, 0, ps.Length);
        }

        /// <summary>Read one chunk and add the slots whose value differs from the committed one to <paramref name="changed"/>
        /// (committing them).</summary>
        public void ScanChunk(PlayerData pd, int chunk, List<int> changed)
        {
            readers[chunk](pd, l, d, s);
            for (var i = chunkStart[chunk]; i < chunkStart[chunk + 1]; i++)
            {
                var k = Slots[i].Idx;
                bool diff;
                switch (Slots[i].Kind)
                {
                    case Kind.Float:
                    case Kind.Double:
                        diff = BitConverter.DoubleToInt64Bits(d[k]) != BitConverter.DoubleToInt64Bits(pdbl[k]);
                        if (diff) pdbl[k] = d[k];
                        break;
                    case Kind.String:
                        diff = !string.Equals(s[k], ps[k]);
                        if (diff) ps[k] = s[k];
                        break;
                    default:
                        diff = l[k] != pl[k];
                        if (diff) pl[k] = l[k];
                        break;
                }
                if (diff) changed.Add(i);
            }
        }

        /// <summary>Read every field and commit it as the new baseline.</summary>
        public void ReadAll(PlayerData pd)
        {
            for (var c = 0; c < ChunkCount; c++) readers[c](pd, l, d, s);
            Array.Copy(l, pl, l.Length);
            Array.Copy(d, pdbl, d.Length);
            Array.Copy(s, ps, s.Length);
        }

        /// <summary>Write the committed value of slot <paramref name="i"/>. Enums are written by name.</summary>
        public void WriteValue(Ipc.MsgPackWriter w, int i)
        {
            var slot = Slots[i];
            var k = slot.Idx;
            switch (slot.Kind)
            {
                case Kind.Bool: w.Bool(pl[k] != 0); break;
                case Kind.Int: w.Int(pl[k]); break;
                case Kind.UInt: w.UInt(unchecked((ulong)pl[k])); break;
                case Kind.Enum: w.Str(Enum.ToObject(slot.EnumType, pl[k]).ToString()); break;
                case Kind.Float: w.Float((float)pdbl[k]); break;
                case Kind.Double: w.Double(pdbl[k]); break;
                default: w.Str(ps[k]); break;
            }
        }
    }
}
