using System;
using System.Collections.Generic;
using System.Text;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Crest
{
    /// <summary>
    /// Probe P17 (DESIGN §5 P17; docs/research/crests.md §5): runtime dumps of the crests, the HeroControllerConfig each
    /// one uses, the hero's attack objects and the Global Gameplay Settings, plus the training-only crest switch that lets
    /// a probe compare crests on one save. RPCs (all on the main thread, never per frame):
    /// <list type="bullet">
    /// <item>crest.dump: every ToolCrest, its slots and saved equips, every config group of the hero (CrestDump).</item>
    /// <item>slash.dump {all_groups=false}: the attack objects of the current config group with their DamageEnemies
    /// fields and collider outlines (SlashDump).</item>
    /// <item>gameplay.dump: crest and tool numbers from Global Gameplay Settings (GameplayDump).</item>
    /// <item>crest.equip {name, unlock=false, force=false} | {restore: true}: TRAIN probe tool (CrestEquip).</item>
    /// </list>
    /// The dumps only read. The Hunter combo meter (STATE hero.hunter_meter, event "hunter_meter") lives with the other
    /// taps in Events.HunterMeterTap.
    /// </summary>
    internal static class CrestModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            Ipc.Rpc.Register("crest.dump", CrestDump.Dump);
            Ipc.Rpc.Register("slash.dump", SlashDump.Dump);
            Ipc.Rpc.Register("gameplay.dump", GameplayDump.Dump);
            Ipc.Rpc.Register("crest.equip", CrestEquip.Equip);
        }

        // ---- shared helpers ----------------------------------------------------------------------------------------

        /// <summary>GameManager._instance.playerData (never PlayerData.instance, which creates one when missing).</summary>
        public static PlayerData Pd()
        {
            var gm = GameManager._instance;
            return gm != null ? gm.playerData : null;
        }

        public static PlayerData RequirePd()
        {
            var pd = Pd();
            if (pd == null) throw new InvalidOperationException("not in a game (no PlayerData)");
            // ToolItemManager.GetAllCrests and friends go through ManagerSingleton.Instance, which searches the scene
            // when the manager is missing.
            if (ManagerSingleton<ToolItemManager>.UnsafeInstance == null) throw new InvalidOperationException("no ToolItemManager (not in a game)");
            return pd;
        }

        public static HeroController RequireHero()
        {
            var hero = HeroController.UnsafeInstance;
            if (hero == null) throw new InvalidOperationException("no hero");
            return hero;
        }

        public static string Name(UnityEngine.Object o) => o != null ? o.name : null;

        /// <summary>"a/b/c" from below <paramref name="root"/> down to <paramref name="t"/> (t's own name when root is not above it).</summary>
        public static string PathFrom(Transform root, Transform t)
        {
            if (t == null) return null;
            var sb = new StringBuilder(t.name);
            for (var p = t.parent; p != null && p != root; p = p.parent) sb.Insert(0, p.name + "/");
            return sb.ToString();
        }

        public static float[] Floats(Vector3 v) => new[] { v.x, v.y, v.z };

        /// <summary>Wraps a getter that may throw (a null reference mid-load, a missing singleton): the value or null.</summary>
        public static object Try(Func<object> f)
        {
            try { return f(); }
            catch (Exception) { return null; }
        }

        /// <summary>Saved crest data by crest name, and whether PlayerData has an entry at all (GetData returns a default
        /// Data for a missing one).</summary>
        public static ToolCrestsData.Data SavedCrest(PlayerData pd, string crest, out bool present)
        {
            var dict = ToolEquipsData != null && pd.ToolEquips != null ? ToolEquipsData(pd.ToolEquips) : null;
            present = dict != null && dict.ContainsKey(crest);
            return pd.ToolEquips != null ? pd.ToolEquips.GetData(crest) : default;
        }

        public static readonly AccessTools.FieldRef<SerializableNamedList<ToolCrestsData.Data, ToolCrestsData.NamedData>, Dictionary<string, ToolCrestsData.Data>> ToolEquipsData =
            Hero.Refs.Field<SerializableNamedList<ToolCrestsData.Data, ToolCrestsData.NamedData>, Dictionary<string, ToolCrestsData.Data>>("RuntimeData");
    }
}
