using System;
using System.Collections;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// Wave starts for training (Forum plan R1, docs/plans/forum_planner_plan.md: targeted data collection and the
    /// curriculum; gates stay on full gauntlets). Two RPCs:
    ///
    /// "battle.wave" {wave, timeout?} fast-forwards the room's running BattleScene to wave index `wave` by killing the
    /// live members of the waves that run before it, through the game's own HealthManager.Die (Generic attack, as
    /// DebugMod's "kill all" does), so the BattleScene advances by its own rules (DecrementEnemy / DoCheckEnemies /
    /// WaveEnd / StartWave with each wave's startDelay, 1.0.30000 BattleScene.cs) and every wave's own events fire on
    /// the way (wave 1's "Call Ally" sends the helper in, the Heavy Sentry waves drop the lamp). Only members of waves
    /// 0..currentWave are killed (Hang_04_boss waves 1, 6 and 12 keep their enemies active and waiting from the scene
    /// load: those are left alone until their wave runs); the Maestro's pooled summons are not wave members and are
    /// not touched. Waits for the battle to have started (the intro's StartBattle and battleStartPause), then answers
    /// once currentWave == wave with {wave, kills, killed: [type names], frames, seconds (real), enemies, to_next}.
    /// While it runs the harness is busy (ACTIONs ignored).
    ///
    /// The other way to a wave start, which the deployed oracle already has: a DebugMod savestate taken during wave i
    /// (DebugMod RoomSpecific saves "BattleScene|Battle Scene|&lt;currentWave&gt;"; its load sets currentWave and
    /// StartBattle, and a transpiler turns DoStartBattle's StartWave(0) into StartWave(currentWave)). Such a load
    /// restarts the battle at wave i, but (forum.md 13.1): wave 1's Call Ally does not fire for i &gt;= 2 (no helper);
    /// room.battles reports wave i from the battle start, startDelay(i) before its members are activated; and the
    /// members of waves 0..i-1 that never ran stay children of their wave objects, so DoCheckEnemiesNew (the sum of
    /// childCount over waves 0..currentWave) is inflated for the whole fight: an overlapping wave (remainingEnemyToEnd
    /// &gt; 0, Forum wave 2) waits for a kill instead of its 1 s count check, and a doubled StartWave is never corrected.
    ///
    /// "battle.prune" {} removes those ghosts: right after a wave-start load (the battle at wave i, before anything
    /// of it has died), it detaches and destroys every child with a HealthManager of waves 0..currentWave-1, so the
    /// count check sees what a natural run at wave i sees. Returns {wave, started, pruned: [names], kept: [names of
    /// children without a HealthManager], child_counts_before, child_counts_after}. Not for a natural run: there the
    /// earlier waves' children are its overlapping survivors. Training copy only (cheats) for both.
    /// </summary>
    internal static class BattleWaveRpc
    {
        private const double DefaultTimeoutS = 120;
        private const float KillEveryS = 0.1f;

        private static readonly AccessTools.FieldRef<BattleScene, bool> Started =
            AccessTools.FieldRefAccess<BattleScene, bool>("started");
        private static readonly AccessTools.FieldRef<BattleScene, bool> Completed =
            AccessTools.FieldRefAccess<BattleScene, bool>("completed");

        public static void Register()
        {
            Rpc.Register("battle.wave", Handle);
            Rpc.Register("battle.prune", HandlePrune);
        }

        private static void Handle(Dictionary<string, object> args, Rpc.Reply reply)
        {
            if (!Core.Profile.Rules.CheatsAllowed)
            {
                reply.Fail($"battle.wave is disabled in profile {Core.Profile.Current}");
                return;
            }
            var wave = (int)Rpc.Long(args, "wave");
            var timeout = Rpc.Double(args, "timeout", DefaultTimeoutS);
            HarnessRunner.Run("battle.wave", reply, op => Body(op, wave, timeout));
        }

        private static void HandlePrune(Dictionary<string, object> args, Rpc.Reply reply)
        {
            if (!Core.Profile.Rules.CheatsAllowed)
            {
                reply.Fail($"battle.prune is disabled in profile {Core.Profile.Current}");
                return;
            }
            var bs = FindBattle();
            if (bs == null)
            {
                reply.Fail("no active, unfinished BattleScene in the room");
                return;
            }
            var upTo = Math.Min(bs.currentWave, bs.waves.Count);
            var pruned = new List<object>();
            var kept = new List<object>();
            var before = new List<object>();
            var after = new List<object>();
            for (var i = 0; i <= upTo && i < bs.waves.Count; i++)
                before.Add((long)(bs.waves[i] != null ? bs.waves[i].transform.childCount : -1));
            for (var i = 0; i < upTo; i++)
            {
                var w = bs.waves[i];
                if (w == null) continue;
                var t = w.transform;
                for (var c = t.childCount - 1; c >= 0; c--)
                {
                    var ch = t.GetChild(c);
                    if (ch.GetComponentInChildren<HealthManager>(true) == null)
                    {
                        kept.Add(ch.name);
                        continue;
                    }
                    try
                    {
                        // detach first: Destroy is deferred to the end of the frame, childCount must drop now
                        ch.gameObject.SetActive(false);
                        ch.SetParent(null, true);
                        UnityEngine.Object.Destroy(ch.gameObject);
                        pruned.Add($"wave {i}: {ch.name}");
                    }
                    catch (Exception e)
                    {
                        Core.Plugin.Log.LogWarning($"battle.prune: {ch.name} failed: {e.Message}");
                        kept.Add(ch.name);
                    }
                }
            }
            for (var i = 0; i <= upTo && i < bs.waves.Count; i++)
                after.Add((long)(bs.waves[i] != null ? bs.waves[i].transform.childCount : -1));
            Core.Plugin.Log.LogInfo($"battle.prune: wave {bs.currentWave}, {pruned.Count} pruned, {kept.Count} kept");
            reply.Ok(new Dictionary<string, object>
            {
                ["wave"] = bs.currentWave,
                ["started"] = Started(bs),
                ["pruned"] = pruned,
                ["kept"] = kept,
                ["child_counts_before"] = before,
                ["child_counts_after"] = after,
            });
        }

        private static BattleScene FindBattle()
        {
            BattleScene best = null;
            foreach (var bs in UnityEngine.Object.FindObjectsByType<BattleScene>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
            {
                if (bs == null || !bs.isActiveAndEnabled || Completed(bs) || bs.waves == null || bs.waves.Count == 0) continue;
                if (best == null || Started(bs) && !Started(best)) best = bs;
            }
            return best;
        }

        private static IEnumerator Body(HarnessOp op, int target, double timeoutS)
        {
            var t0 = Time.realtimeSinceStartup;
            var bs = FindBattle();
            while (bs != null && !Started(bs))
            {
                if (Time.realtimeSinceStartup - t0 > timeoutS)
                {
                    op.Error = "the battle did not start (run the intro first)";
                    yield break;
                }
                yield return null;
                bs = bs != null ? bs : FindBattle();
            }
            if (bs == null)
            {
                op.Error = "no active, unfinished BattleScene in the room";
                yield break;
            }
            if (target < 0 || target >= bs.waves.Count)
            {
                op.Error = $"wave {target} out of range (0..{bs.waves.Count - 1})";
                yield break;
            }
            if (bs.currentWave > target)
            {
                op.Error = $"already at wave {bs.currentWave} > {target}";
                yield break;
            }
            var killed = new List<object>();
            var frame0 = Time.frameCount;
            while (bs.currentWave < target)
            {
                if (bs == null || Completed(bs))
                {
                    op.Error = "the battle ended before the wave";
                    yield break;
                }
                if (Time.realtimeSinceStartup - t0 > timeoutS)
                {
                    op.Error = $"timeout at wave {bs.currentWave} after {killed.Count} kills";
                    yield break;
                }
                for (var i = 0; i <= bs.currentWave && i < bs.waves.Count; i++)
                {
                    var w = bs.waves[i];
                    if (w == null || !w.gameObject.activeInHierarchy) continue;
                    foreach (var hm in w.GetComponentsInChildren<HealthManager>(false))
                    {
                        if (hm == null || hm.isDead || hm.hp <= 0) continue;
                        try
                        {
                            hm.Die(null, AttackTypes.Generic, true);
                            killed.Add(hm.gameObject.name);
                        }
                        catch (Exception e)
                        {
                            Core.Plugin.Log.LogWarning($"battle.wave: Die on {hm.gameObject.name} failed: {e.Message}");
                        }
                    }
                }
                yield return new WaitForSeconds(KillEveryS);
            }
            Core.Plugin.Log.LogInfo($"battle.wave: at wave {bs.currentWave} after {killed.Count} kills, " +
                                    $"{Time.frameCount - frame0} frames");
            Export.FrameExporter.Emit("harness", new Dictionary<string, object>
            {
                ["op"] = "battle.wave", ["wave"] = bs.currentWave, ["kills"] = killed.Count,
            });
            op.Result = new Dictionary<string, object>
            {
                ["wave"] = bs.currentWave,
                ["kills"] = killed.Count,
                ["killed"] = killed,
                ["frames"] = (long)(Time.frameCount - frame0),
                ["seconds"] = (double)(Time.realtimeSinceStartup - t0),
                ["enemies"] = bs.currentEnemies,
                ["to_next"] = bs.enemiesToNext,
            };
        }
    }
}
