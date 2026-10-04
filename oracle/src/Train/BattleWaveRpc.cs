using System;
using System.Collections;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// RPC "battle.wave" {wave, timeout?} (Forum plan R1, docs/plans/forum_planner_plan.md: wave starts for targeted
    /// data collection and the curriculum; gates stay on full gauntlets): fast-forwards the room's running BattleScene
    /// to wave index `wave` by killing the live members of the waves that run before it, through the game's own
    /// HealthManager.Die (Generic attack, as DebugMod's "kill all" does), so the BattleScene advances by its own rules
    /// (DecrementEnemy / DoCheckEnemies / WaveEnd / StartWave with each wave's startDelay, 1.0.30000 BattleScene.cs) and
    /// every wave's own events fire on the way (wave 1's "Call Ally" sends the helper in 4 s after its start, the Heavy
    /// Sentry waves drop the lamp). Only members of waves 0..currentWave are killed (Hang_04_boss waves 1, 6 and 12 keep
    /// their enemies active and waiting from the scene load: those are left alone until their wave runs); the Maestro's
    /// pooled summons are not wave members and are not touched. A DebugMod savestate cannot do this: its load reloads
    /// the scene, and the wave index lives only in the BattleScene's fields.
    /// Waits for the battle to have started (the intro's StartBattle and battleStartPause), then answers once
    /// currentWave == wave (set by StartWave after the wave's startDelay, when its enemies are activated) with
    /// {wave, kills, killed: [type names], frames, seconds (real), enemies, to_next}. Training copy only (cheats).
    /// While it runs the harness is busy (ACTIONs ignored).
    /// </summary>
    internal static class BattleWaveRpc
    {
        private const double DefaultTimeoutS = 120;
        private const float KillEveryS = 0.1f;

        private static readonly AccessTools.FieldRef<BattleScene, bool> Started =
            AccessTools.FieldRefAccess<BattleScene, bool>("started");
        private static readonly AccessTools.FieldRef<BattleScene, bool> Completed =
            AccessTools.FieldRefAccess<BattleScene, bool>("completed");

        public static void Register() => Rpc.Register("battle.wave", Handle);

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
