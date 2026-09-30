using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;

namespace SsOracle.Guards
{
    /// <summary>
    /// Wires the guards package into the oracle (DESIGN §3.1.1 Core + Guards): SymbolCheck first (so its report
    /// precedes every patch error), then Profile, the guards, the slot snapshots, the training probe RPCs, the
    /// "guards" STATE section and the per-frame monitor. Install it before other feature modules.
    /// </summary>
    internal static class GuardsModule
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            Core.SymbolCheck.Install();
            Core.Profile.Install();
            LethalBlock.Install(harmony);
            AchievementGuard.Install(harmony);
            SaveSuppression.Install(harmony);
            SessionGate.Install(harmony);
            SteelSoulSnapshot.Install();
            HurtSpecial.Install();

            Ipc.Rpc.Register("guards.get", args => GuardState.Describe());
            Ipc.Rpc.Register("guards.set", Set);
            Ipc.Rpc.Register("guards.test_achievement", AchievementGuard.TestRpc);

            Export.FrameExporter.Register(new GuardsExporter());
            host.AddComponent<GuardsMonitor>();

            Core.Plugin.Log.LogInfo($"guards: lethal_block={GuardState.LethalName(GuardState.Lethal)} (healthy {GuardState.LethalHealthy}), " +
                                    $"achievement_guard={GuardState.AchievementGuard} (healthy {GuardState.AchievementHealthy}), " +
                                    $"save_suppression={GuardState.SaveSuppression} (healthy {GuardState.SaveSuppressionHealthy}), " +
                                    $"session_gate healthy {GuardState.SessionGateHealthy}, symbols ok {Core.SymbolCheck.Ok}, profile {Core.Profile.Current}");
        }

        /// <summary>
        /// guards.set {lethal_block: bool | "block"|"observe"|"off", save_suppression: bool, achievement_guard: bool}.
        /// All-or-nothing: the new combination is checked against the profile and guard health before anything changes.
        /// </summary>
        private static object Set(Dictionary<string, object> args)
        {
            var lethal = GuardState.Lethal;
            var save = GuardState.SaveSuppression;
            var ach = GuardState.AchievementGuard;
            if (args.TryGetValue("lethal_block", out var lv) && !GuardState.TryParseLethal(lv, out lethal))
                throw new ArgumentException("lethal_block must be a bool or block|observe|off");
            if (args.ContainsKey("save_suppression")) save = Ipc.Rpc.Bool(args, "save_suppression");
            if (args.ContainsKey("achievement_guard")) ach = Ipc.Rpc.Bool(args, "achievement_guard");

            var v = Core.Profile.CheckGuards(Core.Profile.Current, lethal, save, ach);
            if (save && !GuardState.SaveSuppressionHealthy) v.Add("save_suppression is unavailable (patch failed)");
            if (lethal != LethalMode.Off && !GuardState.LethalHealthy) v.Add("lethal_block is unhealthy (patch failed)");
            if (v.Count > 0) throw new InvalidOperationException("guards.set refused: " + string.Join("; ", v.ToArray()));

            if (lethal != GuardState.Lethal || save != GuardState.SaveSuppression || ach != GuardState.AchievementGuard)
            {
                Core.Plugin.Log.LogWarning($"guards.set: lethal_block {GuardState.LethalName(GuardState.Lethal)} -> {GuardState.LethalName(lethal)}, " +
                                           $"save_suppression {GuardState.SaveSuppression} -> {save}, achievement_guard {GuardState.AchievementGuard} -> {ach}");
                Export.FrameExporter.Emit("guards", new Dictionary<string, object>
                {
                    ["lethal_block"] = GuardState.LethalName(lethal),
                    ["save_suppression"] = save,
                    ["achievement_guard"] = ach,
                });
            }
            GuardState.Lethal = lethal;
            GuardState.SaveSuppression = save;
            GuardState.AchievementGuard = ach;
            return GuardState.Describe();
        }
    }

    /// <summary>
    /// STATE "guards": switches, health and the few values the guard probes assert on. Allocation-free; the Fractured
    /// Mask is refreshed at low rate by the monitor (its lookups can search the scene).
    ///   lb 0 off / 1 observe / 2 block, ss save suppression, ag achievement guard,
    ///   ok = symbols ok and every guard healthy and nothing refused, prof profile name,
    ///   hp, blue, dead (cState.dead), inv (cState.Invulnerable), pdm permadeathMode (0 Off, 1 On, 2 Dead),
    ///   mask [equipped, amount_left] or nil, n_cat / n_wd counters.
    /// </summary>
    internal sealed class GuardsExporter : Export.IExporter
    {
        public string Key => "guards";

        public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
        {
            var pd = ctx.Pd;
            var hero = ctx.Hero;
            w.MapHeader(13);
            w.Key("lb"); w.UInt((ulong)GuardState.Lethal);
            w.Key("ss"); w.Bool(GuardState.SaveSuppression);
            w.Key("ag"); w.Bool(GuardState.AchievementGuard);
            w.Key("ok"); w.Bool(Core.SymbolCheck.Ok && GuardState.LethalHealthy && GuardState.AchievementHealthy && !GuardState.Refused);
            w.Key("prof"); w.Str(ProfileNames[(int)Core.Profile.Current]);
            w.Key("hp"); if (pd != null) w.Int(pd.health); else w.Nil();
            w.Key("blue"); if (pd != null) w.Int(pd.healthBlue); else w.Nil();
            w.Key("dead"); if (hero != null) w.Bool(hero.cState.dead); else w.Nil();
            w.Key("inv"); if (hero != null) w.Bool(hero.cState.Invulnerable); else w.Nil();
            w.Key("pdm"); if (pd != null) w.UInt((ulong)pd.permadeathMode); else w.Nil();
            w.Key("mask"); if (hero != null) LethalBlock.WriteMask(w); else w.Nil();
            w.Key("n_cat"); w.Int(GuardState.Catastrophes);
            w.Key("n_wd"); w.Int(GuardState.WouldDie);
        }

        private static readonly string[] ProfileNames = { "TRAIN", "SHADOW", "REHEARSAL_SEG", "REHEARSAL_FULL" };
    }

    /// <summary>
    /// Per-frame guard work on the main thread (LateUpdate, before the end-of-frame STATE): LethalBlock's watchers,
    /// the Steel Soul snapshot check, the late SymbolCheck and profile validation. Resolves GameManager, PlayerData
    /// and the hero afresh every frame (they are rebuilt on Save &amp; Quit, m0:N42).
    /// </summary>
    internal sealed class GuardsMonitor : MonoBehaviour
    {
        private bool first = true;

        private void LateUpdate()
        {
            if (first)
            {
                first = false;
                Core.SymbolCheck.LateCheck();
            }
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            var hero = HeroController.UnsafeInstance;
            try
            {
                LethalBlock.Tick(gm, pd, hero);
                SteelSoulSnapshot.Tick(gm, pd);
                Core.Profile.Tick();
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError("guards monitor failed: " + e);
            }
        }
    }
}
