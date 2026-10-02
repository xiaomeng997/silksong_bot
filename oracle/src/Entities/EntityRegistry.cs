using System;
using System.Collections.Generic;
using System.Reflection;
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
        public int Epoch = -1;           // scene epoch Owner was resolved in; a scene change invalidates it
        public bool OwnRoot;             // Owner is this source's own GameObject
        public float Extent;             // pivot-to-collider-edge distance, widens the view test for big static hazards
        public bool Dead;
        public int LiveIdx = -1;         // index in EntityRegistry's live DamageHero list, -1 when not in it
    }

    /// <summary>One collider of an entity and the damage source on the collider's own GameObject (HeroBox reads
    /// DamageHero / 'damages_hero' from the GameObject of the collider it touched).</summary>
    internal sealed class ColliderSlot
    {
        public Collider2D Col;
        public GameObject Go;
        public Transform Tr;
        public string Name;              // the collider's GameObject name (read once per rebuild: .name allocates)
        public bool OnRoot;
        public byte Shape;
        public DamageHero Dh;
        public PlayMakerFSM DmgFsm;
        public FsmInt DmgVar, HazVar;
        public CogMultiHitter Cog;
        public bool MultiWounder;
    }

    /// <summary>Per-root component cache. Rebuilt when first included (or first measured, see Collect), when a new
    /// source joins it, when one of its tk2d sprites adds a collider, after a failed rebuild (RetryFrames later), and
    /// every RefreshFrames while in view; dropped on scene change or when the root is destroyed.</summary>
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
        public int RetryFrame = int.MaxValue;   // a failed rebuild is retried from this frame on
        public bool Seen;                       // exported (not hidden) at least once in this scene epoch
        public bool Hidden;                     // this frame: exported only as a seen, now inactive HealthManager root
        // tk2d sprites owned by the entity and the colliders each had at the last rebuild (see SpritesChanged).
        public tk2dBaseSprite[] Sprites = EntityRegistry.NoSprites;
        public BoxCollider2D[] SpriteBox;
        public int[] SpritePolys, SpriteEdges;
    }

    internal sealed class RefComparer<T> : IEqualityComparer<T> where T : class
    {
        public static readonly RefComparer<T> Instance = new RefComparer<T>();
        public bool Equals(T a, T b) => ReferenceEquals(a, b);
        public int GetHashCode(T o) => RuntimeHelpers.GetHashCode(o);
    }

    /// <summary>
    /// Finds the threat-relevant objects in view each frame (DESIGN §3.1.1 EntityRegistry, m0 §3 "EntityRegistry
    /// full"). Sources: HealthManager's active list (OnEnable/OnDisable maintained), every awake DamageHero (the
    /// game's private registry _damageHeroes, tracked through hooks), PlayMaker FSMs named 'damages_hero' or
    /// templated 'hornet_multi_wounder', and CogMultiHitters. The game's own collections are read, never scanned
    /// for. DamageHero sources are kept by postfixes on Awake / OnEnable / OnDisable / OnDestroy, so only the
    /// ones whose GameObject may be active are looked at per frame (pooled, inactive projectiles cost nothing);
    /// the registry itself is only read once at start and when it holds more than the hooks reported. FSM and
    /// cog sources arrive through Awake hooks. Per frame the work is one activeInHierarchy + position per live
    /// candidate, and the component caches are rebuilt only for entities that enter the view. Main thread only.
    /// </summary>
    internal static class EntityRegistry
    {
        public static readonly PlayMakerFSM[] NoFsms = new PlayMakerFSM[0];
        public static readonly ColliderSlot[] NoColliders = new ColliderSlot[0];
        public static readonly tk2dBaseSprite[] NoSprites = new tk2dBaseSprite[0];

        /// <summary>View rectangle margin in world units (DESIGN §3.1.2: view frustum + 6 u).</summary>
        public const float Margin = 6f;
        private const int RefreshFrames = 600;        // periodic child-collider rescan while in view
        private const int MaxPeriodicRefreshes = 2;   // per frame; first-sight builds are not limited
        private const float PrefetchPad = 14f;        // never-measured enemies within view + Margin + this get measured
        private const int MaxPrefetches = 4;          // per frame
        private const int SweepFrames = 300;
        private const int MaxCollidersPerEntity = 64;
        public const int MaxEntities = 128;
        private const int RetryFrames = 30;           // a failed rebuild is retried this many frames later
        public const int MaxHidden = 16;              // hidden entities per frame

        // Resolved once in Install; a missing symbol stops the plugin (m0 §3 general rule, DESIGN §3.1.1 SymbolCheck).
        private static List<HealthManager> activeHealthManagers;
        private static Dictionary<GameObject, DamageHero> damageHeroes;
        private static AccessTools.FieldRef<DamageHero, double> damageAllowedTime;
        private static AccessTools.FieldRef<CogMultiHitter, double> cogCanDamageTime;
        private static AccessTools.FieldRef<PlayMakerFSM, Fsm> pmFsm;

        private static readonly Dictionary<int, Entity> EntitiesByRoot = new Dictionary<int, Entity>();
        private static readonly Dictionary<HealthManager, Entity> HmEntities = new Dictionary<HealthManager, Entity>(RefComparer<HealthManager>.Instance);

        // DamageHero sources live as long as their component: made in Awake (or by ReconcileDh), dropped in OnDestroy.
        // They survive scene changes; Source.Epoch invalidates their owner instead.
        private static readonly Dictionary<DamageHero, Source> DhSources = new Dictionary<DamageHero, Source>(RefComparer<DamageHero>.Instance);
        // The DamageHero sources whose GameObject may be active (see the hooks); the only ones looked at per frame.
        private static readonly List<Source> LiveDh = new List<Source>();

        // FSM and cog sources: fed by hooks, rebuilt on scene change.
        private static readonly Dictionary<UnityEngine.Object, Source> ExtraByComp = new Dictionary<UnityEngine.Object, Source>(RefComparer<UnityEngine.Object>.Instance);
        private static readonly HashSet<int> ExtraSourceGos = new HashSet<int>();
        private static readonly List<Source> ExtraSources = new List<Source>();
        private static readonly List<PlayMakerFSM> PendingFsms = new List<PlayMakerFSM>();
        private static readonly List<CogMultiHitter> PendingCogs = new List<CogMultiHitter>();
        private static readonly List<PlayMakerFSM> PendingTemplates = new List<PlayMakerFSM>();
        private const int MaxPending = 4096;

        private static readonly List<HealthManager> HmScratch = new List<HealthManager>();
        private static readonly List<Collider2D> ColScratch = new List<Collider2D>();
        private static readonly List<ColliderSlot> SlotScratch = new List<ColliderSlot>();
        private static readonly List<UnityEngine.Object> KeyScratch = new List<UnityEngine.Object>();
        private static readonly List<DamageHero> DhKeyScratch = new List<DamageHero>();
        private static readonly List<int> IntScratch = new List<int>();
        private static readonly List<HealthManager> HmKeyScratch = new List<HealthManager>();
        private static readonly List<tk2dBaseSprite> SpriteScratch = new List<tk2dBaseSprite>();

        /// <summary>HealthManager entities exported at least once in this scene epoch (candidates for "hidden").</summary>
        private static readonly List<Entity> SeenHm = new List<Entity>();

        /// <summary>Entities selected this frame, in selection order (enemies first).</summary>
        public static readonly List<Entity> Included = new List<Entity>();
        private static readonly HashSet<int> IncludedRoots = new HashSet<int>();

        private static bool sceneDirty, seeded, dhSeeded;
        private static int epoch;
        private static int nextSweep;
        private static int periodicRefreshes, prefetches;
        private static float viewMinX, viewMinY, viewMaxX, viewMaxY;  // camera view + Margin, this frame

        // Counters for ents.stats.
        public static long Reconciles, Refreshes, Prefetches, Capped, SpriteRefreshes, RefreshFailures, HiddenExports;

        public static double Now;  // Time.timeAsDouble of the frame being exported (DamageHero.CanCauseDamage)

        public static void Install(Harmony harmony)
        {
            // Resolve every symbol before patching anything, and fail hard with the full list: a renamed field
            // would otherwise leave "ents" silently empty and poison the labels.
            var missing = new List<string>();
            activeHealthManagers = StaticField<List<HealthManager>>(typeof(HealthManager), "_activeHealthManagers", missing);
            damageHeroes = StaticField<Dictionary<GameObject, DamageHero>>(typeof(DamageHero), "_damageHeroes", missing);
            damageAllowedTime = FieldRef<DamageHero, double>("damageAllowedTime", missing);
            cogCanDamageTime = FieldRef<CogMultiHitter, double>("canDamageTime", missing);
            pmFsm = FieldRef<PlayMakerFSM, Fsm>("fsm", missing);
            var patches = new List<KeyValuePair<MethodInfo, string>>
            {
                Target(typeof(DamageHero), "Awake", null, nameof(DamageHeroAwake), missing),
                Target(typeof(DamageHero), "OnEnable", null, nameof(DamageHeroEnabled), missing),
                Target(typeof(DamageHero), "OnDisable", null, nameof(DamageHeroDisabled), missing),
                Target(typeof(DamageHero), "OnDestroy", null, nameof(DamageHeroDestroyed), missing),
                Target(typeof(PlayMakerFSM), "Awake", null, nameof(FsmAwake), missing),
                Target(typeof(PlayMakerFSM), "SetFsmTemplate", new[] { typeof(FsmTemplate) }, nameof(FsmTemplateSet), missing),
                Target(typeof(CogMultiHitter), "Awake", null, nameof(CogAwake), missing),
            };
            if (missing.Count > 0)
                throw new MissingMemberException("EntityRegistry: game symbols not found: " + string.Join(", ", missing.ToArray()));
            foreach (var p in patches)
                harmony.Patch(p.Key, postfix: new HarmonyMethod(typeof(EntityRegistry), p.Value));
        }

        private static T StaticField<T>(Type type, string name, List<string> missing) where T : class
        {
            var v = AccessTools.Field(type, name)?.GetValue(null) as T;
            if (v == null) missing.Add($"{type.Name}.{name}");
            return v;
        }

        private static AccessTools.FieldRef<T, TF> FieldRef<T, TF>(string name, List<string> missing) where T : class
        {
            if (AccessTools.Field(typeof(T), name)?.FieldType == typeof(TF))
                return AccessTools.FieldRefAccess<T, TF>(name);
            missing.Add($"{typeof(T).Name}.{name} ({typeof(TF).Name})");
            return null;
        }

        private static KeyValuePair<MethodInfo, string> Target(Type type, string method, Type[] args, string patch, List<string> missing)
        {
            var m = AccessTools.DeclaredMethod(type, method, args);
            if (m == null) missing.Add($"{type.Name}.{method}");
            return new KeyValuePair<MethodInfo, string>(m, patch);
        }

        // ---- hooks (main thread; must never throw into game code) ------------------------------------------

        /// <summary>Awake runs with the GameObject active, also for a disabled component (which gets no OnEnable).</summary>
        private static void DamageHeroAwake(DamageHero __instance)
        {
            try
            {
                AddLive(DhSource(__instance));
            }
            catch (Exception) { }
        }

        private static void DamageHeroEnabled(DamageHero __instance)
        {
            try
            {
                AddLive(DhSource(__instance));
            }
            catch (Exception) { }
        }

        /// <summary>
        /// Unity calls OnDisable both for a component disable (enabled is already false) and for a GameObject
        /// deactivation or destroy (enabled is still true). Only the latter takes the source off the live list:
        /// HeroBox still touches a disabled DamageHero (as 0 damage, "dealt" 0 here), and a disabled component gets
        /// no OnEnable when its GameObject is reactivated.
        /// </summary>
        private static void DamageHeroDisabled(DamageHero __instance)
        {
            try
            {
                if (__instance.enabled && DhSources.TryGetValue(__instance, out var s)) RemoveLive(s);
            }
            catch (Exception) { }
        }

        private static void DamageHeroDestroyed(DamageHero __instance)
        {
            try
            {
                if (!DhSources.TryGetValue(__instance, out var s)) return;
                DhSources.Remove(__instance);
                s.Dead = true;
                RemoveLive(s);
            }
            catch (Exception) { }
        }

        /// <summary>Awake rather than OnEnable: HeroBox (FSMUtility.ContainsFSM) also takes damage from a disabled
        /// 'damages_hero' FSM, and a pooled FSM that re-enables is already known.</summary>
        private static void FsmAwake(PlayMakerFSM __instance)
        {
            try
            {
                if (DamageKindOf(__instance) == 0) return;
                if (PendingFsms.Count >= MaxPending)
                {
                    // No brain has drained the queue for a long time: forget what died, else rescan instead.
                    PendingFsms.RemoveAll(f => f == null);
                    if (PendingFsms.Count >= MaxPending)
                    {
                        PendingFsms.Clear();
                        seeded = false;
                    }
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

        public static Fsm FsmOf(PlayMakerFSM f) => pmFsm(f);

        /// <summary>Src.DamagesHeroFsm / Src.MultiWounder for FSMs that hurt the hero, else 0.</summary>
        private static int DamageKindOf(PlayMakerFSM f)
        {
            var fsm = FsmOf(f);
            if (fsm == null) return 0;
            if (fsm.Name == "damages_hero") return Src.DamagesHeroFsm;
            if (f.FsmTemplate != null && HitboxCategory.TemplateName(f) == "hornet_multi_wounder") return Src.MultiWounder;
            return 0;
        }

        public static bool CanCauseDamage(DamageHero dh) => Now >= damageAllowedTime(dh);
        public static bool CogCanDamage(CogMultiHitter cog) => Now >= cogCanDamageTime(cog);

        public static bool IsIncludedRoot(int iid) => IncludedRoots.Contains(iid);

        // ---- per frame -----------------------------------------------------------------------------------

        /// <summary>Select the entities in view for this frame into <see cref="Included"/>.</summary>
        public static void Collect(int frame, float minX, float minY, float maxX, float maxY)
        {
            if (sceneDirty) ResetForScene();
            if (!seeded) Seed();
            if (!dhSeeded) ReconcileDh();
            if (PendingFsms.Count > 0 || PendingCogs.Count > 0 || PendingTemplates.Count > 0) DrainPending();
            if (frame >= nextSweep) Sweep(frame);

            Included.Clear();
            IncludedRoots.Clear();
            periodicRefreshes = 0;
            prefetches = 0;
            viewMinX = minX - Margin;
            viewMinY = minY - Margin;
            viewMaxX = maxX + Margin;
            viewMaxY = maxY + Margin;

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
                if (e.CachedFrame == int.MinValue && prefetches < MaxPrefetches && !InView(p, 0f) && InView(p, PrefetchPad))
                {
                    // Never measured, so Extent is still 0: a big enemy's pivot can lie well outside the view while
                    // its body or attack colliders are inside. Measure it now; it is a one-off per enemy and scene.
                    prefetches++;
                    Prefetches++;
                    SafeRefresh(e, frame);
                    pad = e.Extent;
                }
                if (InView(p, pad)) Include(e, p, frame);
            }
            Pass(LiveDh, true, frame);
            Pass(ExtraSources, false, frame);
            HiddenPass(frame);

            if (Included.Count > MaxEntities)
            {
                // Keep the ones nearest the view centre; a crowd this big is a spawner gone wild or a debug scene.
                Capped++;
                centre = new Vector2((viewMinX + viewMaxX) * 0.5f, (viewMinY + viewMaxY) * 0.5f);
                Included.Sort(ByDistance);
                for (var i = MaxEntities; i < Included.Count; i++) IncludedRoots.Remove(Included[i].Iid);
                Included.RemoveRange(MaxEntities, Included.Count - MaxEntities);
            }
        }

        private static bool InView(Vector3 p, float pad) =>
            p.x >= viewMinX - pad && p.x <= viewMaxX + pad && p.y >= viewMinY - pad && p.y <= viewMaxY + pad;

        private static Vector2 centre;
        private static readonly Comparison<Entity> ByDistance = (a, b) =>
            ((Vector2)a.Pos - centre).sqrMagnitude.CompareTo(((Vector2)b.Pos - centre).sqrMagnitude);

        /// <param name="live">sources is LiveDh: dead entries are taken out on the spot.</param>
        private static void Pass(List<Source> sources, bool live, int frame)
        {
            for (var i = 0; i < sources.Count; i++)
            {
                var s = sources[i];
                if (s.Dead || s.Go == null)
                {
                    s.Dead = true;
                    if (live && RemoveLive(s)) i--;  // the last entry moved into i
                    continue;
                }
                var owner = s.Epoch == epoch ? s.Owner : null;
                if (owner != null && owner.IncludedFrame == frame) continue;  // already exported with its owner
                if (!s.Go.activeInHierarchy) continue;
                if (owner == null || owner.Go == null) owner = ResolveOwner(s);
                if (owner.IncludedFrame == frame) continue;  // just resolved to an entity selected earlier this frame
                var p = s.Tr.position;
                if (!InView(p, s.OwnRoot && owner.Extent > s.Extent ? owner.Extent : s.Extent)) continue;
                Include(owner, s.OwnRoot ? p : owner.Tr.position, frame);
            }
        }

        /// <summary>Callers skip entities whose IncludedFrame is this frame; IncludedRoots is the last guard that an
        /// iid appears once per STATE.</summary>
        private static void Include(Entity e, Vector3 pos, int frame)
        {
            e.IncludedFrame = frame;
            if (!IncludedRoots.Add(e.Iid)) return;
            e.Pos = pos;
            e.Hidden = false;
            Included.Add(e);
            if (e.Dirty || e.CachedFrame == int.MinValue || frame >= e.RetryFrame)
                SafeRefresh(e, frame);
            else if (SpritesChanged(e))
            {
                SpriteRefreshes++;
                SafeRefresh(e, frame);
            }
            else if (frame - e.CachedFrame > RefreshFrames && periodicRefreshes < MaxPeriodicRefreshes)
            {
                periodicRefreshes++;
                SafeRefresh(e, frame);
            }
            if (!e.Seen && e.Hm != null)
            {
                e.Seen = true;
                SeenHm.Add(e);
            }
        }

        /// <summary>
        /// "hidden" entities: a HealthManager root exported earlier in this scene whose HealthManager is now inactive
        /// (component disabled or GameObject inactive; not dead), with no active damage source of its own pulling it in
        /// this frame, still within the view (+ its extent). The Bell Beast spends 1.0-2.2 s of every attack like this
        /// (Submerged, Emerge Antic, Burst Antic, Rage Pos/Antic; behaviour build, 99 fights) while its Control FSM
        /// already fixes where it will come up. Exported without colliders (EntityExporter) and never rebuilt here.
        /// </summary>
        private static void HiddenPass(int frame)
        {
            var n = 0;
            for (var i = 0; i < SeenHm.Count && n < MaxHidden; i++)
            {
                var e = SeenHm[i];
                if (e.IncludedFrame == frame) continue;
                var go = e.Go;
                var hm = e.Hm;
                if (go == null || hm == null || hm.isDead) continue;
                if (hm.enabled && go.activeInHierarchy) continue;  // active: in "ents" when in view, never hidden
                var p = e.Tr.position;
                if (!InView(p, e.Extent)) continue;
                e.IncludedFrame = frame;
                if (!IncludedRoots.Add(e.Iid)) continue;
                e.Pos = p;
                e.Hidden = true;
                Included.Add(e);
                HiddenExports++;
                n++;
            }
        }

        /// <summary>
        /// tk2dBaseSprite.UpdateCollider adds its BoxCollider2D / PolygonCollider2D / EdgeCollider2D with AddComponent the
        /// first time the sprite shows a frame whose definition has that collider type, so a rebuild made before that
        /// misses the collider. This is why the Bell Beast had colliders == [] through its whole first Charge Emerge after
        /// every savestate load (trial run f42726-42769: its body box first appears 85 frames later, when an unrelated
        /// rebuild ran; live i0_000: 1209 of 1211 first-charge frames; no rebuild had failed, the BepInEx logs of the
        /// live run have no "cache rebuild" warning). Per frame: three managed field reads per owned sprite.
        /// </summary>
        private static bool SpritesChanged(Entity e)
        {
            var sprites = e.Sprites;
            for (var i = 0; i < sprites.Length; i++)
            {
                var sp = sprites[i];
                if (ReferenceEquals(sp, null)) continue;
                if (!ReferenceEquals(sp.boxCollider2D, e.SpriteBox[i])) return true;
                var polys = sp.polygonCollider2D;
                if ((polys != null ? polys.Count : 0) != e.SpritePolys[i]) return true;
                var edges = sp.edgeCollider2D;
                if ((edges != null ? edges.Count : 0) != e.SpriteEdges[i]) return true;
            }
            return false;
        }

        private static int refreshErrors;

        /// <summary>A failed rebuild leaves the entity exported without colliders until it is retried RetryFrames later.</summary>
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
                e.Sprites = NoSprites;
                e.CachedFrame = frame;
                e.Dirty = false;
                e.RetryFrame = frame + RetryFrames;
                RefreshFailures++;
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
        private static Source DhSource(DamageHero dh)
        {
            if (DhSources.TryGetValue(dh, out var s)) return s;
            var go = dh.gameObject;
            s = new Source { Comp = dh, Go = go, Tr = go.transform, Kind = Src.DamageHero };
            DhSources[dh] = s;
            return s;
        }

        private static Source ExtraSource(UnityEngine.Object comp, GameObject go, int kind)
        {
            var s = new Source { Comp = comp, Go = go, Tr = go.transform, Kind = kind };
            ExtraByComp[comp] = s;
            ExtraSources.Add(s);
            ExtraSourceGos.Add(go.GetInstanceID());
            return s;
        }

        private static void AddLive(Source s)
        {
            if (s.LiveIdx >= 0 || s.Dead) return;
            s.LiveIdx = LiveDh.Count;
            LiveDh.Add(s);
        }

        /// <summary>O(1): the last entry takes the removed one's place.</summary>
        private static bool RemoveLive(Source s)
        {
            var i = s.LiveIdx;
            if (i < 0) return false;
            var last = LiveDh.Count - 1;
            var moved = LiveDh[last];
            LiveDh[i] = moved;
            moved.LiveIdx = i;
            LiveDh.RemoveAt(last);
            s.LiveIdx = -1;
            return true;
        }

        /// <summary>First time the source is seen active in this scene: find its entity (grouping rule, see OwnedBy).</summary>
        private static Entity ResolveOwner(Source s)
        {
            var go = s.Go;
            var hm = go.GetComponentInParent<HealthManager>(true);
            var owner = hm != null ? HmEntity(hm) : EntityForRoot(go);
            s.Owner = owner;
            s.Epoch = epoch;
            s.OwnRoot = hm == null;
            s.Extent = 0f;
            if (hm == null)
            {
                var col = go.GetComponent<Collider2D>();
                if (col != null) s.Extent = ExtentAround(col.bounds, s.Tr.position);
            }
            // A source that woke (or was added) after the owner's last rebuild is not in its collider list yet. One
            // that was there already needs no rebuild: Refresh scans inactive children too.
            if (owner.CachedFrame != int.MinValue && !owner.Dirty && !Knows(owner, s))
                owner.Dirty = true;
            return owner;
        }

        /// <summary>The entity's cached colliders already carry this source's damage.</summary>
        private static bool Knows(Entity e, Source s)
        {
            var anySlot = false;
            foreach (var slot in e.Colliders)
            {
                if (!ReferenceEquals(slot.Go, s.Go)) continue;
                anySlot = true;
                if (ReferenceEquals(slot.Dh, s.Comp) || ReferenceEquals(slot.DmgFsm, s.Comp) || ReferenceEquals(slot.Cog, s.Comp)
                    || slot.DmgFsm != null  // HeroBox order: a 'damages_hero' FSM hides the GameObject's other damage
                    || (s.Kind == Src.MultiWounder && slot.MultiWounder))
                    return true;
            }
            // A root without a collider of its own adds nothing to the list (Refresh read the root's components).
            return !anySlot && ReferenceEquals(s.Go, e.Go);
        }

        private static float ExtentAround(Bounds b, Vector3 pivot)
        {
            if (b.size.x <= 0f && b.size.y <= 0f) return 0f;
            var dx = Mathf.Max(Mathf.Abs(b.min.x - pivot.x), Mathf.Abs(b.max.x - pivot.x));
            var dy = Mathf.Max(Mathf.Abs(b.min.y - pivot.y), Mathf.Abs(b.max.y - pivot.y));
            return Mathf.Max(dx, dy);
        }

        /// <summary>
        /// DamageHeroes the hooks did not report (awake before Install, or a hook that did not run): read the game's
        /// registry. Once at the first exported frame, then only when the registry holds more than we know
        /// (two DamageHeroes on one GameObject make the registry smaller, never larger).
        /// </summary>
        private static void ReconcileDh()
        {
            dhSeeded = true;
            Reconciles++;
            foreach (var kv in damageHeroes)
            {
                var dh = kv.Value;
                if (dh == null || DhSources.ContainsKey(dh)) continue;
                var s = DhSource(dh);
                if (s.Go.activeInHierarchy) AddLive(s);
            }
        }

        private static void DrainPending()
        {
            for (var i = 0; i < PendingTemplates.Count; i++)
            {
                var f = PendingTemplates[i];
                if (f == null) continue;
                if (ExtraByComp.TryGetValue(f, out var s) && !s.Dead && s.Epoch == epoch && s.Owner != null) s.Owner.Dirty = true;
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
                if (ExtraByComp.TryGetValue(f, out var s) && !s.Dead)
                {
                    // Re-templated, or queued twice: the source is known.
                    if (s.Kind != kind && s.Epoch == epoch && s.Owner != null) s.Owner.Dirty = true;
                    s.Kind = kind;
                    continue;
                }
                ExtraSource(f, f.gameObject, kind);
            }
            PendingFsms.Clear();
            for (var i = 0; i < PendingCogs.Count; i++)
            {
                var c = PendingCogs[i];
                if (c == null || ExtraByComp.ContainsKey(c)) continue;
                ExtraSource(c, c.gameObject, Src.Cog);
            }
            PendingCogs.Clear();
        }

        /// <summary>Once: FSM sources awake before our hooks were installed (enabled ones; FsmList has no others).</summary>
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

        /// <summary>Forget destroyed objects (instance ids are never reused, so this only bounds memory), and catch
        /// DamageHeroes whose hooks were missed.</summary>
        private static void Sweep(int frame)
        {
            nextSweep = frame + SweepFrames;

            ExtraSources.RemoveAll(s => s.Dead || s.Go == null);
            KeyScratch.Clear();
            foreach (var kv in ExtraByComp)
                if (kv.Value.Dead || kv.Key == null) KeyScratch.Add(kv.Key);
            foreach (var k in KeyScratch) ExtraByComp.Remove(k);
            ExtraSourceGos.Clear();
            foreach (var s in ExtraSources) ExtraSourceGos.Add(s.Go.GetInstanceID());

            DhKeyScratch.Clear();
            foreach (var kv in DhSources)
                if (kv.Key == null) DhKeyScratch.Add(kv.Key);
            foreach (var k in DhKeyScratch)
            {
                var s = DhSources[k];
                s.Dead = true;
                RemoveLive(s);
                DhSources.Remove(k);
            }
            if (damageHeroes.Count > DhSources.Count) ReconcileDh();

            SeenHm.RemoveAll(e => e.Go == null);
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
            epoch++;  // every Source.Owner from before is stale
            // Hook-fed sources that survive the scene change (DontDestroyOnLoad, additive scenes) are re-fed.
            foreach (var s in ExtraSources)
            {
                if (s.Dead || s.Comp == null) continue;
                if (s.Comp is PlayMakerFSM f) PendingFsms.Add(f);
                else if (s.Comp is CogMultiHitter c) PendingCogs.Add(c);
            }
            ExtraSources.Clear();
            ExtraSourceGos.Clear();
            ExtraByComp.Clear();
            EntitiesByRoot.Clear();
            HmEntities.Clear();
            SeenHm.Clear();
            Included.Clear();
            IncludedRoots.Clear();
            FsmTap.ClearCache();
        }

        // ---- component cache -----------------------------------------------------------------------------

        private static void Refresh(Entity e, int frame)
        {
            Refreshes++;
            e.CachedFrame = frame;
            e.Dirty = false;
            e.RetryFrame = int.MaxValue;
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
                var slot = new ColliderSlot { Col = c, Go = cgo, Tr = ct, Name = cgo.name, OnRoot = ct == root, Shape = ColliderGeometry.ShapeOf(c) };
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
            SnapshotSprites(e, go, root, hasHm);

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

        /// <summary>The entity's tk2d sprites and the colliders they had at this rebuild (SpritesChanged compares).</summary>
        private static void SnapshotSprites(Entity e, GameObject go, Transform root, bool hasHm)
        {
            SpriteScratch.Clear();
            go.GetComponentsInChildren(true, SpriteScratch);
            var n = 0;
            for (var i = 0; i < SpriteScratch.Count; i++)
                if (SpriteScratch[i] != null && OwnedBy(SpriteScratch[i].transform, root, hasHm)) SpriteScratch[n++] = SpriteScratch[i];
            if (n == 0)
            {
                e.Sprites = NoSprites;
                SpriteScratch.Clear();
                return;
            }
            var sprites = new tk2dBaseSprite[n];
            var box = new BoxCollider2D[n];
            var polys = new int[n];
            var edges = new int[n];
            for (var i = 0; i < n; i++)
            {
                var sp = SpriteScratch[i];
                sprites[i] = sp;
                box[i] = sp.boxCollider2D;
                polys[i] = sp.polygonCollider2D != null ? sp.polygonCollider2D.Count : 0;
                edges[i] = sp.edgeCollider2D != null ? sp.edgeCollider2D.Count : 0;
            }
            SpriteScratch.Clear();
            e.SpriteBox = box;
            e.SpritePolys = polys;
            e.SpriteEdges = edges;
            e.Sprites = sprites;
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
            foreach (var s in DhSources.Values)
                if (!s.Dead && s.Go != null && s.Go.GetInstanceID() == iid) return s.Go;
            foreach (var s in ExtraSources)
                if (!s.Dead && s.Go != null && s.Go.GetInstanceID() == iid) return s.Go;
            return null;
        }

        public static Dictionary<string, object> Stats() => new Dictionary<string, object>
        {
            ["included"] = Included.Count,
            ["entities_cached"] = EntitiesByRoot.Count,
            ["hm_active"] = activeHealthManagers.Count,
            ["dh_registry"] = damageHeroes.Count,
            ["dh_known"] = DhSources.Count,
            ["dh_live"] = LiveDh.Count,
            ["extra_sources"] = ExtraSources.Count,
            ["reconciles"] = Reconciles,
            ["refreshes"] = Refreshes,
            ["sprite_refreshes"] = SpriteRefreshes,
            ["refresh_failures"] = RefreshFailures,
            ["prefetches"] = Prefetches,
            ["capped_frames"] = Capped,
            ["seen_hm"] = SeenHm.Count,
            ["hidden_exports"] = HiddenExports,
        };
    }
}
