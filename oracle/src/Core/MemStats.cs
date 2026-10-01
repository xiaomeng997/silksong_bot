using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Profiling;

namespace SsOracle.Core
{
    /// <summary>
    /// RPC "mem.stats" {objects=false, gc=false, unload=false}: where this process's memory is, to attribute the slow growth the M1 soak saw
    /// (private bytes about +35 MB/h per instance at about 730 savestate loads/h, 2026-09-30). Managed heap and GC
    /// counts, Unity's allocator totals, the sizes of the oracle's own per-scene caches, and with objects=true the number
    /// of loaded Unity objects per type (Resources.FindObjectsOfTypeAll: slow, tens of ms; never per frame). Read-only.
    /// </summary>
    internal static class MemStats
    {
        // By name: AudioClip, AnimationClip and Font live in Unity modules the plugin does not reference.
        private static readonly string[] ObjectTypeNames =
        {
            "UnityEngine.GameObject", "UnityEngine.Component", "UnityEngine.Texture2D", "UnityEngine.RenderTexture",
            "UnityEngine.Mesh", "UnityEngine.Material", "UnityEngine.Sprite", "UnityEngine.AudioClip",
            "UnityEngine.AnimationClip", "UnityEngine.Shader", "UnityEngine.Font", "UnityEngine.ScriptableObject",
        };

        private static List<Type> objectTypes;

        private static List<Type> ObjectTypes()
        {
            if (objectTypes != null) return objectTypes;
            objectTypes = new List<Type>();
            foreach (var name in ObjectTypeNames)
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    var t = asm.GetType(name, false);
                    if (t == null) continue;
                    objectTypes.Add(t);
                    break;
                }
            }
            return objectTypes;
        }

        public static void Register() => Ipc.Rpc.Register("mem.stats", Describe);

        private static object Describe(Dictionary<string, object> args)
        {
            // unload=true: start Resources.UnloadUnusedAssets (asynchronous; sample again a second later to see what it
            // freed). The game does this on its own scene transitions; a DebugMod savestate load may not.
            if (args.ContainsKey("unload") && Ipc.Rpc.Bool(args, "unload"))
                Resources.UnloadUnusedAssets();
            // gc=true: a full collection first, so managed growth that survives it is retained, not garbage not yet
            // collected (one hitch of some ms; a probe tool, not for play).
            if (args.ContainsKey("gc") && Ipc.Rpc.Bool(args, "gc"))
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
            }
            var d = new Dictionary<string, object>
            {
                ["frame"] = (long)Time.frameCount,
                ["scene"] = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                ["gc_total"] = GC.GetTotalMemory(false),
                ["gc_counts"] = new List<object> { (long)GC.CollectionCount(0), (long)GC.CollectionCount(1), (long)GC.CollectionCount(2) },
                ["mono_used"] = Profiler.GetMonoUsedSizeLong(),
                ["mono_heap"] = Profiler.GetMonoHeapSizeLong(),
                ["unity_allocated"] = Profiler.GetTotalAllocatedMemoryLong(),
                ["unity_reserved"] = Profiler.GetTotalReservedMemoryLong(),
                ["unity_unused_reserved"] = Profiler.GetTotalUnusedReservedMemoryLong(),
                ["gfx_driver"] = Profiler.GetAllocatedMemoryForGraphicsDriver(),
                ["oracle"] = new Dictionary<string, object>
                {
                    ["fsm_infos"] = (long)Entities.FsmTap.CacheSize,
                    ["ents"] = Entities.EntityRegistry.Stats(),
                },
            };
            if (args.ContainsKey("objects") && Ipc.Rpc.Bool(args, "objects"))
            {
                var counts = new Dictionary<string, object>();
                var t0 = System.Diagnostics.Stopwatch.GetTimestamp();
                foreach (var t in ObjectTypes())
                    counts[t.Name] = (long)Resources.FindObjectsOfTypeAll(t).Length;
                counts["Object"] = (long)Resources.FindObjectsOfTypeAll(typeof(UnityEngine.Object)).Length;
                d["objects"] = counts;
                // The most common Material names (an instance made by Renderer.material is named "<shared> (Instance)"):
                // which component makes the materials that pile up.
                var names = new Dictionary<string, long>();
                foreach (var m in Resources.FindObjectsOfTypeAll(typeof(Material)))
                {
                    var n = m.name ?? "";
                    names[n] = names.TryGetValue(n, out var c) ? c + 1 : 1;
                }
                var top = new List<KeyValuePair<string, long>>(names);
                top.Sort((a, b) => b.Value.CompareTo(a.Value));
                var materials = new Dictionary<string, object>();
                for (var i = 0; i < top.Count && i < 15; i++)
                    materials[top[i].Key] = top[i].Value;
                d["materials_top"] = materials;
                d["objects_ms"] = (System.Diagnostics.Stopwatch.GetTimestamp() - t0) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
            }
            return d;
        }
    }
}
