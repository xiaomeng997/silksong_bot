using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using GlobalEnums;
using HarmonyLib;
using UnityEngine;
using UnityEngine.SceneManagement;
using SsOracle.Events;

namespace SsOracle.SceneDump
{
    /// <summary>
    /// TERRAIN message (DESIGN §4.6, §3.1.9 SceneGeometry source; field sources m0 §3.2 SceneDumper): once per
    /// gameplay room after it has finished entering, plus on brain connect and on RPC "scene.dump". Contents:
    /// every collider on the TERRAIN (and SOFT_TERRAIN) layer as world outlines, including inactive ones (arena
    /// gates), static hazards (DamageHero with hazardType != ENEMY), transition gates, hazard-respawn zones,
    /// scene preloaders (they grey out Save &amp; Quit for the rest of the room, m0:C8), cutscene/battle/frost/
    /// no-clamber/camera-lock regions, harpoon anchors and cogs, the camera limits and the CustomSceneManager flags.
    ///
    /// The walk is time-sliced (<see cref="SliceBudgetUs"/> per frame) so a large room never costs one frame
    /// more than that; it is abandoned if the room changes. Vertex lists are msgpack bin: little-endian float32
    /// x, y pairs in world units.
    /// </summary>
    internal sealed class SceneDumper : MonoBehaviour
    {
        public const long SliceBudgetUs = 400;
        private const int TerrainLayer = (int)PhysLayers.TERRAIN;
        private const int SoftTerrainLayer = (int)PhysLayers.SOFT_TERRAIN;
        private const int HeroAttackLayer = (int)PhysLayers.HERO_ATTACK;
        private const int InteractiveLayer = (int)PhysLayers.INTERACTIVE_OBJECT;

        private static SceneDumper instance;

        // STATE "room" status.
        public static int LastSeq { get; private set; }
        public static int LastTransition { get; private set; } = -1;
        public static bool Busy => instance != null && instance.running;

        private static readonly AccessTools.FieldRef<ScenePreloader, string> PreloaderScene =
            AccessTools.FieldRefAccess<ScenePreloader, string>("sceneNameToLoad");
        private static readonly AccessTools.FieldRef<ScenePreloader, TriggerEnterEvent> PreloaderTrigger =
            AccessTools.FieldRefAccess<ScenePreloader, TriggerEnterEvent>("activateTrigger");
        private static readonly AccessTools.FieldRef<ScenePreloader, bool> PreloaderStarted =
            AccessTools.FieldRefAccess<ScenePreloader, bool>("startedLoad");
        private static readonly AccessTools.FieldRef<ScenePreloader, PlayerDataTest> PreloaderTest =
            AccessTools.FieldRefAccess<ScenePreloader, PlayerDataTest>("test");
        private static readonly AccessTools.FieldRef<ScenePreloader, TransitionPoint[]> PreloaderWhiteList =
            AccessTools.FieldRefAccess<ScenePreloader, TransitionPoint[]>("entryGateWhiteList");
        private static readonly AccessTools.FieldRef<ScenePreloader, TransitionPoint[]> PreloaderBlackList =
            AccessTools.FieldRefAccess<ScenePreloader, TransitionPoint[]>("entryGateBlackList");
        private static readonly AccessTools.FieldRef<FrostRegion, float> FrostAddOnEnter =
            AccessTools.FieldRefAccess<FrostRegion, float>("addOnEnter");

        private readonly Ipc.MsgPackWriter writer = new Ipc.MsgPackWriter(256 * 1024);
        private readonly List<Ipc.Rpc.Reply> waiters = new List<Ipc.Rpc.Reply>();
        private readonly List<GameObject> roots = new List<GameObject>();
        private readonly List<Collider2D> colliders = new List<Collider2D>(1024);
        private readonly List<Collider2D> zoneColliders = new List<Collider2D>(8);
        private readonly List<Shape> zoneShapes = new List<Shape>(8);
        private byte[] binScratch = new byte[4096];

        private bool running;
        private int runningSince;
        private Coroutine routine;
        private string reason;
        private int seq;

        /// <summary>A dump older than this many frames is assumed dead (it died on an exception) and restarted.</summary>
        private const int StaleDumpFrames = 600;

