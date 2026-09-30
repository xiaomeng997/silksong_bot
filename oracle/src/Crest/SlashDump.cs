using System;
using System.Collections.Generic;
using GlobalSettings;
using HarmonyLib;
using SsOracle.SceneDump;
using UnityEngine;

namespace SsOracle.Crest
{
    /// <summary>
    /// RPC "slash.dump" {all_groups=false} (read-only; crests.md §5 b). Every attack object the hero can use with the
    /// equipped crest, found the way the game finds them in 1.0.30000:
    /// <list type="bullet">
    /// <item>Nail swings: HeroController.Attack/DownAttack use the private normalSlash, alternateSlash, upSlash,
    /// altUpSlash, downSlash/downSpike, altDownSlash/altDownSpike and wallSlash (+ their *Damager), which SetConfigGroup
    /// copies from the current group, or from the override group where that has the object (:1863-1878). "alt" is used
    /// on every second swing in the same direction within AttackRecoveryTime + ALT_ATTACK_RESET; "wall" while wall
    /// sliding (unless Toolmaster). The down slot follows Config.DownSlashType: DownSpike -> the Downspike component,
    /// Slash -> a NailSlash, Custom -> none (crestAttacksFSM runs Config.DownSlashEvent). source "hero".</item>
    /// <item>Custom down slash: down/alt_down still get the group's DownSlashObject/AltDownSlashObject, paired with the
    /// hero's downSlashDamager/altDownSlashDamager (ConfigGroup.Setup binds those for every type), with
    /// down_slash_event. source "group" (an FSM swings them; which objects the FSM itself spawns is not visible here).</item>
    /// <item>dash_stab, dash_stab_alt, charge, taunt: FSMs fetch them with GetHeroAttackObject, which reads
    /// CurrentConfigGroup (never the override group). source "group".</item>
    /// </list>
    /// Reply:
    /// <code>
    /// {frame, crest, config, group, down_slash_type, down_slash_event (Custom only), nail_damage, nail_upgrades,
    ///  long_needle: {equipped, multiplier}, hero: {pos, facing, scale, box},
    ///  attacks: [attack], groups: [{index, kind, config, attacks: [attack]}]   (groups only with all_groups)}
    /// attack   = {slot, source, go, path, active, component, damager, nail: [nail], damagers: [damager], down_attacks: [path],
    ///             down_slash_event (Custom down/alt_down only)}
    /// nail     = {path, type, can_hit_spikes, scale, scale_now, anim, clip: {name, fps, frames, wrap, events: [[i, info]]},
    ///             extra_damager, clash_tink: [collider], fields}
    /// damager  = {path, tag, nail_tag, enabled, active, attack_type, use_nail_damage, nail_damage_mult, damage_dealt,
    ///             damage_mult, damage_mult_per_hit, multi_hitter, steps_per_hit, hits_until_death, magnitude_mult,
    ///             silk_generation, does_not_parry, does_not_critical_hit, does_not_tink, direction, colliders: [collider],
    ///             fields}
    /// collider = {type, enabled, trigger, layer, shapes: [{k, v: [x0, y0, ...], r}], shapes_swing?}
    /// </code>
    /// Paths are relative to the hero. Collider outlines are world space from the transforms as they are now, disabled or
    /// not (a slash's collider is only on between its first two animation events). NailAttackBase.OnSlashStarting sets the
    /// attack's localScale to its "scale" (Long Needle: times Gameplay.LongNeedleMultiplier) when a swing starts; when that
    /// differs from the current localScale, shapes_swing holds the outline with the swing's scale (no Long Needle).
    /// Facing: hero.facing +1 = right (the hero's localScale.x is negative then), so hero-relative forward is
    /// (x - hero.x) * facing.
    /// </summary>
    internal static class SlashDump
    {
        private struct HeroSlot
        {
            public string Slot;
            public AccessTools.FieldRef<HeroController, NailSlash> Slash;
            public AccessTools.FieldRef<HeroController, Downspike> Spike;
            public AccessTools.FieldRef<HeroController, DamageEnemies> Damager;
        }

