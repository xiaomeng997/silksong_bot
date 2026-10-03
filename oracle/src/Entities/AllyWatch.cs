using System;
using System.Collections.Generic;
using HarmonyLib;
using HutongGames.PlayMaker;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// STATE "allies" (M2 W8, DESIGN §3.5.7: helpers are their own class and their attacks are never threats): the
    /// fighters that take the hero's side, which "ents" leaves out because nothing on them hurts the hero (no
    /// HealthManager, no live DamageHero). Two kinds:
    /// <list type="bullet">
    /// <item>"cogfly": every enabled ClockworkHatchling (the Cogfly tool, ToolItem "Cogwork Flier"; 1.0.30000
    /// ClockworkHatchling.cs), kept by postfixes on its OnEnable / OnDisable / OnDestroy.</item>
    /// <item>"npc": the direct children of a BattleScene whose name ends in " Fighter" and that have no HealthManager
    /// (Hang_04_boss "Battle Scene": "Garmond Fighter" and "Shakra Fighter", both always present; the "Call Ally" FSM
    /// sends one of them ENTER FORUM 4 s after wave index 1 starts, from PlayerData garmondAidForumBattle /
    /// shakraAidForumBattle; docs/facts/1.0.30000/forum.md). Registered by the SceneDumper's walk
    /// (SceneDump.BattleWatch.Battle), so they appear once the room's TERRAIN dump is done; a dormant one is listed
    /// too ("active" false, or its "Control" state "Dormant").</item>
    /// </list>
    /// Entry: {kind, name, iid (GameObject instance id), active (activeInHierarchy), pos [x, y], vel [x, y] | nil
    /// (Rigidbody2D), scale_x (lossyScale.x, raw: its sign is the facing, which way depends on the sprite), state
    /// (cogfly: ClockworkHatchling.CurrentState name; npc: the "Control" FSM's active state or nil), hp (cogfly: its
    /// private hpCurrent; npc: nil), box [x0, y0, x1, y1] | nil (bounds of the root's own enabled Collider2D while
    /// active)}. NPC fighters first, at most MaxListed entries. Cost per frame: a few component reads per ally.
    /// </summary>
    internal static class AllyWatch
    {
        public const int MaxListed = 16;

        private sealed class Ally
        {
            public string Kind, Name;
            public GameObject Go;
            public Transform Tr;
            public int Iid;
            public Rigidbody2D Rb;
            public Collider2D Col;
            public ClockworkHatchling Cog;
            public PlayMakerFSM Control;
        }

        private static readonly AccessTools.FieldRef<ClockworkHatchling, int> HpCurrent =
            AccessTools.FieldRefAccess<ClockworkHatchling, int>("hpCurrent");

        private static readonly Dictionary<int, Ally> Cogs = new Dictionary<int, Ally>();
        private static readonly List<Ally> Npcs = new List<Ally>();
        private static readonly List<Ally> Scratch = new List<Ally>();

        public static void Install(Harmony harmony)
        {
            var t = typeof(ClockworkHatchling);
            var missing = new List<string>();
            foreach (var (m, p) in new[] { ("OnEnable", nameof(CogEnabled)), ("OnDisable", nameof(CogDisabled)) })
            {
                var target = AccessTools.DeclaredMethod(t, m);
                if (target == null) missing.Add($"ClockworkHatchling.{m}");
                else harmony.Patch(target, postfix: new HarmonyMethod(typeof(AllyWatch), p));
            }
            if (AccessTools.Field(t, "hpCurrent")?.FieldType != typeof(int)) missing.Add("ClockworkHatchling.hpCurrent (int)");
            if (missing.Count > 0)
                throw new MissingMemberException("AllyWatch: game symbols not found: " + string.Join(", ", missing.ToArray()));
        }

        private static void CogEnabled(ClockworkHatchling __instance)
        {
            try
            {
                var go = __instance.gameObject;
                Cogs[go.GetInstanceID()] = new Ally
                {
                    Kind = "cogfly", Name = go.name, Go = go, Tr = go.transform, Iid = go.GetInstanceID(),
                    Rb = go.GetComponent<Rigidbody2D>(), Col = go.GetComponent<Collider2D>(), Cog = __instance,
                };
            }
            catch (Exception) { }
        }

        private static void CogDisabled(ClockworkHatchling __instance)
        {
            try
            {
                if (__instance != null) Cogs.Remove(__instance.gameObject.GetInstanceID());
            }
            catch (Exception) { }
        }

        /// <summary>SceneDumper walk (main thread): the BattleScene's " Fighter" children without a HealthManager.</summary>
        public static void BattleScene(BattleScene bs)
        {
            if (bs == null) return;
            var tr = bs.transform;
            for (var i = 0; i < tr.childCount && Npcs.Count < MaxListed; i++)
            {
                var c = tr.GetChild(i);
                var go = c.gameObject;
                var name = go.name;
                if (!name.EndsWith(" Fighter", StringComparison.Ordinal) || go.GetComponent<HealthManager>() != null) continue;
                var iid = go.GetInstanceID();
                if (Npcs.Exists(a => a.Iid == iid)) continue;
                PlayMakerFSM control = null;
                foreach (var f in go.GetComponents<PlayMakerFSM>())
                    if (f != null && HitboxCategory.FsmName(f) == "Control") { control = f; break; }
                Npcs.Add(new Ally
                {
                    Kind = "npc", Name = name, Go = go, Tr = c, Iid = iid, Rb = go.GetComponent<Rigidbody2D>(),
                    Col = go.GetComponent<Collider2D>(), Control = control,
                });
            }
        }

        /// <summary>Scene change: NPC fighters belong to the room (Cogflies follow the hero and stay).</summary>
        public static void SceneChanged() => Npcs.RemoveAll(a => a.Go == null);

        public static void Write(Ipc.MsgPackWriter w)
        {
            Scratch.Clear();
            foreach (var a in Npcs)
                if (a.Go != null && Scratch.Count < MaxListed) Scratch.Add(a);
            foreach (var a in Cogs.Values)
                if (a.Go != null && Scratch.Count < MaxListed) Scratch.Add(a);
            w.ArrayHeader(Scratch.Count);
            foreach (var a in Scratch)
            {
                w.MapHeader(10);
                w.Key("kind"); w.Str(a.Kind);
                w.Key("name"); w.Str(a.Name);
                w.Key("iid"); w.Int(a.Iid);
                w.Key("active"); w.Bool(a.Go.activeInHierarchy);
                var p = a.Tr.position;
                w.Key("pos"); w.ArrayHeader(2); w.Float(p.x); w.Float(p.y);
                w.Key("vel");
                if (a.Rb != null) { var v = a.Rb.linearVelocity; w.ArrayHeader(2); w.Float(v.x); w.Float(v.y); }
                else w.Nil();
                w.Key("scale_x"); w.Float(a.Tr.lossyScale.x);
                w.Key("state");
                if (a.Cog != null) w.Str(a.Cog.CurrentState.ToString());
                else if (a.Control != null) w.Str(EntityRegistry.FsmOf(a.Control)?.ActiveState?.Name);
                else w.Nil();
                w.Key("hp");
                if (a.Cog != null) w.Int(HpCurrent(a.Cog)); else w.Nil();
                w.Key("box");
                if (a.Col != null && a.Col.enabled && a.Go.activeInHierarchy)
                {
                    var b = a.Col.bounds;
                    w.ArrayHeader(4); w.Float(b.min.x); w.Float(b.min.y); w.Float(b.max.x); w.Float(b.max.y);
                }
                else w.Nil();
            }
            Scratch.Clear();
        }
    }

    internal sealed class AllyExporter : Export.IExporter
    {
        public string Key => "allies";

        public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx) => AllyWatch.Write(w);
    }
}
