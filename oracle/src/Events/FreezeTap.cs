using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using GlobalEnums;
using HarmonyLib;

namespace SsOracle.Events
{
    /// <summary>
    /// "freeze" start/end for every GameManager.FreezeMoment (hit-freeze and slow motion both block pausing and
    /// unpausing for their whole duration: m0:N13, m0 §2.4). All presets and the hero's own damage freeze
    /// (m0:C5) run the FreezeMoment(float x4, Action) coroutine, so its iterator is wrapped: "end" is emitted when
    /// the coroutine finishes (its finally has already decremented timeSlowedCount by then). If a coroutine is
    /// abandoned (owner destroyed, Save &amp; Quit), the per-frame poll closes it once timeSlowedCount reaches 0.
    /// </summary>
    internal static class FreezeTap
    {
        private struct Open
        {
            public string Type;
            public long StartQpc;
            public long StartFrame;
        }

        private static readonly AccessTools.FieldRef<GameManager, int> TimeSlowedCount =
            AccessTools.FieldRefAccess<GameManager, int>("timeSlowedCount");

        private static readonly Dictionary<int, Open> OpenFreezes = new Dictionary<int, Open>();
        private static readonly List<int> Closing = new List<int>();
        private static string pendingType;
        private static int nextId;
        private static int gmId;

        public static int OpenCount => OpenFreezes.Count;

        public static void Install(Harmony h)
        {
            var gm = typeof(GameManager);
            Tap.Patch(h, gm, "FreezeMoment", new[] { typeof(FreezeMomentTypes), typeof(Action) }, typeof(FreezeTap), nameof(TypedPrefix), nameof(TypedPostfix));
            Tap.Patch(h, gm, "FreezeMoment", new[] { typeof(float), typeof(float), typeof(float), typeof(float), typeof(Action) },
                typeof(FreezeTap), postfix: nameof(RoutinePostfix));
        }

        private static void TypedPrefix(FreezeMomentTypes type) => pendingType = type.ToString();

        private static void TypedPostfix() => pendingType = null;

        private static void RoutinePostfix(GameManager __instance, ref IEnumerator __result, float rampDownTime, float waitTime,
                                           float rampUpTime, float targetSpeed)
        {
            if (__result == null) return;
            if (OpenFreezes.Count == 0) gmId = __instance.GetInstanceID();
            var id = ++nextId;
            var active = Tap.Active;
            // Preset calls are named by their FreezeMomentTypes; a direct call (the hero's own damage freeze with
            // the prefab's DAMAGE_FREEZE_* values, m0:C5; FSM actions) is named by its caller.
            List<string> caller = null;
            var type = pendingType;
            if (type == null)
            {
                caller = active ? Tap.Caller(4) : null;
                type = "direct:" + FirstCaller(caller);
            }
            OpenFreezes[id] = new Open { Type = type, StartQpc = Stopwatch.GetTimestamp(), StartFrame = UnityEngine.Time.frameCount };
            __result = new Tracker(__result, id);
            if (!active) return;
            var d = Tap.Data(12);
            d["phase"] = "start";
            d["id"] = id;
            d["type"] = type;
            d["down"] = rampDownTime;
            d["wait"] = waitTime;
            d["up"] = rampUpTime;
            d["speed"] = targetSpeed;
            if (caller != null) d["caller"] = caller;
            Tap.Attribute(d, false);
            Tap.Emit("freeze", d);
        }

        private static string FirstCaller(List<string> caller)
        {
            if (caller == null) return "?";
            // Skip the patched FreezeMoment itself, however MonoMod named its replacement.
            foreach (var c in caller)
                if (c.IndexOf("FreezeMoment", StringComparison.Ordinal) < 0) return c;
            return "?";
        }

        private static void End(int id, string reason)
        {
            if (!OpenFreezes.TryGetValue(id, out var f)) return;
            OpenFreezes.Remove(id);
            if (!Tap.Active) return;
            var d = Tap.Data(8);
            d["phase"] = "end";
            d["id"] = id;
            d["type"] = f.Type;
            d["ms"] = Tap.Us(f.StartQpc, Stopwatch.GetTimestamp()) / 1000.0;
            d["frames"] = UnityEngine.Time.frameCount - f.StartFrame;
            d["reason"] = reason;
            Tap.Emit("freeze", d);
        }

        /// <summary>Per frame (EventsRunner.LateUpdate, connected or not): close freezes whose coroutine will never finish.</summary>
        public static void Poll(GameManager gm)
        {
            var id = gm != null ? gm.GetInstanceID() : 0;
            if (OpenFreezes.Count == 0)
            {
                gmId = id;
                return;
            }
            string reason = null;
            if (gm == null) reason = "no_game_manager";
            else if (id != gmId) reason = "game_manager_rebuilt";
            else if (TimeSlowedCount(gm) == 0) reason = "abandoned";
            if (reason == null) return;
            gmId = id;
            Closing.Clear();
            Closing.AddRange(OpenFreezes.Keys);
            foreach (var f in Closing) End(f, reason);
        }

        /// <summary>Passes the game's iterator through unchanged and reports when it completes or is disposed.</summary>
        private sealed class Tracker : IEnumerator, IDisposable
        {
            private readonly IEnumerator inner;
            private readonly int id;

            public Tracker(IEnumerator inner, int id)
            {
                this.inner = inner;
                this.id = id;
            }

            public object Current => inner.Current;

            public bool MoveNext()
            {
                bool more;
                try
                {
                    more = inner.MoveNext();
                }
                catch
                {
                    End(id, "exception");
                    throw;
                }
                if (!more) End(id, "done");
                return more;
            }

            public void Reset() => inner.Reset();

            public void Dispose()
            {
                (inner as IDisposable)?.Dispose();
                End(id, "disposed");
            }
        }
    }
}
