using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;

namespace SsOracle.Hero
{
    /// <summary>
    /// HeroControllerStates as a bitset (DESIGN §3.1.2 "cState[92] + 4 int"). The public bool fields are resolved
    /// once by reflection in declaration (metadata-token) order: bit (i % 64) of word (i / 64) is bool field i.
    /// The brain reads the names from RPC "schema.cstate" instead of hard-coding the order, so a field added by a
    /// game update cannot silently shift every bit. FieldRef delegates keep the per-frame read at ~1 us for 92
    /// fields without boxing (FieldInfo.GetValue would allocate 92 objects per frame).
    /// </summary>
    internal static class CStateSchema
    {
        public const int ExpectedBools = 92;
        public const int ExpectedInts = 4;

        public static string[] BoolNames { get; private set; } = new string[0];
        public static string[] IntNames { get; private set; } = new string[0];
        public static int Words { get; private set; }
        public static bool Ready { get; private set; }

        private static AccessTools.FieldRef<HeroControllerStates, bool>[] bools;
        private static AccessTools.FieldRef<HeroControllerStates, int>[] ints;

        /// <summary>Private: Invulnerable = invulnerable || invulnerableCount > 0 (m0 §2.7); exported separately.</summary>
        public static readonly AccessTools.FieldRef<HeroControllerStates, int> InvulnerableCount =
            Refs.Field<HeroControllerStates, int>("invulnerableCount");

        public static void Init()
        {
            var fields = new List<FieldInfo>(typeof(HeroControllerStates).GetFields(BindingFlags.Instance | BindingFlags.Public));
            fields.Sort((a, b) => a.MetadataToken.CompareTo(b.MetadataToken));
            var boolNames = new List<string>();
            var intNames = new List<string>();
            var boolRefs = new List<AccessTools.FieldRef<HeroControllerStates, bool>>();
            var intRefs = new List<AccessTools.FieldRef<HeroControllerStates, int>>();
            foreach (var f in fields)
            {
                if (f.FieldType == typeof(bool))
                {
                    boolNames.Add(f.Name);
                    boolRefs.Add(AccessTools.FieldRefAccess<HeroControllerStates, bool>(f));
                }
                else if (f.FieldType == typeof(int))
                {
                    intNames.Add(f.Name);
                    intRefs.Add(AccessTools.FieldRefAccess<HeroControllerStates, int>(f));
                }
            }
            BoolNames = boolNames.ToArray();
            IntNames = intNames.ToArray();
            bools = boolRefs.ToArray();
            ints = intRefs.ToArray();
            Words = (bools.Length + 63) / 64;
            Ready = true;
            if (bools.Length != ExpectedBools || ints.Length != ExpectedInts)
                Core.Plugin.Log.LogWarning($"HeroControllerStates has {bools.Length} bools / {ints.Length} ints " +
                                           $"(expected {ExpectedBools}/{ExpectedInts}); brain must use schema.cstate");
        }

        /// <summary>Writes the bool fields as an array of Words uint64 values.</summary>
        public static void WriteBits(Ipc.MsgPackWriter w, HeroControllerStates cs)
        {
            w.ArrayHeader(Words);
            ulong word = 0;
            var n = bools.Length;
            for (var i = 0; i < n; i++)
            {
                if (bools[i](cs)) word |= 1UL << (i & 63);
                if ((i & 63) == 63 || i == n - 1)
                {
                    w.UInt(word);
                    word = 0;
                }
            }
        }

        public static void WriteInts(Ipc.MsgPackWriter w, HeroControllerStates cs)
        {
            w.ArrayHeader(ints.Length);
            for (var i = 0; i < ints.Length; i++) w.Int(ints[i](cs));
        }

        /// <summary>RPC "schema.cstate": the order the per-frame bitset and int array use.</summary>
        public static object Describe()
        {
            if (!Ready) throw new InvalidOperationException("cState schema not initialised");
            return new Dictionary<string, object>
            {
                ["bools"] = BoolNames,
                ["ints"] = IntNames,
                ["words"] = Words,
                ["bit_order"] = "bit (i % 64) of word (i / 64) = bools[i]",
            };
        }
    }
}
