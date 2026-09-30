using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Threading;
using HarmonyLib;
using HutongGames.PlayMaker;

namespace SsOracle.Events
{
    /// <summary>
    /// Shared plumbing for the EventTap hooks (DESIGN §3.1.1 EventTap): numbered emission into STATE "ev",
    /// caller summaries, PlayMaker attribution and fault-tolerant Harmony patching. Every event payload gets
    /// "n", a per-process sequence number, so the brain can tell when a dropped STATE took events with it.
    /// </summary>
    internal static class Tap
    {
        /// <summary>
        /// Observer prefixes run before every guard prefix (Priority.First is 800), so an attempt that a guard
        /// later blocks (LethalBlock on Die, SaveSuppression on SaveGame) is still recorded.
        /// </summary>
        public const int PrefixPriority = Priority.First + 100;

        /// <summary>Observer postfixes run after every other postfix, so they see the final state.</summary>
        public const int PostfixPriority = Priority.Last;

        private static readonly Assembly Own = typeof(Tap).Assembly;
        private static readonly ConcurrentQueue<KeyValuePair<string, Dictionary<string, object>>> Foreign =
            new ConcurrentQueue<KeyValuePair<string, Dictionary<string, object>>>();

        private static int mainThreadId;
        private static long seq;
        private static int failedHooks;

        public static long Seq => seq;
        public static int FailedHooks => failedHooks;

        public static void Init() => mainThreadId = Thread.CurrentThread.ManagedThreadId;

        /// <summary>
        /// True while a brain is connected. FrameExporter throws events away otherwise, so hooks check this
        /// before paying for a payload (and especially for a stack walk).
        /// </summary>
        public static bool Active
        {
            get
            {
                var s = Ipc.FramedServer.Instance;
                return s != null && s.Connected;
            }
        }

        public static Dictionary<string, object> Data(int capacity = 8) => new Dictionary<string, object>(capacity);

        /// <summary>
        /// Record an event for the current frame's STATE. Callbacks from the save worker are not on the main
        /// thread (and Time.frameCount is main-thread only), so those are queued and stamped when drained.
        /// </summary>
        public static void Emit(string kind, Dictionary<string, object> data)
        {
            if (Thread.CurrentThread.ManagedThreadId != mainThreadId)
            {
                Foreign.Enqueue(new KeyValuePair<string, Dictionary<string, object>>(kind, data));
                return;
            }
            data["n"] = ++seq;
            Export.FrameExporter.Emit(kind, data);
        }

        /// <summary>Main thread, once per frame: emit events queued by other threads.</summary>
        public static void DrainForeign()
        {
            while (Foreign.TryDequeue(out var e)) Emit(e.Key, e.Value);
        }

        /// <summary>
        /// A short managed stack summary: the first <paramref name="max"/> frames outside SsOracle, Harmony,
        /// MonoMod, System and UnityEngine plumbing. A patched method shows up once as its original name. The
        /// walk stops at the first PlayMaker core frame: the action frame above it (and <see cref="FsmNow"/>)
        /// already say which FSM did it. Costs tens of microseconds, so only call it when something changed.
        /// </summary>
        public static List<string> Caller(int max = 6)
        {
            var list = new List<string>(max);
            StackTrace st;
            try { st = new StackTrace(1, false); }
            catch { return list; }
            var n = st.FrameCount;
            for (var i = 0; i < n && list.Count < max; i++)
            {
                var m = st.GetFrame(i)?.GetMethod();
                if (m == null) continue;
                var t = m.DeclaringType;
                var dmdType = t != null && t.Name.StartsWith("DMD<", StringComparison.Ordinal);
                if (t == null || dmdType || t.Assembly.IsDynamic || m.Name.StartsWith("DMD<", StringComparison.Ordinal))
                {
                    // A patched original. Depending on MonoMod's generator this is a DynamicMethod (no type, name
                    // "DMD<Original>?hash") or a method of a Cecil-built "DMD<Type::Original>" type loaded from bytes.
                    var dyn = DynamicName(dmdType ? t.Name : m.Name);
                    if (dyn != null && (list.Count == 0 || list[list.Count - 1] != dyn)) list.Add(dyn);
                    continue;
                }
                if (t.Assembly == Own) continue;
                var ns = t.Namespace ?? "";
                if (ns.StartsWith("HarmonyLib", StringComparison.Ordinal) || ns.StartsWith("MonoMod", StringComparison.Ordinal) ||
                    ns.StartsWith("System", StringComparison.Ordinal) || ns.StartsWith("UnityEngine", StringComparison.Ordinal))
                    continue;
                var name = Format(t, m);
                if (list.Count > 0 && list[list.Count - 1] == name) continue; // patched original + its trampoline
                list.Add(name);
                if (ns == "HutongGames.PlayMaker") break;
            }
            return list;
        }