        public static void Install(GameObject host)
        {
            instance = host.AddComponent<SceneDumper>();
            FlowTap.RoomEntered += gm => instance.Request("enter", null);
            FlowTap.RoomLeaving += () => instance.Cancel("room changed before the dump finished");
            EventsRunner.BrainConnected += () =>
            {
                if (FlowTap.RoomIsEntered) instance.Request("connect", null);
            };
            Ipc.Rpc.Register("scene.dump", (args, reply) => instance.Request("rpc", reply));
            Export.FrameExporter.Register(new RoomExporter());
        }

        private void Request(string why, Ipc.Rpc.Reply reply)
        {
            if (reply != null) waiters.Add(reply);
            if (!Tap.Active && waiters.Count == 0) return; // nobody would receive it
            if (running && Time.frameCount - runningSince < StaleDumpFrames)
            {
                // The dump in progress is for this room and will be sent; an RPC just waits for it.
                return;
            }
            if (running)
            {
                // Stale: restart below, keeping the waiters (they get this dump's result).
                if (routine != null) StopCoroutine(routine);
                routine = null;
                running = false;
            }
            var gm = GameManager._instance;
            if (gm == null || !gm.IsGameplayScene() || !FlowTap.RoomIsEntered)
            {
                FailWaiters("not in an entered gameplay room");
                return;
            }
            reason = why;
            running = true;
            runningSince = Time.frameCount;
            var r = StartCoroutine(Dump());
            if (running) routine = r; // a small room may finish inside StartCoroutine
        }

        private void Cancel(string why)
        {
            if (!running) return;
            if (routine != null) StopCoroutine(routine);
            routine = null;
            running = false;
            FailWaiters(why);
        }

        private void FailWaiters(string why)
        {
            foreach (var r in waiters) r.Fail(why);
            waiters.Clear();
        }

        // ---- collected room data ---------------------------------------------------------------------------

        private struct Solid
        {
            public int Id, Layer, Flags, ShapeFrom, ShapeTo;
            public string Go;
            public bool On;
            public byte Body;
        }

        private struct Hazard
        {
            public int Id, Damage, DamageFlags, ShapeFrom, ShapeTo;
            public string Go, Type;
            public bool On, Tink, Trigger;
            public byte Body;
        }

        // Solid flags.
        private const int FlagNonSlider = 1, FlagSteepSlope = 2, FlagSlideSurface = 4, FlagNonBouncer = 8, FlagBreakable = 16, FlagSoftTerrain = 32;

        private readonly List<Shape> shapes = new List<Shape>(2048);
        private readonly List<Solid> solids = new List<Solid>(512);
        private readonly List<Hazard> hazards = new List<Hazard>(64);
        private readonly Dictionary<string, List<object>> zones = new Dictionary<string, List<object>>();
        private readonly HashSet<int> sceneHandles = new HashSet<int>();
        private readonly List<string> scannedScenes = new List<string>();
        private readonly List<Scene> scenesToScan = new List<Scene>();