        private static HeroSlot S(string slot, string slash, string damager) => new HeroSlot
        {
            Slot = slot,
            Slash = Hero.Refs.Field<HeroController, NailSlash>(slash),
            Damager = Hero.Refs.Field<HeroController, DamageEnemies>(damager),
        };

        private static HeroSlot D(string slot, string spike, string damager) => new HeroSlot
        {
            Slot = slot,
            Spike = Hero.Refs.Field<HeroController, Downspike>(spike),
            Damager = Hero.Refs.Field<HeroController, DamageEnemies>(damager),
        };

        private static readonly HeroSlot[] Swings =
        {
            S("normal", "normalSlash", "normalSlashDamager"),
            S("alt", "alternateSlash", "alternateSlashDamager"),
            S("up", "upSlash", "upSlashDamager"),
            S("alt_up", "altUpSlash", "altUpSlashDamager"),
            S("wall", "wallSlash", "wallSlashDamager"),
        };

        private static readonly HeroSlot[] DownSlashes = { S("down", "downSlash", "downSlashDamager"), S("alt_down", "altDownSlash", "altDownSlashDamager") };
        private static readonly HeroSlot[] DownSpikes = { D("down", "downSpike", "downSlashDamager"), D("alt_down", "altDownSpike", "altDownSlashDamager") };

        private static readonly AccessTools.FieldRef<NailAttackBase, Vector3> SwingScale = Hero.Refs.Field<NailAttackBase, Vector3>("scale");
        private static readonly AccessTools.FieldRef<Downspike, DamageEnemies> KnockbackH = Hero.Refs.Field<Downspike, DamageEnemies>("horizontalKnockbackDamager");
        private static readonly AccessTools.FieldRef<Downspike, DamageEnemies> KnockbackV = Hero.Refs.Field<Downspike, DamageEnemies>("verticalKnockbackDamager");

        public static object Dump(Dictionary<string, object> args)
        {
            var pd = CrestModule.RequirePd();
            var hero = CrestModule.RequireHero();
            var cfg = hero.Config;
            var root = hero.transform;
            var attacks = new List<object>();
            foreach (var s in Swings) AddHeroSlot(attacks, s, hero);
            if (cfg != null && cfg.DownSlashType == HeroControllerConfig.DownSlashTypes.DownSpike)
                foreach (var s in DownSpikes) AddHeroSlot(attacks, s, hero);
            else if (cfg != null && cfg.DownSlashType == HeroControllerConfig.DownSlashTypes.Slash)
                foreach (var s in DownSlashes) AddHeroSlot(attacks, s, hero);
            else if (cfg != null && cfg.DownSlashType == HeroControllerConfig.DownSlashTypes.Custom)
                AddCustomDown(attacks, hero, cfg.DownSlashEvent);
            var group = hero.CurrentConfigGroup;
            if (group != null) AddFsmObjects(attacks, group, root);

            var pos = root.position;
            var d = new Dictionary<string, object>
            {
                ["frame"] = Time.frameCount,
                ["crest"] = pd.CurrentCrestID,
                ["config"] = CrestModule.Name(cfg),
                ["group"] = CrestDump.CurrentGroupIndex(hero),
                ["down_slash_type"] = cfg != null ? cfg.DownSlashType.ToString() : null,
                ["down_slash_event"] = cfg != null && cfg.DownSlashType == HeroControllerConfig.DownSlashTypes.Custom ? cfg.DownSlashEvent : null,
                ["nail_damage"] = pd.nailDamage,
                ["nail_upgrades"] = pd.nailUpgrades,
                ["long_needle"] = LongNeedle(hero),
                ["hero"] = new Dictionary<string, object>
                {
                    ["pos"] = CrestModule.Floats(pos),
                    ["facing"] = hero.cState.facingRight ? 1 : -1,
                    ["scale"] = CrestModule.Floats(root.localScale),
                    ["box"] = CrestModule.Try(() =>
                    {
                        var b = hero.Bounds;
                        return new[] { b.min.x, b.min.y, b.max.x, b.max.y };
                    }),
                },
                ["attacks"] = attacks,
            };
            if (Ipc.Rpc.Bool(args, "all_groups")) d["groups"] = AllGroups(hero);
            return d;
        }