        // Iterator and lambda classes ("<Die>d__331" nested in HeroController) read as "HeroController.Die".
        private static string Format(Type t, MethodBase m)
        {
            var tn = t.Name;
            if (tn.Length > 1 && tn[0] == '<' && t.DeclaringType != null)
            {
                var close = tn.IndexOf('>');
                return t.DeclaringType.Name + "." + (close > 1 ? tn.Substring(1, close - 1) : tn);
            }
            return tn + "." + m.Name;
        }

        // MonoMod names a patched method's replacement "DMD<Original>?hash" or "DMD<Type::Original>".
        private static string DynamicName(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            if (!name.StartsWith("DMD<", StringComparison.Ordinal)) return name;
            var close = name.LastIndexOf('>');
            if (close <= 4) return name;
            return name.Substring(4, close - 4).Replace("::", ".");
        }

        /// <summary>"GameObject/Fsm/State:Action" of the PlayMaker FSM executing right now, or null (C# caller).</summary>
        public static string FsmNow()
        {
            try
            {
                var fsm = FsmExecutionStack.ExecutingFsm;
                if (fsm == null) return null;
                var action = FsmExecutionStack.ExecutingAction;
                return fsm.GameObjectName + "/" + fsm.Name + "/" + fsm.ActiveStateName +
                       (action != null ? ":" + action.GetType().Name : "");
            }
            catch
            {
                return null;
            }
        }

        /// <summary>Adds "fsm" (when an FSM is executing) and, optionally, "caller" to an event payload.</summary>
        public static void Attribute(Dictionary<string, object> d, bool withCaller, int maxFrames = 6)
        {
            var fsm = FsmNow();
            if (fsm != null) d["fsm"] = fsm;
            if (withCaller) d["caller"] = Caller(maxFrames);
        }

        /// <summary>
        /// Patch one method with observer hooks. A missing target is logged as an error and skipped: the
        /// SymbolCheck package turns missing symbols into a hard failure, the tap itself degrades.
        /// </summary>
        public static bool Patch(Harmony harmony, Type type, string name, Type[] args, Type hooks,
                                 string prefix = null, string postfix = null)
        {
            MethodBase target = null;
            try
            {
                target = args == null ? AccessTools.DeclaredMethod(type, name) : AccessTools.DeclaredMethod(type, name, args);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError($"EventTap: resolving {type.FullName}.{name} failed: {e.Message}");
            }
            if (target == null)
            {
                failedHooks++;
                Core.Plugin.Log.LogError($"EventTap: {type.FullName}.{name} not found; hook skipped");
                return false;
            }
            try
            {
                harmony.Patch(target,
                    prefix: prefix == null ? null : new HarmonyMethod(AccessTools.Method(hooks, prefix)) { priority = PrefixPriority },
                    postfix: postfix == null ? null : new HarmonyMethod(AccessTools.Method(hooks, postfix)) { priority = PostfixPriority });
                return true;
            }
            catch (Exception e)
            {
                failedHooks++;
                Core.Plugin.Log.LogError($"EventTap: patching {type.FullName}.{name} failed: {e}");
                return false;
            }
        }

        /// <summary>Microseconds between two Stopwatch timestamps.</summary>
        public static long Us(long fromQpc, long toQpc) => (toQpc - fromQpc) * 1_000_000 / Stopwatch.Frequency;
    }

    /// <summary>
    /// Which PlayerData instance one consumer saw last. A weak reference compared with ReferenceEquals: it never
    /// keeps the object alive or uses it across frames (m0:N42), and unlike RuntimeHelpers.GetHashCode it cannot
    /// mistake a new PlayerData for the old one (Mono's identity hash comes from the address, and the non-moving
    /// GC can put a new PlayerData where a freed one lived). Each consumer owns its own instance. Main thread only.
    /// </summary>
    internal sealed class PdIdentity
    {
        private readonly WeakReference<PlayerData> last = new WeakReference<PlayerData>(null);

        /// <summary>True if <paramref name="pd"/> is the instance passed last time; otherwise remembers it and returns false.</summary>
        public bool Same(PlayerData pd)
        {
            if (last.TryGetTarget(out var seen) && ReferenceEquals(seen, pd)) return true;
            last.SetTarget(pd);
            return false;
        }
    }

    /// <summary>
    /// Enum names cached per value: Enum.ToString boxes and reflects on every call (and builds a new string for a
    /// [Flags] combination), which hooks on hot paths such as TakeDamage cannot afford.
    /// </summary>
    internal static class EnumName<T> where T : struct, Enum
    {
        private static readonly Dictionary<T, string> Names = new Dictionary<T, string>();

        public static string Of(T value)
        {
            lock (Names)
            {
                if (!Names.TryGetValue(value, out var s)) Names[value] = s = value.ToString();
                return s;
            }
        }
    }
}