        private IEnumerator Dump()
        {
            var total = Stopwatch.StartNew();
            var slice = Stopwatch.StartNew();
            long workTicks = 0;
            var slices = 1;
            var budget = SliceBudgetUs * Stopwatch.Frequency / 1_000_000;
            var startFrame = Time.frameCount;
            var transition = FlowTap.TransitionSeq;
            var gm = GameManager._instance;
            var active = SceneManager.GetActiveScene();

            shapes.Clear();
            solids.Clear();
            hazards.Clear();
            zones.Clear();
            sceneHandles.Clear();
            scannedScenes.Clear();
            scenesToScan.Clear();
            var verts = 0;
            var seen = 0;

            // The room is the active scene plus its sub-scenes ("<base>_boss", "_preload", ...: m0 §2.7).
            var baseName = gm.sceneName ?? active.name;
            var loaded = new List<string>();
            for (var i = 0; i < SceneManager.sceneCount; i++)
            {
                var s = SceneManager.GetSceneAt(i);
                if (!s.isLoaded) continue;
                loaded.Add(s.name);
                if (s == active || s.name.StartsWith(baseName + "_", StringComparison.Ordinal))
                {
                    sceneHandles.Add(s.handle);
                    scannedScenes.Add(s.name);
                    scenesToScan.Add(s);
                }
            }

            for (var si = 0; si < scenesToScan.Count; si++)
            {
                var scene = scenesToScan[si];
                if (!scene.IsValid() || !scene.isLoaded) continue;
                roots.Clear();
                scene.GetRootGameObjects(roots);
                for (var r = 0; r < roots.Count; r++)
                {
                    var root = roots[r];
                    if (root == null) continue;
                    colliders.Clear();
                    root.GetComponentsInChildren(true, colliders);
                    for (var c = 0; c < colliders.Count; c++)
                    {
                        if (slice.ElapsedTicks > budget)
                        {
                            workTicks += slice.ElapsedTicks;
                            yield return null;
                            if (!StillCurrent(gm, transition)) { Abort("room changed"); yield break; }
                            slice.Restart();
                            slices++;
                        }
                        var col = colliders[c];
                        if (col == null) continue;
                        seen++;
                        try { verts += Collect(col); }
                        catch (Exception e) { Core.Plugin.Log.LogWarning($"SceneDumper: collider {col.name} skipped: {e.Message}"); }
                    }
                }
            }

            // Rare component types: one type query per step.
            var steps = new Func<int>[]
            {
                CollectGates, CollectRespawns, CollectPreloaders, CollectBattles, CollectFrost, CollectNoClamber,
                CollectCamLocks, CollectCogs, CollectCutscenes,
            };
            foreach (var step in steps)
            {
                if (slice.ElapsedTicks > budget)
                {
                    workTicks += slice.ElapsedTicks;
                    yield return null;
                    if (!StillCurrent(gm, transition)) { Abort("room changed"); yield break; }
                    slice.Restart();
                    slices++;
                }
                try { verts += step(); }
                catch (Exception e) { Core.Plugin.Log.LogError($"SceneDumper: {step.Method.Name} failed: {e.Message}"); }
            }

            workTicks += slice.ElapsedTicks;
            int bytes;
            try
            {
                bytes = Serialize(gm, active, loaded, transition, startFrame, seen, verts, total, workTicks, slices);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError("SceneDumper: serializing TERRAIN failed: " + e);
                Abort("serializing TERRAIN failed: " + e.Message);
                yield break;
            }
            running = false;
            routine = null;
            LastSeq = seq;
            LastTransition = transition;
            var result = new Dictionary<string, object>
            {
                ["seq"] = seq, ["scene"] = active.name, ["bytes"] = bytes, ["solids"] = solids.Count, ["hazards"] = hazards.Count,
                ["gates"] = zones.TryGetValue("gates", out var g) ? g.Count : 0, ["verts"] = verts,
                ["ms"] = total.Elapsed.TotalMilliseconds, ["work_ms"] = workTicks * 1000.0 / Stopwatch.Frequency, ["slices"] = slices,
            };
            foreach (var w in waiters) w.Ok(result);
            waiters.Clear();
            Core.Plugin.Log.LogInfo($"TERRAIN #{seq} {active.name} ({reason}): {solids.Count} solids, {hazards.Count} hazards, {verts} verts, " +
                                    $"{bytes} B, {slices} slices, work {workTicks * 1000.0 / Stopwatch.Frequency:F2} ms");
        }

        private static bool StillCurrent(GameManager gm, int transition) =>
            GameManager._instance == gm && gm != null && FlowTap.TransitionSeq == transition;

        private void Abort(string why)
        {
            running = false;
            routine = null;
            FailWaiters(why);
        }

        private static byte BodyOf(Collider2D col)
        {
            var rb = col.attachedRigidbody;
            if (rb == null) return 0;
            switch (rb.bodyType)
            {
                case RigidbodyType2D.Static: return 0;
                case RigidbodyType2D.Kinematic: return 1;
                default: return 2;
            }
        }