        private static object LongNeedle(HeroController hero)
        {
            var tool = Gameplay.LongNeedleTool;
            return new Dictionary<string, object>
            {
                ["equipped"] = tool != null && Hero.SafeReads.ToolsReadable(hero) ? (object)tool.IsEquipped : null,
                ["multiplier"] = Gameplay.LongNeedleMultiplier,
            };
        }

        private static void AddHeroSlot(List<object> into, HeroSlot s, HeroController hero)
        {
            NailAttackBase attack = null;
            if (s.Slash != null) attack = s.Slash(hero);
            else if (s.Spike != null) attack = s.Spike(hero);
            if (attack == null) return;
            var damager = s.Damager != null ? s.Damager(hero) : null;
            into.Add(Attack(s.Slot, "hero", attack.gameObject, hero.transform, attack, damager));
        }

        /// <summary>
        /// Custom down slash: no NailSlash/Downspike slot, but ConfigGroup.Setup still takes DownSlashDamager and
        /// AltDownSlashDamager from DownSlashObject/AltDownSlashObject for every type and SetConfigGroup copies them into
        /// the hero (:1873). Listed as source "group" (swung by crestAttacksFSM's DownSlashEvent, not by
        /// HeroController.DownAttack) with that event, from the object carrying the paired damager (the current group's
        /// object unless an override group supplied it).
        /// </summary>
        private static void AddCustomDown(List<object> into, HeroController hero, string downSlashEvent)
        {
            var g = hero.CurrentConfigGroup;
            for (var i = 0; i < DownSlashes.Length; i++)
            {
                var s = DownSlashes[i];
                var damager = s.Damager != null ? s.Damager(hero) : null;
                var go = damager != null ? damager.gameObject : g == null ? null : i == 0 ? g.DownSlashObject : g.AltDownSlashObject;
                if (go == null) continue;
                var a = Attack(s.Slot, "group", go, hero.transform, go.GetComponent<NailAttackBase>(), damager);
                a["down_slash_event"] = downSlashEvent;
                into.Add(a);
            }
        }

        private static void AddFsmObjects(List<object> into, HeroController.ConfigGroup g, Transform root)
        {
            AddObject(into, "dash_stab", g.DashStab, root);
            AddObject(into, "dash_stab_alt", g.DashStabAlt, root);
            AddObject(into, "charge", g.ChargeSlash, root);
            AddObject(into, "taunt", g.TauntSlash, root);
        }

        private static void AddObject(List<object> into, string slot, GameObject go, Transform root)
        {
            if (go == null) return;
            into.Add(Attack(slot, "group", go, root, go.GetComponent<NailAttackBase>(), null));
        }

        /// <summary>Every config group's objects, current or not (inactive roots keep their transforms).</summary>
        private static List<object> AllGroups(HeroController hero)
        {
            var list = new List<object>();
            AddGroups(list, CrestDump.GroupsOf(hero), "configs", hero.transform);
            AddGroups(list, CrestDump.SpecialGroupsOf(hero), "special", hero.transform);
            return list;
        }

        private static void AddGroups(List<object> into, HeroController.ConfigGroup[] groups, string kind, Transform root)
        {
            if (groups == null) return;
            for (var i = 0; i < groups.Length; i++)
            {
                var g = groups[i];
                if (g == null) continue;
                var attacks = new List<object>();
                AddObject(attacks, "normal", g.NormalSlashObject, root);
                AddObject(attacks, "alt", g.AlternateSlashObject, root);
                AddObject(attacks, "up", g.UpSlashObject, root);
                AddObject(attacks, "alt_up", g.AltUpSlashObject, root);
                AddObject(attacks, "down", g.DownSlashObject, root);
                AddObject(attacks, "alt_down", g.AltDownSlashObject, root);
                AddObject(attacks, "wall", g.WallSlashObject, root);
                AddFsmObjects(attacks, g, root);
                into.Add(new Dictionary<string, object>
                {
                    ["index"] = i,
                    ["kind"] = kind,
                    ["config"] = CrestModule.Name(g.Config),
                    ["attacks"] = attacks,
                });
            }
        }

