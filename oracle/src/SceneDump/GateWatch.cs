using System.Collections.Generic;
using UnityEngine;

namespace SsOracle.SceneDump
{
    /// <summary>
    /// STATE room.gates (M2 cross-module decision 5): the room's terrain solids whose state is not the one the TERRAIN
    /// dump recorded, live. TERRAIN is a snapshot taken when the room is entered, so arena gates that close for a fight
    /// are off in it and walls that go away are on (Bone_05: the "Threaded Bell Gate" pair at x 67.2-69.2 and
    /// 102.0-104.0 is off at entry and closes for the fight, the "Wall" at x 91.7-100.3 is on at entry and gone in the
    /// fight; kinematics review, trial and live runs). Watched solids: every collider under a BattleScene's "gates", every
    /// solid that was off when the dump was taken, and every other dumped solid once it is seen in a state different
    /// from the dump (a round-robin poll of PollPerFrame solids per frame finds those; Bone_05 has 31 solids, so each is
    /// looked at every second frame). Each entry: {name: the collider's GameObject name, id: its instance id (TERRAIN
    /// solids[].id), enabled: Collider2D.enabled and GameObject.activeInHierarchy now, box: [x0, y0, x1, y1] world AABB
    /// of the dumped outline, moved with the transform's position since the dump (rotation and scale are not
    /// followed)}. A consumer applies "enabled" over the TERRAIN solid with that id. nil until the current room's dump
    /// is done (unknown, not "no gates"); [] when nothing is watched.
    /// The list holds MaxListed entries. Battle gates and solids seen changed stay once listed; a solid listed only
    /// because it was off at the dump, and still is, says nothing TERRAIN does not, so a newly changed solid takes its
    /// slot when the list is full (EvictSlot; the evicted one goes back to the poll). Only when every slot holds a
    /// battle gate or a changed solid does a changed solid stay unlisted: room.gates_trunc (Truncated) then turns true
    /// for the rest of the room, and a consumer must treat the state of every unlisted TERRAIN solid as unknown.
    /// Cost per frame: for each watched entry a null check, two flag reads and a transform position; for the poll two
    /// flag reads per solid; no allocation.
    /// </summary>
    internal static class GateWatch
    {
        public const int PollPerFrame = 16;
        public const int MaxListed = 32;

        internal sealed class Entry
        {
            public Collider2D Col;
            public GameObject Go;
            public Transform Tr;
            public int Id;
            public string Name;
            public bool OnAtDump, Battle, Listed, On;
            public bool Changed;           // seen in a state different from the dump since it was (last) listed
            public Vector3 Pos0;
            public float X0, Y0, X1, Y1;   // AABB at the dump
            public float Dx, Dy;           // translation since the dump
        }

        private static readonly List<Entry> Building = new List<Entry>(512);
        private static readonly HashSet<int> BattleIds = new HashSet<int>();
        private static List<Entry> entries = new List<Entry>(512);
        private static readonly List<Entry> Listed = new List<Entry>(MaxListed);
        private static int committed = -1;   // FlowTap transition the committed list belongs to
        private static int cursor;
        private static bool truncated;

        public static int Watched => Listed.Count;

        /// <summary>True once a solid seen in a state different from the dump could not be listed in this room.</summary>
        public static bool Truncated => truncated;

        // ---- dump side (SceneDumper coroutine, main thread) --------------------------------------------------

        public static void Begin()
        {
            Building.Clear();
            BattleIds.Clear();
        }

        public static void Solid(Collider2D col, int id, string name, bool on, float[] box)
        {
            if (col == null || box == null) return;
            var go = col.gameObject;
            var tr = go.transform;
            Building.Add(new Entry
            {
                Col = col, Go = go, Tr = tr, Id = id, Name = name, OnAtDump = on, On = on, Pos0 = tr.position,
                X0 = box[0], Y0 = box[1], X1 = box[2], Y1 = box[3],
            });
        }

        public static void BattleGate(int colliderId) => BattleIds.Add(colliderId);

        public static void Commit(int transition)
        {
            var e = entries;
            entries = new List<Entry>(Building);
            e.Clear();
            Building.Clear();
            Listed.Clear();
            // Battle gates first, so a room with many solids off at the dump cannot crowd them out of MaxListed.
            foreach (var x in entries)
            {
                x.Battle = BattleIds.Contains(x.Id);
                x.Listed = false;
                x.Changed = false;
                if (x.Battle && Listed.Count < MaxListed)
                {
                    x.Listed = true;
                    Listed.Add(x);
                }
            }
            foreach (var x in entries)
            {
                if (x.Listed || !IsWatched(x.Battle, x.OnAtDump, x.OnAtDump) || Listed.Count >= MaxListed) continue;
                x.Listed = true;
                Listed.Add(x);
            }
            BattleIds.Clear();
            committed = transition;
            cursor = 0;
            truncated = false;
        }