        /// <summary>Terrain, static-hazard and Clawline-anchor colliders; returns the vertex count added.</summary>
        private int Collect(Collider2D col)
        {
            var go = col.gameObject;
            var layer = go.layer;
            var anchorVerts = layer == HeroAttackLayer || layer == InteractiveLayer ? CollectAnchor(col, layer) : 0;
            var terrain = (layer == TerrainLayer || layer == SoftTerrainLayer) && !col.isTrigger;
            go.TryGetComponent(out DamageHero dh);
            var hazard = dh != null && dh.hazardType != HazardType.ENEMY;
            if (!terrain && !hazard) return anchorVerts;
            // Parts merged into a CompositeCollider2D are exported through the composite itself.
            if (col.compositeOperation != Collider2D.CompositeOperation.None && col.composite != null) return anchorVerts;

            var from = shapes.Count;
            var n = ColliderGeometry.Extract(col, shapes);
            var to = shapes.Count;
            var on = col.enabled && go.activeInHierarchy;
            var body = BodyOf(col);
            if (terrain)
            {
                var flags = 0;
                if (go.TryGetComponent(out NonSlider ns) && ns.IsActive) flags |= FlagNonSlider;
                if (SteepSlope.IsSteepSlope(go)) flags |= FlagSteepSlope;
                if (go.TryGetComponent(out SlideSurface _)) flags |= FlagSlideSurface;
                if (go.TryGetComponent(out NonBouncer _)) flags |= FlagNonBouncer;
                if (go.TryGetComponent(out Breakable _)) flags |= FlagBreakable;
                if (layer == SoftTerrainLayer) flags |= FlagSoftTerrain;
                solids.Add(new Solid { Id = col.GetInstanceID(), Go = go.name, Layer = layer, On = on, Body = body, Flags = flags, ShapeFrom = from, ShapeTo = to });
            }
            if (hazard)
            {
                hazards.Add(new Hazard
                {
                    Id = col.GetInstanceID(), Go = go.name, On = on && dh.enabled, Type = dh.hazardType.ToString(), Damage = dh.damageDealt,
                    DamageFlags = (int)dh.damagePropertyFlags, Tink = go.TryGetComponent(out TinkEffect _), Trigger = col.isTrigger,
                    Body = body, ShapeFrom = from, ShapeTo = to,
                });
            }
            return n + anchorVerts;
        }

        /// <summary>
        /// Clawline anchors, classified the way HarpoonDashRayCheck classifies what its non-terrain rays hit
        /// (layers ENEMIES | HERO_ATTACK | INTERACTIVE_OBJECT, triggers included): "pod" (tag "Bounce Pod", a
        /// BouncePod or a HarpoonHook), "ring" (tag "Harpoon Ring"), "tink" (HERO_ATTACK with a TinkEffect that
        /// allows hooking). Hooking an enemy (layer ENEMIES) is the entity export's business.
        /// </summary>
        private int CollectAnchor(Collider2D col, int layer)
        {
            var go = col.gameObject;
            string kind = null;
            if (col.CompareTag("Bounce Pod") || go.TryGetComponent(out BouncePod _) || go.TryGetComponent(out HarpoonHook _)) kind = "pod";
            else if (col.CompareTag("Harpoon Ring")) kind = "ring";
            else if (layer == HeroAttackLayer && go.TryGetComponent(out TinkEffect tink) && !tink.noHarpoonHook) kind = "tink";
            if (kind == null) return 0;
            zoneShapes.Clear();
            var n = ColliderGeometry.Extract(col, zoneShapes);
            var d = new Dictionary<string, object>
            {
                ["go"] = go.name,
                ["id"] = col.GetInstanceID(),
                ["kind"] = kind,
                ["on"] = col.enabled && go.activeInHierarchy,
                ["trigger"] = col.isTrigger,
                ["body"] = (int)BodyOf(col),
                ["pos"] = (Vector2)go.transform.position,
            };
            if (zoneShapes.Count > 0)
            {
                d["shapes"] = ShapeObjects(zoneShapes, 0, zoneShapes.Count);
                d["aabb"] = ColliderGeometry.Bounds(zoneShapes, 0, zoneShapes.Count);
            }
            Zone("harpoon").Add(d);
            return n;
        }

        // ---- rare components ------------------------------------------------------------------------------

