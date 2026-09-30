using GlobalEnums;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// Port of DebugMod HitboxRender.CategorizeHitbox (REF\Silksong.DebugMod\Hitbox\HitboxRender.cs, MIT), the
    /// community's reference answer to "what is this collider". DebugMod's "Enemy" type means "damages the hero";
    /// we split it into "enemy" (the entity owns a HealthManager) and "hazard" (it does not). DebugMod's
    /// "Knight" is "player", "Attack" is "player_attack", "Trigger" is "interactable"; its debug-only types
    /// (NonMantleRegion, AlertRegion, and colliders it hides) fold into "other". Runs only when an entity's
    /// component cache is (re)built, never per frame: every check is a GetComponent call.
    /// </summary>
    internal static class HitboxCategory
    {
        public const string Enemy = "enemy";
        public const string Hazard = "hazard";
        public const string Terrain = "terrain";
        public const string Player = "player";
        public const string PlayerAttack = "player_attack";
        public const string HazardRespawn = "hazard_respawn";
        public const string Gate = "gate";
        public const string Breakable = "breakable";
        public const string Interactable = "interactable";
        public const string Other = "other";

        private const int InteractiveObjectLayer = (int)PhysLayers.INTERACTIVE_OBJECT;

        /// <summary>
        /// Category of an entity root. <paramref name="col"/> is the root's own collider (may be null: DebugMod
        /// categorizes colliders, and a root without one can only match the component tests). The entity-level
        /// facts decide the enemy/hazard split and rescue HealthManager roots that the collider rules would call
        /// "other" or "player_attack" (enemies that hurt other enemies carry DamageEnemies).
        /// </summary>
        public static string Categorize(GameObject go, Collider2D col, PlayMakerFSM[] rootFsms, bool hasHealthManager, bool groupDealsDamage)
        {
            var raw = CategorizeCollider(go, col, rootFsms);
            if (raw == Enemy)
                return hasHealthManager ? Enemy : Hazard;
            if (hasHealthManager && (raw == Other || raw == PlayerAttack || raw == Terrain))
                return Enemy;
            if (!hasHealthManager && groupDealsDamage && raw == Other)
                return Hazard;
            return raw;
        }

        /// <summary>DebugMod's rule order, verbatim where the components exist in 1.0.30000.</summary>
        private static string CategorizeCollider(GameObject go, Collider2D col, PlayMakerFSM[] fsms)
        {
            if (go.GetComponent<DamageHero>() != null || HasFsm(fsms, "damages_hero") || HasTemplate(fsms, "hornet_multi_wounder")
                || go.GetComponent<CogMultiHitter>() != null
                || (go.GetComponent<TriggerEnterEvent>() != null && go.transform.parent != null
                    && go.transform.parent.GetComponent<RangeAttackGroup>() != null))
                return Enemy;

            if (go.layer == (int)PhysLayers.TERRAIN)
                return Terrain;  // DebugMod's NonSliderTerrain distinction is a render detail

            var hero = HeroController.UnsafeInstance;
            var isTrigger = col != null && col.isTrigger;
            if (hero != null && go == hero.gameObject && col != null && !isTrigger)
                return Player;

            if (go.GetComponent<DamageEnemies>() != null || HasFsm(fsms, "damages_enemy")
                || (go.name == "Damager" && HasFsm(fsms, "Damage")))
                return PlayerAttack;

            if (isTrigger && go.GetComponent<HazardRespawnTrigger>() != null)
                return HazardRespawn;

            if (isTrigger && go.GetComponent<TransitionPoint>() != null)
                return Gate;

            if (go.GetComponent<Breakable>() != null || go.layer == InteractiveObjectLayer)
            {
                if (go.GetComponent<Lever_tk2d>() != null || go.GetComponent<Lever>() != null)
                    return Interactable;
                // DebugMod hides NonBouncer breakables unless in its verbose mode; they are still breakables.
                return Breakable;
            }

            // tag == rather than CompareTag: CompareTag logs an error for tags the project does not define.
            if (go.GetComponent<HarpoonHook>() != null || go.GetComponent<Lever_tk2d>() != null || go.GetComponent<Lever>() != null
                || go.tag == "Geo")
                return Interactable;

            return Other;
        }

        public static bool HasFsm(PlayMakerFSM[] fsms, string name)
        {
            if (fsms == null) return false;
            foreach (var f in fsms)
                if (f != null && FsmName(f) == name) return true;
            return false;
        }

        public static bool HasTemplate(PlayMakerFSM[] fsms, string name)
        {
            if (fsms == null) return false;
            foreach (var f in fsms)
                if (f != null && TemplateName(f) == name) return true;
            return false;
        }

        /// <summary>FsmName without the NullReferenceException PlayMakerFSM throws before its Fsm exists.</summary>
        public static string FsmName(PlayMakerFSM f)
        {
            var fsm = EntityRegistry.FsmOf(f);
            return fsm != null ? fsm.Name : null;
        }

        /// <summary>FsmTemplate.name allocates a string on every call (native Object.name), so resolve each
        /// template once. Templates are assets and live for the whole session.</summary>
        public static string TemplateName(PlayMakerFSM f)
        {
            var t = f.FsmTemplate;
            if (t == null) return null;
            var id = t.GetInstanceID();
            if (!TemplateNames.TryGetValue(id, out var name))
                TemplateNames[id] = name = t.name;
            return name;
        }

        private static readonly System.Collections.Generic.Dictionary<int, string> TemplateNames =
            new System.Collections.Generic.Dictionary<int, string>();
    }
}
