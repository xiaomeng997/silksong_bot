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
    /// gameplay room after it has finished entering, again when a sub-scene of the room loads or unloads after that
    /// (reason "subscene", see SubSceneChanged), plus on brain connect and on RPC "scene.dump". Contents:
    /// every collider on the TERRAIN (and SOFT_TERRAIN) layer as world outlines, including inactive ones (arena
    /// gates), static hazards (DamageHero, or the legacy 'damages_hero' FSM that HeroBox checks first, with
    /// hazardType != ENEMY), transition gates, hazard-respawn zones, scene preloaders (they grey out Save &amp;
    /// Quit for the rest of the room, m0:C8), cutscene/battle/frost/no-clamber/camera-lock regions, harpoon
    /// anchors and cogs, the camera limits and the CustomSceneManager flags.
    ///
    /// The walk and the message writing are time-sliced (<see cref="SliceBudgetUs"/> per frame, checked per
    /// GameObject, zone and outline entry) so a large room never costs one frame much more than that; the dump is
    /// abandoned if the room changes. The first slice runs on the frame after the request, never inside the game's
    /// FinishedEnteringScene call. The work done in the current frame is reported as STATE "room".work_us. Not
    /// split: one collider's outline (a huge composite or tilemap goes through Collider2D.GetShapes at once).
    /// Vertex lists are msgpack bin: little-endian float32 x, y pairs in world units.
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

        // Dump work done in one frame (the coroutine resumes before the end-of-frame STATE build).
        private static int workFrame = -1;
        private static long workFrameTicks;

        /// <summary>Microseconds of dump work done in frame <paramref name="frame"/> so far.</summary>
        public static long WorkUs(long frame) => workFrame == frame ? workFrameTicks * 1_000_000 / Stopwatch.Frequency : 0;

        private static void NoteWork(long ticks)
        {
            var f = Time.frameCount;
            if (f != workFrame)
            {
                workFrame = f;
                workFrameTicks = 0;
            }
            workFrameTicks += ticks;
        }

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
        private readonly List<Transform> walk = new List<Transform>(512);
        private readonly List<Component> comps = new List<Component>(16);
        private readonly List<Collider2D> colliders = new List<Collider2D>(8);
        private readonly List<Component> rare = new List<Component>(64);
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
            SceneManager.sceneLoaded += (scene, mode) => instance.SubSceneChanged(scene, "loaded");
            SceneManager.sceneUnloaded += scene => instance.SubSceneChanged(scene, "unloaded");
            Export.FrameExporter.Register(new RoomExporter());
        }

        /// <summary>A sub-scene of the room "baseName" ("Bone_05_boss" of "Bone_05"; m0 §2.7); the dump scans the
        /// active scene and these (pure; oracle/tests/EntitiesCheck).</summary>
        public static bool IsSubScene(string name, string baseName) =>
            !string.IsNullOrEmpty(name) && !string.IsNullOrEmpty(baseName) && name.Length > baseName.Length + 1
            && name.StartsWith(baseName, StringComparison.Ordinal) && name[baseName.Length] == '_';

        /// <summary>
        /// A sub-scene of the current room that loads (or unloads) after the room has finished entering makes the dump
        /// taken at entry stale, so the room is dumped again ("subscene") and room.gates is nil until that dump is
        /// committed. DebugMod's savestate load does this: once the transition is over it loads the state's extra scenes
        /// itself (SaveState.LoadStateCoro, LoadDuped: Bone_05_boss, which holds both "Threaded Bell Gate"s and "Wall"),
        /// after GameManager.FinishedEnteringScene; a SceneAdditiveLoadConditional outside a SceneLoad sequence also
        /// loads its scene from Start. m2_exports probe, 2026-10-02: a load of bellbeast_arena from Bonetown gave
        /// TERRAIN "enter" with 28 solids and room.gates without the gates; a reload inside Bone_05 gave 31.
        /// </summary>
        private void SubSceneChanged(Scene scene, string what)
        {
            try
            {
                if (!FlowTap.RoomIsEntered) return; // in a transition: the entry dump comes after it
                var gm = GameManager._instance;
                if (gm == null || !gm.IsGameplayScene()) return;
                var active = SceneManager.GetActiveScene();
                if (scene == active || !IsSubScene(scene.name, gm.sceneName ?? active.name)) return;
                Core.Plugin.Log.LogInfo($"TERRAIN: {scene.name} {what} after {gm.sceneName} was entered: dumping the room again");
                GateWatch.Invalidate();
                Request("subscene", null, restart: true);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogWarning($"SceneDumper: sub-scene {what} handler failed: {e.Message}");
            }
        }

        /// <param name="restart">A dump in progress may have listed the room's scenes already: start over.</param>
        private void Request(string why, Ipc.Rpc.Reply reply, bool restart = false)
        {
            if (reply != null) waiters.Add(reply);
            if (!Tap.Active && waiters.Count == 0) return; // nobody would receive it
            if (running && !restart && Time.frameCount - runningSince < StaleDumpFrames)
            {
                // The dump in progress is for this room and will be sent; an RPC just waits for it.
                return;
            }
            if (running)
            {
                // Stale or restarted: start over below, keeping the waiters (they get the new dump's result).
                if (routine != null) StopCoroutine(routine);
                routine = null;
                running = false;
                ReleaseObjects();
                GateWatch.Discard();
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
            routine = StartCoroutine(Dump());
        }

        private void Cancel(string why)
        {
            if (!running) return;
            if (routine != null) StopCoroutine(routine);
            routine = null;
            running = false;
            ReleaseObjects();
            GateWatch.Discard();
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
            public string Go, Type, Src;
            public bool On, Tink, Trigger;
            public byte Body;
        }

        /// <summary>What one GameObject carries, from a single GetComponents call (instead of a TryGetComponent per type).</summary>
        private struct GoInfo
        {
            public DamageHero Dh;
            public PlayMakerFSM DamagesHeroFsm;
            public bool FsmRead, FsmOk;
            public int FsmHazard, FsmDamage;
            public bool HasNonSlider, NonSliderActive, Slide, NonBouncer, Breakable, Pod;
            public TinkEffect Tink;
        }

        // Solid flags.
        private const int FlagNonSlider = 1, FlagSteepSlope = 2, FlagSlideSurface = 4, FlagNonBouncer = 8, FlagBreakable = 16, FlagSoftTerrain = 32;

        private readonly List<Shape> shapes = new List<Shape>(2048);
        private readonly List<Solid> solids = new List<Solid>(512);
        private readonly List<Hazard> hazards = new List<Hazard>(64);
        private readonly Dictionary<string, List<object>> zones = new Dictionary<string, List<object>>();
        private readonly List<string> scannedScenes = new List<string>();
        private readonly List<Scene> scenesToScan = new List<Scene>();

        // The running dump's slice bookkeeping.
        private readonly Stopwatch slice = new Stopwatch();
        private long budgetTicks, dumpWorkTicks;
        private int dumpSlices;
        private string writeError;

        private bool SliceOver => slice.ElapsedTicks > budgetTicks;

        private void EndSlice()
        {
            dumpWorkTicks += slice.ElapsedTicks;
            NoteWork(slice.ElapsedTicks);
        }

        /// <summary>After a yield: false (and the dump aborted) if the room changed meanwhile.</summary>
        private bool NextSlice(GameManager gm, int transition)
        {
            if (!StillCurrent(gm, transition))
            {
                Abort("room changed");
                return false;
            }
            slice.Restart();
            dumpSlices++;
            return true;
        }

        private IEnumerator Dump()
        {
            var total = Stopwatch.StartNew();
            var startFrame = Time.frameCount;
            var transition = FlowTap.TransitionSeq;
            var gm = GameManager._instance;
            // Nothing runs inside the caller (the game's FinishedEnteringScene, an RPC dispatch, a connect handler).
            yield return null;
            if (!StillCurrent(gm, transition)) { Abort("room changed"); yield break; }

            slice.Restart();
            dumpWorkTicks = 0;
            dumpSlices = 1;
            budgetTicks = SliceBudgetUs * Stopwatch.Frequency / 1_000_000;
            var active = SceneManager.GetActiveScene();

            shapes.Clear();
            solids.Clear();
            hazards.Clear();
            zones.Clear();
            scannedScenes.Clear();
            scenesToScan.Clear();
            rare.Clear();
            GateWatch.Begin();
            var verts = 0;
            var seen = 0;
            var visited = 0;

            // The room is the active scene plus its sub-scenes ("<base>_boss", "_preload", ...: m0 §2.7).
            var baseName = gm.sceneName ?? active.name;
            var loaded = new List<string>();
            for (var i = 0; i < SceneManager.sceneCount; i++)
            {
                var sc = SceneManager.GetSceneAt(i);
                if (!sc.isLoaded) continue;
                loaded.Add(sc.name);
                if (sc == active || IsSubScene(sc.name, baseName))
                {
                    scannedScenes.Add(sc.name);
                    scenesToScan.Add(sc);
                }
            }

            // Depth-first over every GameObject (inactive ones too) with an explicit stack, so the walk itself is
            // sliced: one GetComponents per object, the budget checked between objects.
            for (var si = 0; si < scenesToScan.Count; si++)
            {
                var scene = scenesToScan[si];
                if (!scene.IsValid() || !scene.isLoaded) continue;
                roots.Clear();
                scene.GetRootGameObjects(roots);
                walk.Clear();
                for (var r = roots.Count - 1; r >= 0; r--)
                    if (roots[r] != null) walk.Add(roots[r].transform);
                roots.Clear();
                while (walk.Count > 0)
                {
                    if (SliceOver)
                    {
                        EndSlice();
                        yield return null;
                        if (!NextSlice(gm, transition)) yield break;
                    }
                    var t = walk[walk.Count - 1];
                    walk.RemoveAt(walk.Count - 1);
                    if (t == null) continue; // destroyed since the previous slice
                    for (var ch = t.childCount - 1; ch >= 0; ch--) walk.Add(t.GetChild(ch));
                    visited++;
                    try { verts += Visit(t.gameObject, ref seen); }
                    catch (Exception e) { Core.Plugin.Log.LogWarning($"SceneDumper: object {t.name} skipped: {e.Message}"); }
                }
            }

            // Zone-like components found during the walk: one per budget check.
            for (var i = 0; i < rare.Count; i++)
            {
                if (SliceOver)
                {
                    EndSlice();
                    yield return null;
                    if (!NextSlice(gm, transition)) yield break;
                }
                var c = rare[i];
                if (c == null) continue;
                try { verts += CollectRare(c); }
                catch (Exception e) { Core.Plugin.Log.LogError($"SceneDumper: {c.GetType().Name} {c.name} failed: {e.Message}"); }
            }
            ReleaseObjects();

            // The message, written in slices too (a large room has thousands of outlines).
            var w = writer;
            if (!WriteHead(w, gm, active, loaded, transition, startFrame)) { Abort("serializing TERRAIN failed: " + writeError); yield break; }
            w.Key("solids");
            w.ArrayHeader(solids.Count);
            for (var i = 0; i < solids.Count; i++)
            {
                if (SliceOver)
                {
                    EndSlice();
                    yield return null;
                    if (!NextSlice(gm, transition)) yield break;
                }
                WriteSolid(w, solids[i]);
            }
            w.Key("hazards");
            w.ArrayHeader(hazards.Count);
            for (var i = 0; i < hazards.Count; i++)
            {
                if (SliceOver)
                {
                    EndSlice();
                    yield return null;
                    if (!NextSlice(gm, transition)) yield break;
                }
                WriteHazard(w, hazards[i]);
            }
            foreach (var kv in zones)
            {
                if (SliceOver)
                {
                    EndSlice();
                    yield return null;
                    if (!NextSlice(gm, transition)) yield break;
                }
                if (!WriteZone(w, kv.Key, kv.Value)) { Abort("serializing TERRAIN failed: " + writeError); yield break; }
            }
            WriteTail(w, startFrame, seen, visited, verts, total, dumpWorkTicks + slice.ElapsedTicks, dumpSlices);
            if (Tap.Active) Ipc.FramedServer.Instance.Send(Ipc.Protocol.MsgType.Terrain, w);
            var bytes = w.Length;
            EndSlice();
            slice.Stop();

            running = false;
            routine = null;
            LastSeq = seq;
            LastTransition = transition;
            GateWatch.Commit(transition);
            var workMs = dumpWorkTicks * 1000.0 / Stopwatch.Frequency;
            var result = new Dictionary<string, object>
            {
                ["seq"] = seq, ["scene"] = active.name, ["bytes"] = bytes, ["solids"] = solids.Count, ["hazards"] = hazards.Count,
                ["gates"] = zones.TryGetValue("gates", out var g) ? g.Count : 0, ["verts"] = verts, ["objects"] = visited,
                ["ms"] = total.Elapsed.TotalMilliseconds, ["work_ms"] = workMs, ["slices"] = dumpSlices,
            };
            foreach (var r in waiters) r.Ok(result);
            waiters.Clear();
            Core.Plugin.Log.LogInfo($"TERRAIN #{seq} {active.name} ({reason}): {solids.Count} solids, {hazards.Count} hazards, {verts} verts, " +
                                    $"{visited} objects, {bytes} B, {dumpSlices} slices, work {workMs:F2} ms");
        }

        private static bool StillCurrent(GameManager gm, int transition) =>
            GameManager._instance == gm && gm != null && FlowTap.TransitionSeq == transition;

        private void Abort(string why)
        {
            running = false;
            routine = null;
            ReleaseObjects();
            GateWatch.Discard();
            FailWaiters(why);
        }

        /// <summary>Drop the Unity object references held between slices.</summary>
        private void ReleaseObjects()
        {
            walk.Clear();
            roots.Clear();
            comps.Clear();
            colliders.Clear();
            rare.Clear();
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

        /// <summary>One GameObject: sort its components, then collect its colliders; returns the vertex count added.</summary>
        private int Visit(GameObject go, ref int seen)
        {
            comps.Clear();
            colliders.Clear();
            go.GetComponents(comps);
            var info = default(GoInfo);
            for (var i = 0; i < comps.Count; i++)
            {
                var c = comps[i];
                if (c == null) continue; // missing script
                switch (c)
                {
                    case Transform _: break;
                    case Collider2D col: colliders.Add(col); break;
                    case DamageHero dh: if (info.Dh == null) info.Dh = dh; break;
                    case PlayMakerFSM fsm: if (info.DamagesHeroFsm == null && fsm.FsmName == "damages_hero") info.DamagesHeroFsm = fsm; break;
                    case NonSlider ns:
                        if (!info.HasNonSlider)
                        {
                            info.HasNonSlider = true;
                            info.NonSliderActive = ns.IsActive;
                        }
                        break;
                    case SlideSurface _: info.Slide = true; break;
                    case NonBouncer _: info.NonBouncer = true; break;
                    case Breakable _: info.Breakable = true; break;
                    case TinkEffect tink: if (info.Tink == null) info.Tink = tink; break;
                    case BouncePod _: info.Pod = true; break;
                    case HarpoonHook _: info.Pod = true; break;
                    case TransitionPoint _:
                    case HazardRespawnTrigger _:
                    case ScenePreloader _:
                    case BattleScene _:
                    case FrostRegion _:
                    case NoClamberRegion _:
                    case CameraLockArea _:
                    case CogMultiHitter _:
                    case InGameCutsceneInfo _:
                        rare.Add(c);
                        break;
                }
            }
            comps.Clear();
            var verts = 0;
            for (var i = 0; i < colliders.Count; i++)
            {
                seen++;
                var col = colliders[i];
                try { verts += Collect(col, ref info); }
                catch (Exception e) { Core.Plugin.Log.LogWarning($"SceneDumper: collider {col.name} skipped: {e.Message}"); }
            }
            colliders.Clear();
            return verts;
        }

        /// <summary>
        /// The legacy 'damages_hero' FSM's ints, read the way HeroBox.CheckForDamage reads them (it checks this FSM
        /// before any DamageHero: HeroBox.cs:62-68). TakeDamage gets no DamagePropertyFlags from this path.
        /// </summary>
        private static void ReadDamagesHeroFsm(ref GoInfo info)
        {
            info.FsmRead = true;
            try
            {
                var vars = info.DamagesHeroFsm.FsmVariables;
                var hazard = vars?.FindFsmInt("hazardType");
                var damage = vars?.FindFsmInt("damageDealt");
                if (hazard == null || damage == null) return;
                info.FsmHazard = hazard.Value;
                info.FsmDamage = damage.Value;
                info.FsmOk = true;
            }
            catch (Exception)
            {
                // An FSM whose variables cannot be read is not exported.
            }
        }

        /// <summary>Terrain, static-hazard and Clawline-anchor colliders; returns the vertex count added.</summary>
        private int Collect(Collider2D col, ref GoInfo info)
        {
            var go = col.gameObject;
            var layer = go.layer;
            var anchorVerts = layer == HeroAttackLayer || layer == InteractiveLayer ? CollectAnchor(col, layer, info) : 0;
            var terrain = (layer == TerrainLayer || layer == SoftTerrainLayer) && !col.isTrigger;
            var hazard = false;
            if (info.DamagesHeroFsm != null)
            {
                if (!info.FsmRead) ReadDamagesHeroFsm(ref info);
                hazard = info.FsmOk && info.FsmHazard != (int)HazardType.ENEMY;
            }
            else if (info.Dh != null)
            {
                hazard = info.Dh.hazardType != HazardType.ENEMY;
            }
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
                if (info.HasNonSlider && info.NonSliderActive) flags |= FlagNonSlider;
                if (SteepSlope.IsSteepSlope(go)) flags |= FlagSteepSlope;
                if (info.Slide) flags |= FlagSlideSurface;
                if (info.NonBouncer) flags |= FlagNonBouncer;
                if (info.Breakable) flags |= FlagBreakable;
                if (layer == SoftTerrainLayer) flags |= FlagSoftTerrain;
                var solid = new Solid { Id = col.GetInstanceID(), Go = go.name, Layer = layer, On = on, Body = body, Flags = flags, ShapeFrom = from, ShapeTo = to };
                solids.Add(solid);
                GateWatch.Solid(col, solid.Id, solid.Go, on, ColliderGeometry.Bounds(shapes, from, to));
            }
            if (hazard)
            {
                var h = new Hazard
                {
                    Id = col.GetInstanceID(), Go = go.name, Tink = info.Tink != null, Trigger = col.isTrigger, Body = body, ShapeFrom = from, ShapeTo = to,
                };
                if (info.DamagesHeroFsm != null)
                {
                    // HeroBox does not look at the FSM's enabled state, only at the trigger contact.
                    h.Src = "fsm";
                    h.On = on;
                    h.Type = EnumName<HazardType>.Of((HazardType)info.FsmHazard);
                    h.Damage = info.FsmDamage;
                }
                else
                {
                    // HeroBox treats a disabled DamageHero as 0 damage.
                    h.Src = "dh";
                    h.On = on && info.Dh.enabled;
                    h.Type = EnumName<HazardType>.Of(info.Dh.hazardType);
                    h.Damage = info.Dh.damageDealt;
                    h.DamageFlags = (int)info.Dh.damagePropertyFlags;
                }
                hazards.Add(h);
            }
            return n + anchorVerts;
        }

        /// <summary>
        /// Clawline anchors, classified the way HarpoonDashRayCheck classifies what its non-terrain rays hit
        /// (layers ENEMIES | HERO_ATTACK | INTERACTIVE_OBJECT, triggers included): "pod" (tag "Bounce Pod", a
        /// BouncePod or a HarpoonHook), "ring" (tag "Harpoon Ring"), "tink" (HERO_ATTACK with a TinkEffect that
        /// allows hooking). Hooking an enemy (layer ENEMIES) is the entity export's business.
        /// </summary>
        private int CollectAnchor(Collider2D col, int layer, in GoInfo info)
        {
            var go = col.gameObject;
            string kind = null;
            if (col.CompareTag("Bounce Pod") || info.Pod) kind = "pod";
            else if (col.CompareTag("Harpoon Ring")) kind = "ring";
            else if (layer == HeroAttackLayer && info.Tink != null && !info.Tink.noHarpoonHook) kind = "tink";
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

        private int CollectRare(Component c)
        {
            switch (c)
            {
                case TransitionPoint tp: return CollectGate(tp);
                case HazardRespawnTrigger t: return CollectRespawn(t);
                case ScenePreloader p: return CollectPreloader(p);
                case BattleScene bs: return CollectBattle(bs);
                case FrostRegion f: return CollectFrost(f);
                case NoClamberRegion r: return CollectNoClamber(r);
                case CameraLockArea a: return CollectCamLock(a);
                case CogMultiHitter cog: return CollectZone("cogs", cog);
                case InGameCutsceneInfo ci: return CollectZone("cutscene_info", ci);
                default: return 0;
            }
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
            zoneColliders.Clear();
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

        private int CollectGate(TransitionPoint tp)
        {
            var verts = 0;
            var listed = TransitionPoint.TransitionPoints;
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
            return verts;
        }

        private int CollectRespawn(HazardRespawnTrigger t)
        {
            var verts = 0;
            var d = Base(t, ref verts);
            d["fire_once"] = t.fireOnce;
            if (t.respawnMarker != null) d["marker"] = (Vector2)t.respawnMarker.transform.position;
            Zone("respawns").Add(d);
            return verts;
        }

        /// <summary>
        /// ScenePreloaders grey out Save &amp; Quit from the moment they start loading until the room is left
        /// (m0:C8). One without an activateTrigger starts in Start(); one with a trigger starts when Hornet enters
        /// it ("shapes" are the trigger's). Either way it only starts if its PlayerDataTest passes and the entry
        /// gate passes the white/black lists (ScenePreloader.StartPreload).
        /// </summary>
        private int CollectPreloader(ScenePreloader p)
        {
            var verts = 0;
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

        private int CollectBattle(BattleScene bs)
        {
            var verts = 0;
            var d = Base(bs, ref verts);
            d["no_end_slomo"] = bs.noEndSlomo;
            d["waves"] = bs.waves != null ? bs.waves.Count : 0;
            d["set_pd_bool"] = bs.setPDBoolOnEnd;
            if (bs.gates != null)
            {
                // Arena walls are TERRAIN colliders under "gates" (in "solids", usually inactive until the fight).
                var ids = new List<object>();
                foreach (var c in bs.gates.GetComponentsInChildren<Collider2D>(true))
                {
                    ids.Add(c.GetInstanceID());
                    GateWatch.BattleGate(c.GetInstanceID());
                }
                d["gate_ids"] = ids;
            }
            Zone("battles").Add(d);
            return verts;
        }

        private int CollectFrost(FrostRegion f)
        {
            var verts = 0;
            var d = Base(f, ref verts);
            d["frost_speed"] = f.FrostSpeed;
            d["add_on_enter"] = FrostAddOnEnter(f);
            Zone("frost").Add(d);
            return verts;
        }

        private int CollectNoClamber(NoClamberRegion r)
        {
            var verts = 0;
            var d = Base(r, ref verts);
            d["auto"] = r is AutoNoClamberRegion;
            Zone("no_clamber").Add(d);
            return verts;
        }

        private int CollectCamLock(CameraLockArea a)
        {
            var verts = 0;
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
            return verts;
        }

        private int CollectZone(string key, Component c)
        {
            var verts = 0;
            Zone(key).Add(Base(c, ref verts));
            return verts;
        }

        // ---- message ---------------------------------------------------------------------------------------

        /// <summary>Resets the writer and writes the map header and every key before "solids".</summary>
        private bool WriteHead(Ipc.MsgPackWriter w, GameManager gm, Scene active, List<string> loaded, int transition, int startFrame)
        {
            try
            {
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
                return true;
            }
            catch (Exception e)
            {
                return WriteFailed(e);
            }
        }

        private bool WriteZone(Ipc.MsgPackWriter w, string key, List<object> items)
        {
            try
            {
                w.Key(key);
                Ipc.FramedServer.WriteObject(w, items);
                return true;
            }
            catch (Exception e)
            {
                return WriteFailed(e);
            }
        }

        private bool WriteFailed(Exception e)
        {
            writeError = e.Message;
            Core.Plugin.Log.LogError("SceneDumper: serializing TERRAIN failed: " + e);
            return false;
        }

        private static void WriteTail(Ipc.MsgPackWriter w, int startFrame, int seen, int visited, int verts, Stopwatch total, long workTicks, int slices)
        {
            w.Key("layers");
            w.MapHeader(2);
            w.Key("terrain"); w.Int(TerrainLayer);
            w.Key("soft_terrain"); w.Int(SoftTerrainLayer);
            w.Key("stats");
            w.MapHeader(7);
            w.Key("objects"); w.Int(visited);
            w.Key("colliders_seen"); w.Int(seen);
            w.Key("verts"); w.Int(verts);
            w.Key("slices"); w.Int(slices);
            w.Key("frames"); w.Int(Time.frameCount - startFrame + 1);
            w.Key("work_ms"); w.Double(workTicks * 1000.0 / Stopwatch.Frequency);
            w.Key("ms"); w.Double(total.Elapsed.TotalMilliseconds);
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

        private void WriteSolid(Ipc.MsgPackWriter w, in Solid s)
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

        private void WriteHazard(Ipc.MsgPackWriter w, in Hazard h)
        {
            w.MapHeader(11);
            w.Key("id"); w.Int(h.Id);
            w.Key("go"); w.Str(h.Go);
            w.Key("src"); w.Str(h.Src);
            w.Key("on"); w.Bool(h.On);
            w.Key("hazard"); w.Str(h.Type);
            w.Key("damage"); w.Int(h.Damage);
            w.Key("flags"); w.Int(h.DamageFlags);
            w.Key("tink"); w.Bool(h.Tink);
            w.Key("trigger"); w.Bool(h.Trigger);
            w.Key("body"); w.Int(h.Body);
            w.Key("shapes"); WriteShapes(w, h.ShapeFrom, h.ShapeTo);
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

        /// <summary>
        /// STATE "room": {seq: last TERRAIN sent, transition: the room it was for, current: transition count,
        /// busy: a dump is in progress, work_us: the dump's main-thread work in this frame, gates: the watched
        /// battle/arena gates and other solids whose state differs from the dump, live (GateWatch; nil until the
        /// current room's dump is done, and while a sub-scene that came or went after it is dumped again),
        /// gates_trunc: true once a changed solid could not be listed in this room, so unlisted solids' state is
        /// unknown (nil while gates is nil)}.
        /// </summary>
        private sealed class RoomExporter : Export.IExporter
        {
            public string Key => "room";

            public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
            {
                w.MapHeader(7);
                w.Key("seq"); w.Int(LastSeq);
                w.Key("transition"); w.Int(LastTransition);
                w.Key("current"); w.Int(FlowTap.TransitionSeq);
                w.Key("busy"); w.Bool(Busy);
                w.Key("work_us"); w.Int(WorkUs(ctx.Frame));
                w.Key("gates"); GateWatch.Write(w, FlowTap.TransitionSeq);
                w.Key("gates_trunc"); GateWatch.WriteTruncated(w, FlowTap.TransitionSeq);
            }
        }
    }
}