        public static void Discard()
        {
            Building.Clear();
            BattleIds.Clear();
        }

        /// <summary>Which solids room.gates lists: battle gates, solids off in the dump, solids seen changed since.</summary>
        public static bool IsWatched(bool battle, bool onAtDump, bool onNow) => battle || !onAtDump || onNow != onAtDump;

        /// <summary>
        /// The slot a newly changed solid takes in a full list: the first entry that is neither a battle gate nor a
        /// solid seen changed and whose state is still the dump's (pure; oracle/tests/EntitiesCheck). -1 when none.
        /// </summary>
        public static int EvictSlot(List<Entry> listed)
        {
            for (var i = 0; i < listed.Count; i++)
            {
                var e = listed[i];
                if (!e.Battle && !e.Changed && e.On == e.OnAtDump) return i;
            }
            return -1;
        }

        /// <summary>
        /// Lists a polled solid whose state differs from the dump (pure list logic; EntitiesCheck): appended while there
        /// is room, else in an evictable slot, else left out and the list marked truncated. Returns whether it was listed.
        /// </summary>
        public static bool Admit(List<Entry> listed, Entry e, ref bool overflow)
        {
            if (listed.Count < MaxListed)
            {
                listed.Add(e);
            }
            else
            {
                var slot = EvictSlot(listed);
                if (slot < 0)
                {
                    overflow = true;
                    return false;
                }
                listed[slot].Listed = false;
                listed[slot] = e;
            }
            e.Listed = true;
            return true;
        }

        // ---- per frame (RoomExporter) ------------------------------------------------------------------------

        private static bool IsOn(Entry e) => e.Col != null && e.Col.enabled && e.Go.activeInHierarchy;

        private static int errorsLogged;

        private static void Poll()
        {
            for (var i = 0; i < Listed.Count; i++)
            {
                var e = Listed[i];
                e.On = IsOn(e);
                if (e.On != e.OnAtDump) e.Changed = true;
                if (e.Tr != null)
                {
                    var p = e.Tr.position;
                    e.Dx = p.x - e.Pos0.x;
                    e.Dy = p.y - e.Pos0.y;
                }
            }
            var n = entries.Count;
            for (var k = 0; k < PollPerFrame && k < n; k++)
            {
                if (cursor >= n) cursor = 0;
                var e = entries[cursor++];
                if (e.Listed) continue;
                var on = IsOn(e);
                if (!IsWatched(e.Battle, e.OnAtDump, on)) continue;
                // A full list takes only a solid whose state differs from the dump (an unchanged off-at-dump solid
                // adds nothing to TERRAIN); the poll keeps looking at the others.
                if (Listed.Count >= MaxListed && on == e.OnAtDump) continue;
                e.On = on;
                e.Changed = on != e.OnAtDump;
                Admit(Listed, e, ref truncated);
            }
        }

        /// <summary>room.gates_trunc: Truncated for the current room's committed list, nil while room.gates is nil.</summary>
        public static void WriteTruncated(Ipc.MsgPackWriter w, int transition)
        {
            if (committed != transition) w.Nil();
            else w.Bool(truncated);
        }

        public static void Write(Ipc.MsgPackWriter w, int transition)
        {
            if (committed != transition)
            {
                w.Nil();
                return;
            }
            // Unity first, then the bytes: a destroyed object can never leave a half-written value behind.
            try
            {
                Poll();
            }
            catch (System.Exception ex)
            {
                if (errorsLogged++ < 5) Core.Plugin.Log.LogWarning("room.gates: " + ex.GetType().Name + ": " + ex.Message);
                w.Nil();
                return;
            }
            w.ArrayHeader(Listed.Count);
            foreach (var e in Listed)
            {
                w.MapHeader(4);
                w.Key("name"); w.Str(e.Name);
                w.Key("id"); w.Int(e.Id);
                w.Key("enabled"); w.Bool(e.On);
                w.Key("box");
                w.ArrayHeader(4);
                w.Float(e.X0 + e.Dx); w.Float(e.Y0 + e.Dy); w.Float(e.X1 + e.Dx); w.Float(e.Y1 + e.Dy);
            }
        }
    }
}
