using System;
using System.Collections;
using System.Collections.Generic;
using GlobalEnums;
using UnityEngine;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// Randomized episode starts after a savestate load (DESIGN §3.1.1 Harness StartRandomizer, §3.9.1):
    ///   randomize_start {seed, hp: [min,max], silk: [min,max], dx: [min,max], facing: "left"|"right"|"random",
    ///                    wait_frames: [min,max]}
    /// Seeds UnityEngine.Random (the game's AI rolls) with the seed, then draws five uniforms from System.Random(seed) in a
    /// fixed order (hp, silk, dx, facing, wait) whether or not each field is given, so a seed names the same start. HP
    /// and silk are written to PlayerData (clamped to [1, max] / [0, max]) and the HUD redrawn; dx moves the hero only
    /// if the terrain allows (StartPlacement: no wall in between, ground within a step, room to stand), otherwise a
    /// shorter offset or none; facing uses FaceLeft/FaceRight; then N frames pass with no input (ACTIONs are ignored).
    /// Answers with what was applied and the hero state at the end of the wait.
    /// </summary>
    internal static class StartRandomizer
    {
        private const int MaxWaitFrames = 600;

        public static void Register() => Rpc.Register("randomize_start", Randomize);

        private sealed class Request
        {
            public int Seed;
            public bool HasHp, HasSilk, HasDx, HasWait;
            public double HpLo, HpHi, SilkLo, SilkHi, DxLo, DxHi, WaitLo, WaitHi;
            public string Facing;
        }

        private static void Randomize(Dictionary<string, object> args, Rpc.Reply reply)
        {
            var r = new Request
            {
                Seed = unchecked((int)Rpc.Long(args, "seed")),
                Facing = Rpc.Str(args, "facing"),
            };
            r.HasHp = Range(args, "hp", out r.HpLo, out r.HpHi);
            r.HasSilk = Range(args, "silk", out r.SilkLo, out r.SilkHi);
            r.HasDx = Range(args, "dx", out r.DxLo, out r.DxHi);
            r.HasWait = Range(args, "wait_frames", out r.WaitLo, out r.WaitHi);
            if (r.Facing != null && r.Facing != "left" && r.Facing != "right" && r.Facing != "random" && r.Facing != "keep")
                throw new ArgumentException("facing must be left, right, random or keep");
            HarnessRunner.Run("randomize_start", reply, op => Body(op, r));
        }

        private static IEnumerator Body(HarnessOp op, Request r)
        {
            var gm = GameManager._instance;
            var hero = HeroController.UnsafeInstance;
            var pd = gm != null ? gm.playerData : null;
            if (gm == null || hero == null || pd == null)
            {
                op.Error = "no game loaded (no GameManager, hero or PlayerData)";
                yield break;
            }
            if (DebugModBridge.LoadInProgress || gm.GameState != GameState.PLAYING || gm.IsInSceneTransition || hero.cState.transitioning)
            {
                op.Error = $"not in a steady gameplay state (GameState {gm.GameState}; load the savestate first)";
                yield break;
            }
            DebugModBridge.Resolve();  // optional: only used for the HUD refresh

            UnityEngine.Random.InitState(r.Seed);
            var rng = new System.Random(r.Seed);
            double uHp = rng.NextDouble(), uSilk = rng.NextDouble(), uDx = rng.NextDouble(), uFace = rng.NextDouble(), uWait = rng.NextDouble();
            var result = new Dictionary<string, object> { ["seed"] = r.Seed, ["frame_applied"] = (long)Time.frameCount };

            var hpBefore = pd.health;
            if (r.HasHp)
            {
                var hp = Mathf.Clamp(PickInt(uHp, r.HpLo, r.HpHi), 1, Math.Max(1, pd.CurrentMaxHealth));
                if (hp != pd.health)
                {
                    pd.health = hp;
                    EventRegister.SendEvent("HEALTH UPDATE");
                    DebugModBridge.RefreshHud(masks: true, spool: false);
                }
            }
            result["hp_before"] = hpBefore;
            result["hp"] = pd.health;

            var silkBefore = pd.silk;
            if (r.HasSilk) SetSilk(hero, pd, Mathf.Clamp(PickInt(uSilk, r.SilkLo, r.SilkHi), 0, Math.Max(0, pd.CurrentSilkMax)));
            result["silk_before"] = silkBefore;
            result["silk"] = pd.silk;

            // Facing first: flipping the scale can move an off-centre collider, and the placement search uses its bounds.
            var face = r.Facing == "random" ? (uFace < 0.5 ? "left" : "right") : r.Facing;
            if (face == "left") hero.FaceLeft();
            else if (face == "right") hero.FaceRight();
            Physics2D.SyncTransforms();
            result["facing"] = hero.cState.facingRight ? "right" : "left";

            var dxWant = r.HasDx ? (float)(r.DxLo + uDx * (r.DxHi - r.DxLo)) : 0f;
            var dx = StartPlacement.FindOffset(hero, dxWant, out var dy, out var tries, out var note);
            if (dx != 0f || dy != 0f)
            {
                var p = hero.transform.position;
                p.x += dx;
                p.y += dy;
                hero.transform.position = p;
                var body = hero.Body;
                if (body != null) body.position = new Vector2(p.x, p.y);
                Physics2D.SyncTransforms();
                try
                {
                    gm.cameraCtrl.PositionToHeroInstant(false);
                }
                catch (Exception e)
                {
                    Core.Plugin.Log.LogWarning("randomize_start: camera snap failed: " + e.Message);
                }
            }
            result["dx_requested"] = dxWant;
            result["dx"] = dx;
            result["dy"] = dy;
            result["dx_tries"] = tries;
            result["dx_note"] = note;

            var wait = r.HasWait ? Mathf.Clamp(PickInt(uWait, r.WaitLo, r.WaitHi), 0, MaxWaitFrames) : 0;
            result["wait_frames"] = wait;
            Export.FrameExporter.Emit("harness", new Dictionary<string, object>
            {
                ["op"] = "randomize_start", ["seed"] = r.Seed, ["hp"] = pd.health, ["silk"] = pd.silk, ["dx"] = dx, ["wait"] = wait,
            });
            Core.Plugin.Log.LogInfo($"randomize_start seed {r.Seed}: hp {hpBefore}->{pd.health}, silk {silkBefore}->{pd.silk}, " +
                                    $"dx {dxWant:0.00}->{dx:0.00} ({note ?? "ok"}), facing {result["facing"]}, wait {wait}");
            for (var i = 0; i < wait; i++) yield return null;

            hero = HeroController.UnsafeInstance;
            gm = GameManager._instance;
            pd = gm != null ? gm.playerData : null;
            if (hero == null || pd == null)
            {
                op.Error = "game unloaded during the wait";
                yield break;
            }
            result["frame_done"] = (long)Time.frameCount;
            result["pos"] = hero.transform.position;
            result["vel"] = hero.Body != null ? hero.Body.linearVelocity : Vector2.zero;
            result["on_ground"] = hero.cState.onGround;
            result["facing_right"] = hero.cState.facingRight;
            result["hp_now"] = pd.health;
            result["silk_now"] = pd.silk;
            op.Result = result;
        }

        /// <summary>Silk through the hero's own API (it redraws the spool and resets regen); the refill sound and the
        /// can-bind flash are suppressed. TakeSilk is a no-op while tools are in cutscene state, hence the fallback.</summary>
        private static void SetSilk(HeroController hero, PlayerData pd, int target)
        {
            var before = pd.silk;
            if (target > before)
            {
                hero.SuppressRefillSound(2);
                hero.AddSilk(target - before, false);
            }
            else if (target < before)
            {
                hero.TakeSilk(before - target);
            }
            if (pd.silk != target)
            {
                pd.silk = target;
                var spool = SilkSpool.Instance;
                if (spool != null) spool.RefreshSilk();
                DebugModBridge.RefreshHud(masks: false, spool: true);
            }
        }

        private static int PickInt(double u, double lo, double hi)
        {
            var a = (int)Math.Ceiling(lo);
            var b = (int)Math.Floor(hi);
            if (b <= a) return a;
            return Math.Min(b, a + (int)Math.Floor(u * (b - a + 1)));
        }

        /// <summary>[min, max] or a single number; absent / nil = not requested.</summary>
        private static bool Range(Dictionary<string, object> args, string key, out double lo, out double hi)
        {
            lo = hi = 0;
            if (!args.TryGetValue(key, out var v) || v == null) return false;
            if (v is List<object> l)
            {
                if (l.Count != 2) throw new ArgumentException($"{key} must be [min, max]");
                lo = Convert.ToDouble(l[0]);
                hi = Convert.ToDouble(l[1]);
            }
            else
            {
                lo = hi = Convert.ToDouble(v);
            }
            if (double.IsNaN(lo) || double.IsNaN(hi) || hi < lo) throw new ArgumentException($"{key} must be [min, max] with min <= max");
            return true;
        }
    }
}