        private static Dictionary<string, object> Attack(string slot, string source, GameObject go, Transform root, NailAttackBase main, DamageEnemies damager)
        {
            var nails = new List<object>();
            foreach (var nb in go.GetComponentsInChildren<NailAttackBase>(true)) nails.Add(Nail(nb, root));

            var seen = new HashSet<DamageEnemies>();
            var damagers = new List<object>();
            foreach (var de in go.GetComponentsInChildren<DamageEnemies>(true))
                if (seen.Add(de)) damagers.Add(Damager(de, root, go.transform));
            // A Downspike's knockback damagers and the damager SetConfigGroup paired with the slot need not be children.
            foreach (var spike in go.GetComponentsInChildren<Downspike>(true))
            {
                foreach (var extra in new[] { KnockbackH != null ? KnockbackH(spike) : null, KnockbackV != null ? KnockbackV(spike) : null })
                    if (extra != null && seen.Add(extra)) damagers.Add(Damager(extra, root, go.transform));
            }
            if (damager != null && seen.Add(damager)) damagers.Add(Damager(damager, root, go.transform));

            var down = new List<object>();
            foreach (var hda in go.GetComponentsInChildren<HeroDownAttack>(true)) down.Add(CrestModule.PathFrom(root, hda.transform));

            return new Dictionary<string, object>
            {
                ["slot"] = slot,
                ["source"] = source,
                ["go"] = go.name,
                ["path"] = CrestModule.PathFrom(root, go.transform),
                ["active"] = go.activeInHierarchy,
                ["component"] = main != null ? main.GetType().Name : null,
                ["damager"] = damager != null ? CrestModule.PathFrom(root, damager.transform) : null,
                ["nail"] = nails,
                ["damagers"] = damagers,
                ["down_attacks"] = down,
            };
        }

        private static Dictionary<string, object> Nail(NailAttackBase nb, Transform root)
        {
            var fields = PlainValues.Fields(nb);
            var anim = nb is NailSlash ns ? ns.animName : fields.TryGetValue("animName", out var a) ? a as string : null;
            List<object> clash = null;
            var clashT = nb.transform.Find("Clash Tink");
            if (clashT != null)
            {
                clash = new List<object>();
                foreach (var c in clashT.GetComponents<Collider2D>()) clash.Add(Collider(c, root, nb.transform));
            }
            return new Dictionary<string, object>
            {
                ["path"] = CrestModule.PathFrom(root, nb.transform),
                ["type"] = nb.GetType().Name,
                ["can_hit_spikes"] = nb.CanHitSpikes,
                ["scale"] = SwingScale != null ? CrestModule.Floats(SwingScale(nb)) : null,
                ["scale_now"] = CrestModule.Floats(nb.transform.localScale),
                ["anim"] = anim,
                ["clip"] = Clip(nb.GetComponent<tk2dSpriteAnimator>(), anim),
                ["extra_damager"] = nb.transform.Find("Extra Damager") != null,
                ["clash_tink"] = clash,
                ["fields"] = fields,
            };
        }

        /// <summary>The swing's tk2d clip: NailSlash turns its collider on at the first non-"Bounce" event frame and off at the second.</summary>
        private static object Clip(tk2dSpriteAnimator an, string name)
        {
            if (an == null || string.IsNullOrEmpty(name)) return null;
            tk2dSpriteAnimationClip clip;
            try { clip = an.GetClipByName(name); }
            catch (Exception) { return null; }
            if (clip == null) return null;
            var events = new List<object>();
            var frames = clip.frames ?? new tk2dSpriteAnimationFrame[0];
            for (var i = 0; i < frames.Length; i++)
                if (frames[i] != null && frames[i].triggerEvent) events.Add(new object[] { i, frames[i].eventInfo });
            return new Dictionary<string, object>
            {
                ["name"] = clip.name,
                ["fps"] = clip.fps,
                ["frames"] = frames.Length,
                ["wrap"] = clip.wrapMode.ToString(),
                ["events"] = events,
            };
        }

