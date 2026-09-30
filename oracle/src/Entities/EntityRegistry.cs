using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using GlobalEnums;
using HarmonyLib;
using HutongGames.PlayMaker;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>Bits of Entity.Src: which kinds of threat source make up the entity (DESIGN §3.1.1 EntityRegistry).</summary>
    internal static class Src
    {
        public const int HealthManager = 1;   // root has a HealthManager ("enemy")
        public const int DamageHero = 2;      // some collider's GameObject has a DamageHero
        public const int DamagesHeroFsm = 4;  // some collider's GameObject has a legacy 'damages_hero' FSM (HeroBox.CheckForDamage)
        public const int MultiWounder = 8;    // 'hornet_multi_wounder' FSM template (STEAM DamageHeroes get one in OnAwake)
        public const int Cog = 16;            // CogMultiHitter: hurts through DamageHeroDirectly, no DamageHero (m0:C3)
        public const int Projectile = 32;     // heuristic: no HealthManager, and PROJECTILES layer or a dynamic Rigidbody2D
        public const int Damage = DamageHero | DamagesHeroFsm | MultiWounder | Cog;
    }

    /// <summary>A GameObject that can hurt the hero, and the entity it is exported under.</summary>
    internal sealed class Source
    {
        public UnityEngine.Object Comp;  // DamageHero, PlayMakerFSM or CogMultiHitter
        public GameObject Go;
        public Transform Tr;
        public int Kind;                 // Src bit
        public Entity Owner;             // the HealthManager ancestor's entity, else the source's own; resolved on first activity
        public bool OwnRoot;             // Owner is this source's own GameObject
        public float Extent;             // pivot-to-collider-edge distance, widens the view test for big static hazards
        public bool Dead;
    }

    /// <summary>One collider of an entity and the damage source on the collider's own GameObject (HeroBox reads
    /// DamageHero / 'damages_hero' from the GameObject of the collider it touched).</summary>
    internal sealed class ColliderSlot
    {
        public Collider2D Col;
        public GameObject Go;
        public Transform Tr;
        public bool OnRoot;
        public byte Shape;
        public DamageHero Dh;
        public PlayMakerFSM DmgFsm;
        public FsmInt DmgVar, HazVar;
        public CogMultiHitter Cog;
        public bool MultiWounder;
    }

    /// <summary>Per-root component cache. Rebuilt when first included, when a new source joins it, and every
    /// RefreshFrames while in view; dropped on scene change or when the root is destroyed.</summary>
    internal sealed class Entity
    {
        public int Iid;
        public GameObject Go;
        public Transform Tr;
        public HealthManager Hm;
        public string TypeKey = "";
        public string Category = HitboxCategory.Other;
        public int Src;
        public Rigidbody2D Rb;
        public tk2dSpriteAnimator Anim;
        public tk2dBaseSprite Sprite;
        public Renderer Renderer;
        public PlayMakerFSM[] Fsms = EntityRegistry.NoFsms;
        public ColliderSlot[] Colliders = EntityRegistry.NoColliders;
        public float Extent;
        public int CachedFrame = int.MinValue;
        public bool Dirty = true;
        public int IncludedFrame = int.MinValue;
        public Vector3 Pos;
    }

    internal sealed class RefComparer<T> : IEqualityComparer<T> where T : class
    {
        public static readonly RefComparer<T> Instance = new RefComparer<T>();
        public bool Equals(T a, T b) => ReferenceEquals(a, b);
        public int GetHashCode(T o) => RuntimeHelpers.GetHashCode(o);
    }

    /// <summary>
    /// Finds the threat-relevant objects in view each frame (DESIGN §3.1.1 EntityRegistry, m0 §3 "EntityRegistry
    /// full"). Sources: HealthManager's active list (OnEnable/OnDisable maintained), DamageHero's private static
    /// registry _damageHeroes (every awake DamageHero, active or not), PlayMaker FSMs named 'damages_hero' or
    /// templated 'hornet_multi_wounder', and CogMultiHitters. The game's own collections are read, never scanned
    /// for: the registry is mirrored into a flat list only when a DamageHero wakes or dies, FSM and cog sources
    /// arrive through OnEnable/Awake hooks. Per frame the work is one activeInHierarchy + position per candidate,
    /// and the component caches are rebuilt only for entities that enter the view. Main thread only.
    /// </summary>
    internal static class EntityRegistry
    {
        public static readonly PlayMakerFSM[] NoFsms = new PlayMakerFSM[0];
        public static readonly ColliderSlot[] NoColliders = new ColliderSlot[0];

        /// <summary>View rectangle margin in world units (DESIGN §3.1.2: view frustum + 6 u).</summary>
        public const float Margin = 6f;
        private const int RefreshFrames = 600;        // periodic child-collider rescan while in view
        private const int MaxPeriodicRefreshes = 2;   // per frame; first-sight builds are not limited
        private const int SweepFrames = 300;
        private const int MaxCollidersPerEntity = 64;
        public const int MaxEntities = 128;

        private static List<HealthManager> activeHealthManagers;
        private static Dictionary<GameObject, DamageHero> damageHeroes;
        private static AccessTools.FieldRef<DamageHero, double> damageAllowedTime;
        private static AccessTools.FieldRef<CogMultiHitter, double> cogCanDamageTime;
        private static AccessTools.FieldRef<PlayMakerFSM, Fsm> pmFsm;

        private static readonly Dictionary<int, Entity> EntitiesByRoot = new Dictionary<int, Entity>();
        private static readonly Dictionary<HealthManager, Entity> HmEntities = new Dictionary<HealthManager, Entity>(RefComparer<HealthManager>.Instance);
        private static readonly Dictionary<UnityEngine.Object, Source> SourcesByComp = new Dictionary<UnityEngine.Object, Source>(RefComparer<UnityEngine.Object>.Instance);
        private static readonly HashSet<int> ExtraSourceGos = new HashSet<int>();
        private static List<Source> dhSources = new List<Source>();
        private static List<Source> dhSourcesNext = new List<Source>();
        private static readonly List<Source> ExtraSources = new List<Source>();
        private static readonly List<PlayMakerFSM> PendingFsms = new List<PlayMakerFSM>();
        private static readonly List<CogMultiHitter> PendingCogs = new List<CogMultiHitter>();
        private static readonly List<PlayMakerFSM> PendingTemplates = new List<PlayMakerFSM>();
        private const int MaxPending = 4096;

        private static readonly List<HealthManager> HmScratch = new List<HealthManager>();
        private static readonly List<Collider2D> ColScratch = new List<Collider2D>();
        private static readonly List<ColliderSlot> SlotScratch = new List<ColliderSlot>();
        private static readonly List<UnityEngine.Object> KeyScratch = new List<UnityEngine.Object>();
        private static readonly List<int> IntScratch = new List<int>();
        private static readonly List<HealthManager> HmKeyScratch = new List<HealthManager>();

        /// <summary>Entities selected this frame, in selection order (enemies first).</summary>
        public static readonly List<Entity> Included = new List<Entity>();
        private static readonly HashSet<int> IncludedRoots = new HashSet<int>();

        private static bool dhDirty = true, sceneDirty, seeded;
        private static int lastDhCount = -1;
        private static int nextSweep;
        private static int periodicRefreshes;

        // Counters for ents.stats.
        public static long Rebuilds, Refreshes, Capped;

        public static double Now;  // Time.timeAsDouble of the frame being exported (DamageHero.CanCauseDamage)

        public static void Install(Harmony harmony)
        {
            activeHealthManagers = AccessTools.Field(typeof(HealthManager), "_activeHealthManagers")?.GetValue(null) as List<HealthManager>;
            if (activeHealthManagers == null)
                Core.Plugin.Log.LogError("EntityRegistry: HealthManager._activeHealthManagers not found; no enemies in 'ents'");
            damageHeroes = AccessTools.Field(typeof(DamageHero), "_damageHeroes")?.GetValue(null) as Dictionary<GameObject, DamageHero>;
            if (damageHeroes == null)
                Core.Plugin.Log.LogError("EntityRegistry: DamageHero._damageHeroes not found; no damage sources in 'ents'");
            damageAllowedTime = FieldRef<DamageHero, double>("damageAllowedTime");
            cogCanDamageTime = FieldRef<CogMultiHitter, double>("canDamageTime");
            pmFsm = FieldRef<PlayMakerFSM, Fsm>("fsm");

            Postfix(harmony, AccessTools.Method(typeof(DamageHero), "Awake"), nameof(DamageHeroChanged), "DamageHero.Awake");
            Postfix(harmony, AccessTools.Method(typeof(DamageHero), "OnDestroy"), nameof(DamageHeroChanged), "DamageHero.OnDestroy");
            Postfix(harmony, AccessTools.Method(typeof(PlayMakerFSM), "OnEnable"), nameof(FsmEnabled), "PlayMakerFSM.OnEnable");
            Postfix(harmony, AccessTools.Method(typeof(PlayMakerFSM), "SetFsmTemplate", new[] { typeof(FsmTemplate) }), nameof(FsmTemplateSet), "PlayMakerFSM.SetFsmTemplate");
            Postfix(harmony, AccessTools.Method(typeof(CogMultiHitter), "Awake"), nameof(CogAwake), "CogMultiHitter.Awake");
        }

        private static AccessTools.FieldRef<T, TF> FieldRef<T, TF>(string name) where T : class
        {
            try
            {
                return AccessTools.FieldRefAccess<T, TF>(name);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError($"EntityRegistry: {typeof(T).Name}.{name} not found ({e.Message})");
                return null;
            }
        }

        private static void Postfix(Harmony harmony, System.Reflection.MethodInfo target, string patch, string what)
        {
            if (target == null)
            {
                Core.Plugin.Log.LogError($"EntityRegistry: {what} not found; its sources are missed");
                return;
            }
            harmony.Patch(target, postfix: new HarmonyMethod(typeof(EntityRegistry), patch));
        }

        // ---- hooks (main thread; must never throw into game code) ------------------------------------------

        private static void DamageHeroChanged() => dhDirty = true;

        private static void FsmEnabled(PlayMakerFSM __instance)
        {
            try
            {
                if (DamageKindOf(__instance) == 0) return;
                if (PendingFsms.Count >= MaxPending)
                {
                    // No brain has drained the queue for a long time (pooled damagers re-enable): rescan instead.
                    PendingFsms.Clear();
                    seeded = false;
                }
                PendingFsms.Add(__instance);
            }
            catch (Exception)
            {
                // An FSM without data (added by AddComponent before SetFsmTemplate) is simply not a source yet.
            }
        }

        /// <summary>A new template replaces the FSM's variables, so cached FsmInt references go stale.</summary>
        private static void FsmTemplateSet(PlayMakerFSM __instance)
        {
            if (PendingTemplates.Count < MaxPending) PendingTemplates.Add(__instance);
        }

        private static void CogAwake(CogMultiHitter __instance)
        {
            if (PendingCogs.Count < MaxPending) PendingCogs.Add(__instance);
        }

        /// <summary>SceneManager callback: drop every cached lookup at the next exported frame (cache rule,
        /// m0:N42). The hooks keep queueing while no brain is connected, so prune what died with the scene now.</summary>
        public static void MarkSceneChanged()
        {
            sceneDirty = true;
            PendingFsms.RemoveAll(f => f == null);
            PendingCogs.RemoveAll(c => c == null);
            PendingTemplates.RemoveAll(f => f == null);
            FsmTap.ClearCache();
        }

        public static Fsm FsmOf(PlayMakerFSM f) => pmFsm != null ? pmFsm(f) : f.Fsm;

        /// <summary>Src.DamagesHeroFsm / Src.MultiWounder for FSMs that hurt the hero, else 0.</summary>
        private static int DamageKindOf(PlayMakerFSM f)
        {
            var fsm = FsmOf(f);
            if (fsm == null) return 0;
            if (fsm.Name == "damages_hero") return Src.DamagesHeroFsm;
            if (f.FsmTemplate != null && HitboxCategory.TemplateName(f) == "hornet_multi_wounder") return Src.MultiWounder;
            return 0;
        }

        public static bool CanCauseDamage(DamageHero dh) => damageAllowedTime == null ? dh.CanCauseDamage : Now >= damageAllowedTime(dh);
        public static bool CogCanDamage(CogMultiHitter cog) => cogCanDamageTime == null || Now >= cogCanDamageTime(cog);

        public static bool IsIncludedRoot(int iid) => IncludedRoots.Contains(iid);

        // ---- per frame -----------------------------------------------------------------------------------

        /// <summary>Select the entities in view for this frame into <see cref="Included"/>.</summary>
        public static void Collect(int frame, float minX, float minY, float maxX, float maxY)
        {
            if (sceneDirty) ResetForScene();
            if (!seeded) Seed();
            if (damageHeroes != null && (dhDirty || damageHeroes.Count != lastDhCount)) RebuildDhMirror();
            if (PendingFsms.Count > 0 || PendingCogs.Count > 0 || PendingTemplates.Count > 0) DrainPending();
            if (frame >= nextSweep) Sweep(frame);

            Included.Clear();
            IncludedRoots.Clear();
            periodicRefreshes = 0;
            minX -= Margin; minY -= Margin; maxX += Margin; maxY += Margin;

            if (activeHealthManagers != null)
            {
                // Copy first: nothing here should enable objects, but the list belongs to the game.
                HmScratch.Clear();
                for (var i = 0; i < activeHealthManagers.Count; i++) HmScratch.Add(activeHealthManagers[i]);  // AddRange allocates
                for (var i = 0; i < HmScratch.Count; i++)
                {
                    var hm = HmScratch[i];
                    if (hm == null) continue;
                    var e = HmEntity(hm);
                    if (e.IncludedFrame == frame) continue;
                    var p = e.Tr.position;
                    var pad = e.Extent;
                    if (p.x >= minX - pad && p.x <= maxX + pad && p.y >= minY - pad && p.y <= maxY + pad)
                        Include(e, p, frame);
                }
            }
            Pass(dhSources, frame, minX, minY, maxX, maxY);
            Pass(ExtraSources, frame, minX, minY, maxX, maxY);

            if (Included.Count > MaxEntities)
            {
                // Keep the ones nearest the view centre; a crowd this big is a spawner gone wild or a debug scene.
                Capped++;
                centre = new Vector2((minX + maxX) * 0.5f, (minY + maxY) * 0.5f);
                Included.Sort(ByDistance);
                for (var i = MaxEntities; i < Included.Count; i++) IncludedRoots.Remove(Included[i].Iid);
                Included.RemoveRange(MaxEntities, Included.Count - MaxEntities);
            }
        }

        private static Vector2 centre;
        private static readonly Comparison<Entity> ByDistance = (a, b) =>
            ((Vector2)a.Pos - centre).sqrMagnitude.CompareTo(((Vector2)b.Pos - centre).sqrMagnitude);

        private static void Pass(List<Source> sources, int frame, float minX, float minY, float maxX, float maxY)
        {
            for (var i = 0; i < sources.Count; i++)
            {
                var s = sources[i];
                if (s.Dead) continue;
                var owner = s.Owner;
                if (owner != null && owner.IncludedFrame == frame) continue;  // already exported with its owner
                if (s.Go == null)
                {
                    s.Dead = true;
                    continue;
                }
                if (!s.Go.activeInHierarchy) continue;
                if (owner == null || owner.Go == null) owner = ResolveOwner(s);
                var p = s.Tr.position;
                var pad = s.OwnRoot && owner.Extent > s.Extent ? owner.Extent : s.Extent;
                if (p.x < minX - pad || p.x > maxX + pad || p.y < minY - pad || p.y > maxY + pad) continue;
                Include(owner, s.OwnRoot ? p : owner.Tr.position, frame);
            }
        }

        private static void Include(Entity e, Vector3 pos, int frame)
        {
            e.IncludedFrame = frame;
            e.Pos = pos;
            Included.Add(e);
            IncludedRoots.Add(e.Iid);
            if (e.Dirty || e.CachedFrame == int.MinValue)
                SafeRefresh(e, frame);
            else if (frame - e.CachedFrame > RefreshFrames && periodicRefreshes < MaxPeriodicRefreshes)
            {
                periodicRefreshes++;
                SafeRefresh(e, frame);
            }
        }

        private static int refreshErrors;

        /// <summary>A failed rebuild leaves the entity exported without colliders until the next rebuild.</summary>
        private static void SafeRefresh(Entity e, int frame)
        {
            try
            {
                Refresh(e, frame);
            }
            catch (Exception ex)
            {
                e.Colliders = NoColliders;
                e.Fsms = NoFsms;
                e.CachedFrame = frame;
                e.Dirty = false;
                if (refreshErrors++ < 10)
                    Core.Plugin.Log.LogWarning($"ents: cache rebuild of {e.Iid} failed: {ex.GetType().Name}: {ex.Message}");
            }
        }

        // ---- sources -------------------------------------------------------------------------------------

        private static Entity HmEntity(HealthManager hm)
        {
            if (HmEntities.TryGetValue(hm, out var e) && e.Go != null) return e;
            e = EntityForRoot(hm.gameObject);
            e.Hm = hm;
            e.Dirty = true;
            HmEntities[hm] = e;
            return e;
        }

        private static Entity EntityForRoot(GameObject go)
        {
            var iid = go.GetInstanceID();
            if (EntitiesByRoot.TryGetValue(iid, out var e) && e.Go != null) return e;
            e = new Entity { Iid = iid, Go = go, Tr = go.transform };
            EntitiesByRoot[iid] = e;
            return e;
        }

        /// <summary>Cheap on purpose: a scene wakes hundreds of pooled DamageHeroes that may never activate.</summary>
        private static Source MakeSource(UnityEngine.Object comp, GameObject go, int kind)
        {
            var s = new Source { Comp = comp, Go = go, Tr = go.transform, Kind = kind };
            SourcesByComp[comp] = s;
            return s;
        }

        /// <summary>First time the source is seen active: find its entity (grouping rule, see OwnedBy).</summary>
        private static Entity ResolveOwner(Source s)
        {
            var go = s.Go;
            var hm = go.GetComponentInParent<HealthManager>(true);
            s.OwnRoot = hm == null;
            s.Owner = hm != null ? HmEntity(hm) : EntityForRoot(go);
            s.Owner.Dirty = true;  // its collider list may now include this source's colliders
            if (hm == null)
            {
                var col = go.GetComponent<Collider2D>();
                if (col != null) s.Extent = ExtentAround(col.bounds, s.Tr.position);
            }
            return s.Owner;
        }

        private static float ExtentAround(Bounds b, Vector3 pivot)
        {
            if (b.size.x <= 0f && b.size.y <= 0f) return 0f;
            var dx = Mathf.Max(Mathf.Abs(b.min.x - pivot.x), Mathf.Abs(b.max.x - pivot.x));
            var dy = Mathf.Max(Mathf.Abs(b.min.y - pivot.y), Mathf.Abs(b.max.y - pivot.y));
            return Mathf.Max(dx, dy);
        }

        private static void RebuildDhMirror()
        {
            Rebuilds++;
            dhDirty = false;
            lastDhCount = damageHeroes.Count;
            dhSourcesNext.Clear();
            foreach (var kv in damageHeroes)
            {
                var go = kv.Key;
                var dh = kv.Value;
                if (go == null || dh == null) continue;
                if (!SourcesByComp.TryGetValue(dh, out var s) || s.Dead)
                    s = MakeSource(dh, go, Src.DamageHero);
                dhSourcesNext.Add(s);
            }
            var t = dhSources;
            dhSources = dhSourcesNext;
            dhSourcesNext = t;
        }

        private static void DrainPending()
        {
            for (var i = 0; i < PendingTemplates.Count; i++)
            {
                var f = PendingTemplates[i];
                if (f == null) continue;
                if (SourcesByComp.TryGetValue(f, out var s) && !s.Dead && s.Owner != null) s.Owner.Dirty = true;
                PendingFsms.Add(f);  // it may have just become a damage source
            }
            PendingTemplates.Clear();
            for (var i = 0; i < PendingFsms.Count; i++)
            {
                var f = PendingFsms[i];
                if (f == null) continue;
                int kind;
                try { kind = DamageKindOf(f); }
                catch (Exception) { continue; }
                if (kind == 0) continue;
                if (SourcesByComp.TryGetValue(f, out var s) && !s.Dead)
                {
                    // Re-enabled (pooled) or re-templated: the source is known.
                    if (s.Kind != kind && s.Owner != null) s.Owner.Dirty = true;
                    s.Kind = kind;
                    continue;
                }
                var go = f.gameObject;
                ExtraSources.Add(MakeSource(f, go, kind));
                ExtraSourceGos.Add(go.GetInstanceID());
            }
            PendingFsms.Clear();
            for (var i = 0; i < PendingCogs.Count; i++)
            {
                var c = PendingCogs[i];
                if (c == null || SourcesByComp.ContainsKey(c)) continue;
                var go = c.gameObject;
                ExtraSources.Add(MakeSource(c, go, Src.Cog));
                ExtraSourceGos.Add(go.GetInstanceID());
            }
            PendingCogs.Clear();
        }

        /// <summary>Once: FSM sources enabled before our hooks were installed.</summary>
        private static void Seed()
        {
            seeded = true;
            foreach (var f in PlayMakerFSM.FsmList)
            {
                try
                {
                    if (f != null && DamageKindOf(f) != 0) PendingFsms.Add(f);
                }
                catch (Exception) { }
            }
        }

        /// <summary>Forget destroyed objects (instance ids are never reused, so this only bounds memory).</summary>
        private static void Sweep(int frame)
        {
            nextSweep = frame + SweepFrames;
            ExtraSources.RemoveAll(s => s.Dead || s.Go == null);
            KeyScratch.Clear();
            foreach (var kv in SourcesByComp)
                if (kv.Value.Dead || kv.Key == null) KeyScratch.Add(kv.Key);
            foreach (var k in KeyScratch) SourcesByComp.Remove(k);
            IntScratch.Clear();
            foreach (var kv in EntitiesByRoot)
                if (kv.Value.Go == null) IntScratch.Add(kv.Key);
            foreach (var k in IntScratch) EntitiesByRoot.Remove(k);
            HmKeyScratch.Clear();
            foreach (var kv in HmEntities)
                if (kv.Key == null || kv.Value.Go == null) HmKeyScratch.Add(kv.Key);
            foreach (var k in HmKeyScratch) HmEntities.Remove(k);
        }

        private static void ResetForScene()
        {
            sceneDirty = false;
            // Hook-fed sources that survive the scene change (DontDestroyOnLoad, additive scenes) are re-fed.
            foreach (var s in ExtraSources)
            {
                if (s.Dead || s.Comp == null) continue;
                if (s.Comp is PlayMakerFSM f) PendingFsms.Add(f);
                else if (s.Comp is CogMultiHitter c) PendingCogs.Add(c);
            }
            ExtraSources.Clear();
            ExtraSourceGos.Clear();
            dhSources.Clear();
            SourcesByComp.Clear();
            EntitiesByRoot.Clear();
            HmEntities.Clear();
            Included.Clear();
            IncludedRoots.Clear();
            dhDirty = true;
            FsmTap.ClearCache();
        }

        // ---- component cache -----------------------------------------------------------------------------

        private static void Refresh(Entity e, int frame)
        {
            Refreshes++;
            e.CachedFrame = frame;
            e.Dirty = false;
            var go = e.Go;
            var root = e.Tr;
            e.TypeKey = TypeKey(go.name);
            if (e.Hm == null) e.Hm = go.GetComponent<HealthManager>();
            e.Rb = go.GetComponent<Rigidbody2D>();
            e.Anim = go.GetComponent<tk2dSpriteAnimator>();
            e.Sprite = go.GetComponent<tk2dBaseSprite>();
            e.Renderer = go.GetComponent<Renderer>();
            e.Fsms = go.GetComponents<PlayMakerFSM>();

            var hasHm = e.Hm != null;
            var src = hasHm ? Src.HealthManager : 0;
            Collider2D rootCol = null;
            float extent = 0f;
            var pivot = root.position;
            ColScratch.Clear();
            go.GetComponentsInChildren(true, ColScratch);
            SlotScratch.Clear();
            for (var i = 0; i < ColScratch.Count && SlotScratch.Count < MaxCollidersPerEntity; i++)
            {
                var c = ColScratch[i];
                if (c == null) continue;
                var ct = c.transform;
                if (!OwnedBy(ct, root, hasHm)) continue;
                var cgo = c.gameObject;
                var slot = new ColliderSlot { Col = c, Go = cgo, Tr = ct, OnRoot = ct == root, Shape = ColliderGeometry.ShapeOf(c) };
                var dmg = ResolveDamage(slot, slot.OnRoot ? e.Fsms : null);
                src |= dmg;
                if (slot.OnRoot && rootCol == null) rootCol = c;
                // Extent from bodies and damage colliders only: big alert-range triggers would pull far enemies in.
                if ((dmg != 0 || !c.isTrigger) && c.enabled && cgo.activeInHierarchy)
                    extent = Mathf.Max(extent, ExtentAround(c.bounds, pivot));
                SlotScratch.Add(slot);
            }
            e.Colliders = SlotScratch.Count == 0 ? NoColliders : SlotScratch.ToArray();
            e.Extent = extent;

            // A root source without a collider of its own (the damage lives on children) still names the kind.
            if (DamageHero.TryGet(go, out _)) src |= Src.DamageHero;
            if (HitboxCategory.HasFsm(e.Fsms, "damages_hero")) src |= Src.DamagesHeroFsm;
            if (HitboxCategory.HasTemplate(e.Fsms, "hornet_multi_wounder")) src |= Src.MultiWounder;
            var layer = go.layer;
            if (!hasHm && (layer == (int)PhysLayers.PROJECTILES || (e.Rb != null && e.Rb.bodyType == RigidbodyType2D.Dynamic)))
                src |= Src.Projectile;
            e.Src = src;
            e.Category = HitboxCategory.Categorize(go, rootCol, e.Fsms, hasHm, (src & Src.Damage) != 0);
        }

        /// <summary>
        /// Grouping rule: a collider belongs to the nearest ancestor-or-self that is an entity root. HealthManager
        /// roots absorb their child damage sources; a nested HealthManager (or, under a free damage source, a
        /// nested source) is an entity of its own and keeps its colliders.
        /// </summary>
        private static bool OwnedBy(Transform t, Transform root, bool rootIsHm)
        {
            for (var x = t; x != null; x = x.parent)
            {
                if (x == root) return true;
                var xgo = x.gameObject;
                if (xgo.GetComponent<HealthManager>() != null) return false;
                if (!rootIsHm && IsSourceGo(xgo)) return false;
            }
            return false;
        }

        private static bool IsSourceGo(GameObject go) =>
            DamageHero.TryGet(go, out _) || ExtraSourceGos.Contains(go.GetInstanceID());

        /// <summary>HeroBox order: a 'damages_hero' FSM wins over a DamageHero on the same GameObject.</summary>
        private static int ResolveDamage(ColliderSlot slot, PlayMakerFSM[] rootFsms)
        {
            var go = slot.Go;
            var fsms = rootFsms ?? go.GetComponents<PlayMakerFSM>();
            foreach (var f in fsms)
            {
                if (f == null) continue;
                var fsm = FsmOf(f);
                if (fsm == null || fsm.Name != "damages_hero") continue;
                slot.DmgFsm = f;
                slot.DmgVar = fsm.Variables.FindFsmInt("damageDealt");
                slot.HazVar = fsm.Variables.FindFsmInt("hazardType");
                return Src.DamagesHeroFsm;
            }
            var multi = HitboxCategory.HasTemplate(fsms, "hornet_multi_wounder");
            if (DamageHero.TryGet(go, out var dh) || (dh = go.GetComponent<DamageHero>()) != null)
            {
                slot.Dh = dh;
                slot.MultiWounder = multi || dh.hazardType == HazardType.STEAM;
                return Src.DamageHero | (slot.MultiWounder ? Src.MultiWounder : 0);
            }
            var cog = go.GetComponent<CogMultiHitter>();
            if (cog != null)
            {
                slot.Cog = cog;
                return Src.Cog;
            }
            if (multi)
            {
                slot.MultiWounder = true;
                return Src.MultiWounder;
            }
            return 0;
        }

        /// <summary>
        /// Object name without Unity's instantiation suffixes, so every copy of a prefab shares one key:
        /// "Bone Hunter (3)(Clone)" -> "Bone Hunter".
        /// </summary>
        public static string TypeKey(string name)
        {
            if (string.IsNullOrEmpty(name)) return name ?? "";
            var end = name.Length;
            while (true)
            {
                while (end > 0 && name[end - 1] == ' ') end--;
                if (end >= 7 && string.CompareOrdinal(name, end - 7, "(Clone)", 0, 7) == 0)
                {
                    end -= 7;
                    continue;
                }
                if (end >= 3 && name[end - 1] == ')')
                {
                    var i = end - 2;
                    while (i >= 0 && name[i] >= '0' && name[i] <= '9') i--;
                    if (i >= 0 && i < end - 2 && name[i] == '(')
                    {
                        end = i;
                        continue;
                    }
                }
                break;
            }
            if (end == 0) return name;
            return end == name.Length ? name : name.Substring(0, end);
        }

        // ---- lookups for RPCs ------------------------------------------------------------------------------

        public static GameObject FindGo(int iid)
        {
            if (EntitiesByRoot.TryGetValue(iid, out var e) && e.Go != null) return e.Go;
            foreach (var s in SourcesByComp.Values)
                if (!s.Dead && s.Go != null && s.Go.GetInstanceID() == iid) return s.Go;
            return null;
        }

        public static Dictionary<string, object> Stats() => new Dictionary<string, object>
        {
            ["included"] = Included.Count,
            ["entities_cached"] = EntitiesByRoot.Count,
            ["hm_active"] = activeHealthManagers?.Count ?? -1,
            ["dh_registry"] = damageHeroes?.Count ?? -1,
            ["dh_sources"] = dhSources.Count,
            ["extra_sources"] = ExtraSources.Count,
            ["mirror_rebuilds"] = Rebuilds,
            ["refreshes"] = Refreshes,
            ["capped_frames"] = Capped,
        };
    }
}
