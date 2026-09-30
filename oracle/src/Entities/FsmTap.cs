using System;
using System.Collections.Generic;
using HarmonyLib;
using HutongGames.PlayMaker;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// FSM_TRANSITION events (DESIGN §3.1.1 FsmTap, §3.10 fsm.parquet): a Harmony prefix on the private
    /// HutongGames.PlayMaker.Fsm.EnterState(FsmState), the single entry point of every state (m0 §3 PlayMaker
    /// row). Emits FrameExporter event "fsm" {iid, ent, obj, fsm, from, to, t_in_prev, rt_in_prev}:
    ///   iid = GameObject holding the FSM, ent = its entity root (HealthManager ancestor, else DamageHero
    ///   ancestor, else itself), obj = GameObject name, from = null on a (re)start, t_in_prev = FsmState.StateTime
    ///   of the state being left (scaled; PlayMaker stops counting once a state's actions have all finished),
    ///   rt_in_prev = its FsmState.StateRealTime (unscaled seconds since it was entered, never stops); both null
    ///   with from. Exact scaled dwell = the game time between this event's frame and the one that entered from.
    /// A prefix, not a postfix: OnEnter can chain further transitions inside EnterState, and the events must
    /// come out in the order the states were entered; and a self-transition resets StateTime in OnEnter.
    /// By default only FSMs of entities of interest are reported (HealthManager or DamageHero ancestor, a
    /// damage-source FSM or cog, or a root currently in "ents"); "fsmtap.set" {all: true} reports every FSM.
    /// </summary>
    internal static class FsmTap
    {
        public static bool Enabled = true;
        public static bool All;
        public static long Emitted, Dropped, Deferred;

        /// <summary>Scene loads start thousands of FSMs in one frame; cap what one STATE can carry.</summary>
        private const int MaxPerFrame = 512;
        /// <summary>...and cap the owner lookups (two GetComponentInParent each) so a load frame is not a
        /// multi-millisecond spike. An FSM over the cap is looked up at its next state entry; the entry itself is
        /// not reported (counted in Deferred). On a load frame these are almost all start events (from == null).</summary>
        private const int MaxResolvesPerFrame = 64;
        private static int frame = -1, perFrame, resolves;
        private static int errorsLogged;

        private sealed class Info
        {
            public GameObject Go;
            public int GoIid;
            public int EntIid;
            public string Obj;  // GameObject.name allocates: read on the first emitted event only
            public bool Interest;
        }

        private static readonly Dictionary<Fsm, Info> Infos = new Dictionary<Fsm, Info>(1024, RefComparer<Fsm>.Instance);

        public static void Install(Harmony harmony)
        {
            // Hard failure on a missing symbol (m0 §3 general rule): Harmony would bind ___activeStateEntered lazily.
            var target = AccessTools.DeclaredMethod(typeof(Fsm), "EnterState", new[] { typeof(FsmState) });
            var entered = AccessTools.Field(typeof(Fsm), "activeStateEntered");
            if (target == null || entered == null || entered.FieldType != typeof(bool))
                throw new MissingMemberException("FsmTap: HutongGames.PlayMaker.Fsm.EnterState(FsmState) or bool Fsm.activeStateEntered not found");
            harmony.Patch(target, prefix: new HarmonyMethod(typeof(FsmTap), nameof(EnterStatePrefix)));
        }

        /// <summary>Scene change: the cached owner lookups belong to destroyed objects.</summary>
        public static void ClearCache() => Infos.Clear();

        public static int CacheSize => Infos.Count;

        private static void NewFrame()
        {
            var f = Time.frameCount;
            if (f == frame) return;
            frame = f;
            perFrame = 0;
            resolves = 0;
        }

        // ___activeStateEntered is still the value from before this entry: false on Start/restart (no ExitState ran,
        // PreviousActiveState is stale), true on a normal SwitchState (ExitState just set PreviousActiveState).
        private static void EnterStatePrefix(Fsm __instance, FsmState state, bool ___activeStateEntered)
        {
            if (!Enabled || state == null) return;
            // Nothing drains events without a brain, and the cache would only grow.
            var server = Ipc.FramedServer.Instance;
            if (server == null || !server.Connected) return;
            try
            {
                if (!Infos.TryGetValue(__instance, out var info))
                {
                    NewFrame();
                    if (resolves >= MaxResolvesPerFrame)
                    {
                        Deferred++;
                        return;
                    }
                    resolves++;
                    Infos[__instance] = info = Resolve(__instance);
                }
                if (!All && !info.Interest && !EntityRegistry.IsIncludedRoot(info.EntIid)) return;

                NewFrame();
                if (++perFrame > MaxPerFrame)
                {
                    Dropped++;
                    return;
                }

                if (info.Obj == null) info.Obj = info.Go != null ? info.Go.name : "";
                var prev = ___activeStateEntered ? __instance.PreviousActiveState : null;
                Export.FrameExporter.Emit("fsm", new Dictionary<string, object>(8)
                {
                    ["iid"] = info.GoIid,
                    ["ent"] = info.EntIid,
                    ["obj"] = info.Obj,
                    ["fsm"] = __instance.Name,
                    ["from"] = prev?.Name,
                    ["to"] = state.Name,
                    ["t_in_prev"] = prev != null ? (object)prev.StateTime : null,
                    ["rt_in_prev"] = prev != null ? (object)prev.StateRealTime : null,
                });
                Emitted++;
            }
            catch (Exception e)
            {
                // Never throw into PlayMaker.
                if (errorsLogged++ < 10) Core.Plugin.Log.LogWarning("FsmTap: " + e.GetType().Name + ": " + e.Message);
            }
        }

        private static Info Resolve(Fsm fsm)
        {
            var owner = fsm.Owner;
            if (owner == null) return new Info { Obj = "" };
            var go = owner.gameObject;
            var goIid = go.GetInstanceID();
            var hm = go.GetComponentInParent<HealthManager>(true);
            var dh = hm == null ? go.GetComponentInParent<DamageHero>(true) : null;
            var damageFsm = owner is PlayMakerFSM pm && HitboxCategory.FsmName(pm) == "damages_hero";
            var cog = go.GetComponent<CogMultiHitter>() != null;
            return new Info
            {
                Go = go,
                GoIid = goIid,
                EntIid = hm != null ? hm.gameObject.GetInstanceID() : dh != null ? dh.gameObject.GetInstanceID() : goIid,
                Interest = hm != null || dh != null || damageFsm || cog,
            };
        }
    }
}