        private static Dictionary<string, object> Damager(DamageEnemies de, Transform root, Transform attackRoot)
        {
            var f = PlainValues.Fields(de);
            object F(string k) => f.TryGetValue(k, out var v) ? v : null;
            var colliders = new List<object>();
            foreach (var c in de.GetComponents<Collider2D>()) colliders.Add(Collider(c, root, attackRoot));
            return new Dictionary<string, object>
            {
                ["path"] = CrestModule.PathFrom(root, de.transform),
                ["tag"] = de.gameObject.tag,
                ["nail_tag"] = de.gameObject.CompareTag("Nail Attack"),
                ["enabled"] = de.enabled,
                ["active"] = de.gameObject.activeInHierarchy,
                ["attack_type"] = de.attackType.ToString(),
                ["use_nail_damage"] = de.useNailDamage,
                ["nail_damage_mult"] = de.nailDamageMultiplier,
                ["damage_dealt"] = de.damageDealt,
                ["damage_mult"] = de.DamageMultiplier,
                ["damage_mult_per_hit"] = F("damageMultPerHit"),
                ["multi_hitter"] = de.multiHitter,
                ["steps_per_hit"] = de.stepsPerHit,
                ["hits_until_death"] = de.hitsUntilDeath,
                ["magnitude_mult"] = de.magnitudeMult,
                ["silk_generation"] = F("silkGeneration"),
                ["does_not_parry"] = de.doesNotParry,
                ["does_not_critical_hit"] = F("doesNotCriticalHit"),
                ["does_not_tink"] = de.doesNotTink,
                ["direction"] = de.direction,
                ["colliders"] = colliders,
                ["fields"] = f,
            };
        }

        private static readonly List<Shape> Shapes = new List<Shape>(8);

        private static Dictionary<string, object> Collider(Collider2D c, Transform root, Transform attackRoot = null)
        {
            Shapes.Clear();
            ColliderGeometry.Extract(c, Shapes);
            var d = new Dictionary<string, object>
            {
                ["type"] = c.GetType().Name,
                ["enabled"] = c.enabled,
                ["trigger"] = c.isTrigger,
                ["layer"] = c.gameObject.layer,
                ["shapes"] = ShapeList(Shapes),
            };
            if (SwingMatrix(c.transform, attackRoot, out var m))
            {
                Shapes.Clear();
                ColliderGeometry.Extract(c, m, Shapes);
                d["shapes_swing"] = ShapeList(Shapes);
            }
            return d;
        }

        /// <summary>
        /// The collider's localToWorld with the nearest NailAttackBase at or above it (up to the attack root) scaled to its
        /// swing "scale" instead of its current localScale; false when there is none or the two already agree.
        /// </summary>
        private static bool SwingMatrix(Transform t, Transform attackRoot, out Matrix4x4 m)
        {
            m = Matrix4x4.identity;
            if (attackRoot == null || SwingScale == null) return false;
            NailAttackBase nb = null;
            for (var p = t; p != null; p = p.parent)
            {
                nb = p.GetComponent<NailAttackBase>();
                if (nb != null || p == attackRoot) break;
            }
            if (nb == null) return false;
            var nt = nb.transform;
            var scale = SwingScale(nb);
            if ((scale - nt.localScale).sqrMagnitude < 1e-10f) return false;
            var parent = nt.parent != null ? nt.parent.localToWorldMatrix : Matrix4x4.identity;
            m = parent * Matrix4x4.TRS(nt.localPosition, nt.localRotation, scale) * nt.worldToLocalMatrix * t.localToWorldMatrix;
            return true;
        }

        private static List<object> ShapeList(List<Shape> shapes)
        {
            var list = new List<object>(shapes.Count);
            foreach (var s in shapes)
                list.Add(new Dictionary<string, object> { ["k"] = s.Kind, ["v"] = s.Verts, ["r"] = s.Radius });
            return list;
        }
    }
}