        private List<T> Find<T>() where T : Component
        {
            var list = new List<T>();
            foreach (var c in FindObjectsByType<T>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                if (c != null && sceneHandles.Contains(c.gameObject.scene.handle)) list.Add(c);
            return list;
        }

        private List<object> Zone(string key)
        {
            if (!zones.TryGetValue(key, out var list)) zones[key] = list = new List<object>();
            return list;
        }

        /// <summary>Common fields of a zone-like component: name, active, position, and its collider outlines.</summary>
        private Dictionary<string, object> Base(Component c, ref int verts, GameObject shapesFrom = null)
        {
            var go = c.gameObject;
            var d = new Dictionary<string, object>
            {
                ["go"] = go.name,
                ["on"] = go.activeInHierarchy && (!(c is Behaviour b) || b.enabled),
                ["pos"] = (Vector2)go.transform.position,
            };
            zoneColliders.Clear();
            zoneShapes.Clear();
            (shapesFrom != null ? shapesFrom : go).GetComponents(zoneColliders);
            foreach (var col in zoneColliders)
                if (col != null) verts += ColliderGeometry.Extract(col, zoneShapes);
            if (zoneShapes.Count > 0)
            {
                d["shapes"] = ShapeObjects(zoneShapes, 0, zoneShapes.Count);
                d["aabb"] = ColliderGeometry.Bounds(zoneShapes, 0, zoneShapes.Count);
            }
            return d;
        }

        private static List<object> ShapeObjects(List<Shape> list, int from, int to)
        {
            var o = new List<object>(to - from);
            for (var i = from; i < to; i++)
            {
                var s = list[i];
                var bytes = new byte[s.Verts.Length * 4];
                Buffer.BlockCopy(s.Verts, 0, bytes, 0, bytes.Length);
                var d = new Dictionary<string, object> { ["k"] = s.Kind, ["v"] = bytes };
                if (s.Radius > 0f) d["r"] = s.Radius;
                o.Add(d);
            }
            return o;
        }

        private int CollectGates()
        {
            var verts = 0;
            var listed = TransitionPoint.TransitionPoints;
            foreach (var tp in Find<TransitionPoint>())
            {
                var d = Base(tp, ref verts);
                d["target"] = tp.targetScene;
                d["entry"] = tp.entryPoint;
                d["side"] = tp.GetGatePosition().ToString();
                d["door"] = tp.isADoor;
                d["inactive"] = tp.isInactive;
                d["non_hazard"] = tp.nonHazardGate;
                d["listed"] = listed != null && listed.Contains(tp);
                if (tp.respawnMarker != null) d["respawn"] = (Vector2)tp.respawnMarker.transform.position;
                Zone("gates").Add(d);
            }
            return verts;
        }

        private int CollectRespawns()
        {
            var verts = 0;
            foreach (var t in Find<HazardRespawnTrigger>())
            {
                var d = Base(t, ref verts);
                d["fire_once"] = t.fireOnce;
                if (t.respawnMarker != null) d["marker"] = (Vector2)t.respawnMarker.transform.position;
                Zone("respawns").Add(d);
            }
            return verts;
        }

        /// <summary>
        /// ScenePreloaders grey out Save &amp; Quit from the moment they start loading until the room is left
        /// (m0:C8). One without an activateTrigger starts in Start(); one with a trigger starts when Hornet enters
        /// it ("shapes" are the trigger's). Either way it only starts if its PlayerDataTest passes and the entry
        /// gate passes the white/black lists (ScenePreloader.StartPreload).
        /// </summary>
        private int CollectPreloaders()
        {
            var verts = 0;
            foreach (var p in Find<ScenePreloader>())
            {
                var trigger = PreloaderTrigger(p);
                var d = Base(p, ref verts, trigger != null ? trigger.gameObject : null);
                d["loads"] = PreloaderScene(p);
                d["started"] = PreloaderStarted(p);
                d["has_trigger"] = trigger != null;
                if (trigger != null) d["trigger_on"] = trigger.isActiveAndEnabled;
                var test = PreloaderTest(p);
                if (test != null)
                {
                    try { d["test_ok"] = test.IsFulfilled; }
                    catch (Exception) { /* a test on a missing PlayerData field: leave it out */ }
                }
                d["gate_white"] = GateNames(PreloaderWhiteList(p));
                d["gate_black"] = GateNames(PreloaderBlackList(p));
                Zone("preloaders").Add(d);
            }
            return verts;
        }

        private static List<object> GateNames(TransitionPoint[] gates)
        {
            var names = new List<object>();
            if (gates == null) return names;
            foreach (var g in gates)
                if (g != null) names.Add(g.gameObject.name);
            return names;
        }

        private int CollectBattles()
        {
            var verts = 0;
            foreach (var bs in Find<BattleScene>())
            {
                var d = Base(bs, ref verts);
                d["no_end_slomo"] = bs.noEndSlomo;
                d["waves"] = bs.waves != null ? bs.waves.Count : 0;
                d["set_pd_bool"] = bs.setPDBoolOnEnd;
                if (bs.gates != null)
                {
                    // Arena walls are TERRAIN colliders under "gates" (in "solids", usually inactive until the fight).
                    var ids = new List<object>();
                    foreach (var c in bs.gates.GetComponentsInChildren<Collider2D>(true)) ids.Add(c.GetInstanceID());
                    d["gate_ids"] = ids;
                }
                Zone("battles").Add(d);
            }
            return verts;
        }

        private int CollectFrost()
        {
            var verts = 0;
            foreach (var f in Find<FrostRegion>())
            {
                var d = Base(f, ref verts);
                d["frost_speed"] = f.FrostSpeed;
                d["add_on_enter"] = FrostAddOnEnter(f);
                Zone("frost").Add(d);
            }
            return verts;
        }

        private int CollectNoClamber()
        {
            var verts = 0;
            foreach (var r in Find<NoClamberRegion>())
            {
                var d = Base(r, ref verts);
                d["auto"] = r is AutoNoClamberRegion;
                Zone("no_clamber").Add(d);
            }
            return verts;
        }

        private int CollectCamLocks()
        {
            var verts = 0;
            foreach (var a in Find<CameraLockArea>())
            {
                var d = Base(a, ref verts);
                d["x_min"] = a.cameraXMin;
                d["y_min"] = a.cameraYMin;
                d["x_max"] = a.cameraXMax;
                d["y_max"] = a.cameraYMax;
                d["space"] = a.positionSpace.ToString();
                d["no_look_up"] = a.preventLookUp;
                d["no_look_down"] = a.preventLookDown;
                d["priority"] = a.priority;
                Zone("cam_locks").Add(d);
            }
            return verts;
        }

        private int CollectCogs()
        {
            var verts = 0;
            foreach (var c in Find<CogMultiHitter>()) Zone("cogs").Add(Base(c, ref verts));
            return verts;
        }

        private int CollectCutscenes()
        {
            var verts = 0;
            foreach (var c in Find<InGameCutsceneInfo>()) Zone("cutscene_info").Add(Base(c, ref verts));
            return verts;
        }

        // ---- message ---------------------------------------------------------------------------------------

        private int Serialize(GameManager gm, Scene active, List<string> loaded, int transition, int startFrame,
                              int seen, int verts, Stopwatch total, long workTicks, int slices)
        {
            var w = writer;
            w.Reset();
            w.MapHeader(15 + zones.Count);
            w.Key("seq"); w.Int(++seq);
            w.Key("reason"); w.Str(reason);
            w.Key("frame"); w.Int(startFrame);
            w.Key("transition"); w.Int(transition);
            w.Key("scene_raw"); w.Str(active.name);
            w.Key("scene"); w.Str(gm.sceneName);
            w.Key("scenes"); Ipc.FramedServer.WriteObject(w, scannedScenes);
            w.Key("loaded"); Ipc.FramedServer.WriteObject(w, loaded);
            w.Key("cam"); Ipc.FramedServer.WriteObject(w, CameraInfo(gm));
            w.Key("sm"); Ipc.FramedServer.WriteObject(w, SceneManagerInfo(gm));
            w.Key("cutscene"); w.Bool(InGameCutsceneInfo.IsInCutscene);
            w.Key("solids"); WriteSolids(w);
            w.Key("hazards"); WriteHazards(w);
            foreach (var kv in zones)
            {
                w.Key(kv.Key);
                Ipc.FramedServer.WriteObject(w, kv.Value);
            }
            w.Key("layers"); Ipc.FramedServer.WriteObject(w, new Dictionary<string, object> { ["terrain"] = TerrainLayer, ["soft_terrain"] = SoftTerrainLayer });
            w.Key("stats");
            w.MapHeader(6);
            w.Key("colliders_seen"); w.Int(seen);
            w.Key("verts"); w.Int(verts);
            w.Key("slices"); w.Int(slices);
            w.Key("frames"); w.Int(Time.frameCount - startFrame + 1);
            w.Key("work_ms"); w.Double(workTicks * 1000.0 / Stopwatch.Frequency);
            w.Key("ms"); w.Double(total.Elapsed.TotalMilliseconds);
            if (Tap.Active) Ipc.FramedServer.Instance.Send(Ipc.Protocol.MsgType.Terrain, w);
            return w.Length;
        }

        private void WriteShapes(Ipc.MsgPackWriter w, int from, int to)
        {
            w.ArrayHeader(to - from);
            for (var i = from; i < to; i++)
            {
                var s = shapes[i];
                w.MapHeader(s.Radius > 0f ? 3 : 2);
                w.Key("k"); w.Str(s.Kind);
                w.Key("v");
                var n = s.Verts.Length * 4;
                if (binScratch.Length < n) binScratch = new byte[Math.Max(n, binScratch.Length * 2)];
                Buffer.BlockCopy(s.Verts, 0, binScratch, 0, n);
                w.Bin(binScratch, 0, n);
                if (s.Radius > 0f) { w.Key("r"); w.Float(s.Radius); }
            }
        }

        private void WriteSolids(Ipc.MsgPackWriter w)
        {
            w.ArrayHeader(solids.Count);
            foreach (var s in solids)
            {
                w.MapHeader(7);
                w.Key("id"); w.Int(s.Id);
                w.Key("go"); w.Str(s.Go);
                w.Key("layer"); w.Int(s.Layer);
                w.Key("on"); w.Bool(s.On);
                w.Key("body"); w.Int(s.Body);
                w.Key("flags"); w.Int(s.Flags);
                w.Key("shapes"); WriteShapes(w, s.ShapeFrom, s.ShapeTo);
            }
        }

        private void WriteHazards(Ipc.MsgPackWriter w)
        {
            w.ArrayHeader(hazards.Count);
            foreach (var h in hazards)
            {
                w.MapHeader(10);
                w.Key("id"); w.Int(h.Id);
                w.Key("go"); w.Str(h.Go);
                w.Key("on"); w.Bool(h.On);
                w.Key("hazard"); w.Str(h.Type);
                w.Key("damage"); w.Int(h.Damage);
                w.Key("flags"); w.Int(h.DamageFlags);
                w.Key("tink"); w.Bool(h.Tink);
                w.Key("trigger"); w.Bool(h.Trigger);
                w.Key("body"); w.Int(h.Body);
                w.Key("shapes"); WriteShapes(w, h.ShapeFrom, h.ShapeTo);
            }
        }

        private static Dictionary<string, object> CameraInfo(GameManager gm)
        {
            var d = new Dictionary<string, object> { ["gm_scene_w"] = gm.sceneWidth, ["gm_scene_h"] = gm.sceneHeight };
            var cc = gm.cameraCtrl;
            if (cc != null)
            {
                d["scene_w"] = cc.sceneWidth;
                d["scene_h"] = cc.sceneHeight;
                d["x_limit"] = cc.xLimit;
                d["y_limit"] = cc.yLimit;
                d["mode"] = cc.mode.ToString();
                // Camera centre clamp (m0 §2.7): x in [14.6, x_limit], y in [8.3, y_limit].
                d["x_min"] = 14.6f;
                d["y_min"] = 8.3f;
            }
            return d;
        }

        private static Dictionary<string, object> SceneManagerInfo(GameManager gm)
        {
            var d = new Dictionary<string, object>();
            var sm = gm.sm;
            if (sm == null) return d;
            d["scene_type"] = sm.sceneType.ToString();
            d["map_zone"] = sm.mapZone.ToString();
            d["hero_keep_health"] = sm.HeroKeepHealth;
            d["force_not_memory"] = sm.ForceNotMemory;
            d["memory"] = gm.IsMemoryScene();
            d["frost_speed"] = sm.FrostSpeed;
            d["darkness"] = sm.darknessLevel;
            d["windy"] = sm.isWindy;
            d["tremor"] = sm.isTremorZone;
            d["environment"] = sm.environmentType.ToString();
            return d;
        }

        /// <summary>STATE "room": {seq: last TERRAIN sent, transition: the room it was for, busy: a dump is in progress}.</summary>
        private sealed class RoomExporter : Export.IExporter
        {
            public string Key => "room";

            public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
            {
                w.MapHeader(4);
                w.Key("seq"); w.Int(LastSeq);
                w.Key("transition"); w.Int(LastTransition);
                w.Key("current"); w.Int(FlowTap.TransitionSeq);
                w.Key("busy"); w.Bool(Busy);
            }
        }
    }
}
