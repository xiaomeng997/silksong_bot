using System.Collections.Generic;
using HarmonyLib;

namespace SsOracle.SceneDump
{
    /// <summary>
    /// STATE room.battles (M2 W8, Forum): the live state of the room's arena gauntlets. A multi-wave arena is one
    /// BattleScene component that runs its waves itself (1.0.30000 BattleScene.cs: StartWave / DecrementEnemy /
    /// WaveEnd / EndBattle); which wave is running is only in its fields, and the brain could otherwise only guess it
    /// from enemy spawns. Hang_04_boss (the High Halls Forum) has one BattleScene with 14 BattleWaves (scene bundle,
    /// docs/facts/1.0.30000/forum.md). The SceneDumper's walk finds every BattleScene of the room (it has a collider;
    /// SceneDumper.CollectBattle) and registers it here; the list follows the TERRAIN dump's lifecycle exactly like
    /// GateWatch (Begin / Commit / Discard / Invalidate), so it is nil until the room's dump is done.
    /// Each entry: {name: GameObject name, id: instance id (TERRAIN zones.battles[].id), wave: currentWave (index of the
    /// wave started last; 0 before the start), waves: waves.Count, started, completed (private fields: started is
    /// false again once the battle is completed), enemies: currentEnemies (its own count of live enemies, decremented
    /// by HealthManager.Die), to_next: enemiesToNext (the wave ends when enemies drops to it)}. A destroyed component
    /// is written with only name and id. Cost per frame: five field reads per BattleScene, no allocation.
    /// </summary>
    internal static class BattleWatch
    {
        public const int MaxListed = 8;

        private sealed class Entry
        {
            public BattleScene Bs;
            public int Id;
            public string Name;
        }

        private static readonly AccessTools.FieldRef<BattleScene, bool> Started =
            AccessTools.FieldRefAccess<BattleScene, bool>("started");
        private static readonly AccessTools.FieldRef<BattleScene, bool> Completed =
            AccessTools.FieldRefAccess<BattleScene, bool>("completed");

        private static readonly List<Entry> Building = new List<Entry>(MaxListed);
        private static List<Entry> entries = new List<Entry>(MaxListed);
        private static int committed = -1;

        public static void Begin() => Building.Clear();

        public static void Battle(BattleScene bs)
        {
            if (bs == null || Building.Count >= MaxListed) return;
            Building.Add(new Entry { Bs = bs, Id = bs.GetInstanceID(), Name = bs.gameObject.name });
        }

        public static void Commit(int transition)
        {
            entries = new List<Entry>(Building);
            Building.Clear();
            committed = transition;
        }

        public static void Discard() => Building.Clear();

        public static void Invalidate() => committed = -1;

        public static void Write(Ipc.MsgPackWriter w, int transition)
        {
            if (committed < 0 || committed != transition)
            {
                w.Nil();
                return;
            }
            w.ArrayHeader(entries.Count);
            foreach (var e in entries)
            {
                var bs = e.Bs;
                if (bs == null)
                {
                    w.MapHeader(2);
                    w.Key("name"); w.Str(e.Name);
                    w.Key("id"); w.Int(e.Id);
                    continue;
                }
                w.MapHeader(8);
                w.Key("name"); w.Str(e.Name);
                w.Key("id"); w.Int(e.Id);
                w.Key("wave"); w.Int(bs.currentWave);
                w.Key("waves"); w.Int(bs.waves != null ? bs.waves.Count : 0);
                w.Key("started"); w.Bool(Started(bs));
                w.Key("completed"); w.Bool(Completed(bs));
                w.Key("enemies"); w.Int(bs.currentEnemies);
                w.Key("to_next"); w.Int(bs.enemiesToNext);
            }
        }
    }
}
