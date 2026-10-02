using System;
using System.Collections.Generic;
using GlobalEnums;
using HutongGames.PlayMaker;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// STATE "ents" (DESIGN §3.1.2 entities[]): every threat-relevant object within the main camera's view of the
    /// z = 0 plane plus EntityRegistry.Margin, one map per entity:
    ///   iid, type_key, category, src (Src bits), layer, pos [x,y,z], vel [x,y] | nil, gravity_scale | nil,
    ///   hp | nil, is_dead | nil, inv | nil (HealthManager.IsInvincible), fsms [{name, state, t, rt}], anim {clip, frame, n} | nil,
    ///   flipX, render_aabb [minx, miny, maxx, maxy] | nil, hidden,
    ///   colliders [{kind, name, verts_world [x0, y0, x1, y1, ...], enabled, layer, r (circles only), damage | nil}]
    /// damage = {dealt, eff, hazard_type, flags, parry, parryable, can_cause_damage}; see WriteDamage.
    /// hidden (M2): the entity is a HealthManager root exported earlier in this scene, alive, not in view, and out of
    /// sight: root renderer disabled or HealthManager inactive (EntityRegistry.HiddenPass: e.g. the Bell Beast
    /// underground, parked 18 u under the floor with its renderer off); it keeps pos (transform), flipX, fsms, anim and
    /// hp, its colliders are [] and render_aabb is nil unless its renderer is on and its GameObject active (only its
    /// HealthManager off). An entity in view or pulled in by an active damage source of its own is never hidden, so no
    /// threat collider is dropped this way.
    /// colliders[].name (M2): the collider's GameObject name ("PolyCollider", "LeapCollider", or the root's own name
    /// for root colliders); one entry per path of a polygon, all with the same name.
    /// fsms[].t = FsmState.StateTime (scaled; PlayMaker stops it once all of the state's actions have finished),
    /// fsms[].rt = FsmState.StateRealTime (unscaled seconds since the state was entered; never stops, but also runs
    /// through pauses and hit-stop). Exact scaled dwell times come from the "fsm" event frames (FsmTap).
    /// Unity is only touched before the first byte is written (EntityRegistry.Collect, then a gather pass where a
    /// failure drops one entity), so a destroyed object can never leave a half-written msgpack value behind,
    /// which would cost the whole STATE and disable the exporter.
    /// </summary>
    internal sealed class EntityExporter : Export.IExporter
    {
        /// <summary>DamageHero parry bits ("parry"). CLASH: canClashTink, a nail hit tinks off it (hero recoils,
        /// NailClash; DamageHero.TryClashTinkCollider). FORCE: an enabled DamageHero with forceParry, a 0-damage touch
        /// still runs HeroController.CheckParry (HeroBox.TakeDamageFromDamager). COUNTER: hazard ENEMY, the only type
        /// the Cross Stitch parry stance (cState.parrying, needs hasParry) catches (HeroController.TakeDamage,
        /// CheckParry). "parryable" is CLASH or FORCE only: COUNTER holds for nearly every enemy hitbox.</summary>
        public const int ParryClash = 1, ParryForce = 2, ParryCounter = 4;

        /// <summary>The "parryable" flag: the source itself reacts to the nail or forces a parry check (DESIGN
        /// §3.1.2 damage.parryable, forceParry / canClashTink semantics). The Cross Stitch counter is bit COUNTER.</summary>
        public static bool Parryable(int parry) => (parry & (ParryClash | ParryForce)) != 0;

        public string Key => "ents";

        private sealed class ColSnap
        {
            public byte Kind;
            public string Name;
            public int V0, VN;
            public bool Enabled;
            public int Layer;
            public float Radius;
            public bool HasDamage;
            public int Dealt, Eff, Haz, Flags, Parry;
            public bool CanCause;
        }

        private sealed class Snap
        {
            public Entity E;
            public Vector3 Pos;
            public int Layer;
            public bool HasRb;
            public Vector2 Vel;
            public float Grav;
            public bool HasHp, Dead, Inv;
            public int Hp;
            public int F0, FN, C0, CN;
            public string Clip;
            public int Frame, FrameCount;
            public bool Flip;
            public bool Hidden;
            public bool HasAabb;
            public float MinX, MinY, MaxX, MaxY;
        }

        private readonly List<Snap> snaps = new List<Snap>();
        private int snapCount;
        private readonly List<ColSnap> cols = new List<ColSnap>();
        private int colCount;
        private readonly List<float> verts = new List<float>(4096);
        private readonly List<string> fsmNames = new List<string>(64);
        private readonly List<string> fsmStates = new List<string>(64);
        private readonly List<float> fsmTimes = new List<float>(64);
        private readonly List<float> fsmRealTimes = new List<float>(64);
        private float realNow;  // FsmTime.RealtimeSinceStartup, the clock of FsmState.StateRealTime
        private readonly List<Vector2> points = new List<Vector2>(64);
        private static int errorsLogged;

        public void Write(Ipc.MsgPackWriter w, Export.FrameContext ctx)
        {
            var cam = ctx.MainCamera;
            if (ctx.Gm == null || cam == null)
            {
                w.Nil();
                return;
            }

            // The world rectangle the camera sees on the z = 0 plane (the gameplay plane; tk2d perspective camera
            // looking down +z). Objects off that plane are covered by the margin.
            var dist = -cam.transform.position.z;
            if (!(dist > 0.01f)) dist = 10f;
            var a = cam.ViewportToWorldPoint(new Vector3(0f, 0f, dist));
            var b = cam.ViewportToWorldPoint(new Vector3(1f, 1f, dist));

            EntityRegistry.Now = Time.timeAsDouble;
            realNow = FsmTime.RealtimeSinceStartup;
            try
            {
                EntityRegistry.Collect((int)ctx.Frame, Mathf.Min(a.x, b.x), Mathf.Min(a.y, b.y), Mathf.Max(a.x, b.x), Mathf.Max(a.y, b.y));
            }
            catch (Exception ex)
            {
                // Nothing written yet: report "no data" for this frame instead of losing the exporter for good.
                if (errorsLogged++ < 10) Core.Plugin.Log.LogError("ents: selection failed: " + ex);
                EntityRegistry.MarkSceneChanged();
                w.Nil();
                return;
            }

            snapCount = 0;
            colCount = 0;
            verts.Clear();
            fsmNames.Clear();
            fsmStates.Clear();
            fsmTimes.Clear();
            fsmRealTimes.Clear();
            var included = EntityRegistry.Included;
            for (var i = 0; i < included.Count; i++)
                Gather(included[i]);

            w.ArrayHeader(snapCount);
            for (var i = 0; i < snapCount; i++)
                WriteEntity(w, snaps[i]);
        }

        // ---- gather --------------------------------------------------------------------------------------

        private void Gather(Entity e)
        {
            int c0 = colCount, v0 = verts.Count, f0 = fsmNames.Count;
            try
            {
                var go = e.Go;
                if (go == null) return;
                if (snapCount == snaps.Count) snaps.Add(new Snap());
                var s = snaps[snapCount];
                s.E = e;
                s.Pos = e.Pos;
                s.Layer = go.layer;
                var m = e.Tr.localToWorldMatrix;

                var rb = e.Rb;
                s.HasRb = rb != null;
                if (s.HasRb)
                {
                    s.Vel = rb.linearVelocity;
                    s.Grav = rb.gravityScale;
                }

                var hm = e.Hm;
                s.HasHp = hm != null;
                if (s.HasHp)
                {
                    s.Hp = hm.hp;
                    s.Dead = hm.isDead;
                    s.Inv = hm.IsInvincible;
                }

                s.F0 = f0;
                foreach (var f in e.Fsms)
                {
                    if (f == null) continue;
                    var fsm = EntityRegistry.FsmOf(f);
                    if (fsm == null) continue;
                    var st = fsm.ActiveState;
                    fsmNames.Add(fsm.Name);
                    fsmStates.Add(st?.Name);
                    fsmTimes.Add(st != null ? st.StateTime : 0f);
                    fsmRealTimes.Add(st != null ? realNow - st.RealStartTime : 0f);
                }
                s.FN = fsmNames.Count - f0;

                s.Clip = null;
                var anim = e.Anim;
                if (anim != null)
                {
                    var clip = anim.CurrentClip;
                    if (clip != null)
                    {
                        var n = clip.frames?.Length ?? 0;
                        s.Clip = clip.name;
                        s.FrameCount = n;
                        s.Frame = n > 0 ? SafeFrame(anim, n) : 0;
                    }
                }

                var sprite = e.Sprite;
                s.Flip = (m.m00 < 0f) ^ (sprite != null && sprite.FlipX);
                s.Hidden = e.Hidden;

                var r = e.Renderer;
                s.HasAabb = r != null && r.enabled && (!s.Hidden || go.activeInHierarchy);
                if (s.HasAabb)
                {
                    var bounds = r.bounds;
                    var min = bounds.min;
                    var max = bounds.max;
                    s.MinX = min.x; s.MinY = min.y; s.MaxX = max.x; s.MaxY = max.y;
                }

                s.C0 = c0;
                if (!s.Hidden)
                    foreach (var slot in e.Colliders)
                        GatherCollider(slot, ref m, s.Layer);
                s.CN = colCount - c0;
                snapCount++;
            }
            catch (Exception ex)
            {
                // Roll back this entity only; the frame and the exporter carry on.
                colCount = c0;
                verts.RemoveRange(v0, verts.Count - v0);
                var nf = fsmNames.Count - f0;
                fsmNames.RemoveRange(f0, nf);
                fsmStates.RemoveRange(f0, nf);
                fsmTimes.RemoveRange(f0, nf);
                fsmRealTimes.RemoveRange(f0, nf);
                if (errorsLogged++ < 10)
                    Core.Plugin.Log.LogWarning($"ents: skipped entity {e.Iid} '{e.TypeKey}': {ex.GetType().Name}: {ex.Message}");
            }
        }

        /// <summary>CurrentFrame does not null-check, can return frames.Length in Once mode and divides by the loop
        /// length in the loop modes (m0 §3 tk2d row), so clamp it and never let it cost the entity.</summary>
        private static int SafeFrame(tk2dSpriteAnimator anim, int n)
        {
            try
            {
                return Mathf.Clamp(anim.CurrentFrame, 0, n - 1);
            }
            catch (Exception)
            {
                return 0;
            }
        }

        private ColSnap NextCol()
        {
            if (colCount == cols.Count) cols.Add(new ColSnap());
            return cols[colCount++];
        }

        private void GatherCollider(ColliderSlot slot, ref Matrix4x4 rootM, int rootLayer)
        {
            var c = slot.Col;
            if (c == null) return;
            if (!slot.OnRoot && !slot.Go.activeInHierarchy) return;
            colName = slot.Name;
            var enabled = c.enabled;
            var layer = slot.OnRoot ? rootLayer : slot.Go.layer;
            var m = slot.OnRoot ? rootM : slot.Tr.localToWorldMatrix;

            // Damage first: it is shared by every path of a multi-path polygon.
            bool hasDamage = true, can = false;
            int dealt = 0, eff = 0, haz = 0, flags = 0, parry = 0;
            if (slot.DmgFsm != null)
            {
                // Legacy PlayMaker damager (HeroBox.CheckForDamage reads these two ints; no flags, always armed).
                dealt = slot.DmgVar?.Value ?? 0;
                haz = slot.HazVar?.Value ?? (int)HazardType.ENEMY;
                eff = Effective(dealt, haz, 0);
                parry = haz == (int)HazardType.ENEMY ? ParryCounter : 0;
                can = true;
            }
            else if (slot.Dh != null)
            {
                var dh = slot.Dh;
                var on = dh.enabled;
                dealt = on ? dh.damageDealt : 0;  // HeroBox treats a disabled DamageHero as 0 damage
                haz = (int)dh.hazardType;
                flags = (int)dh.damagePropertyFlags;
                parry = (dh.canClashTink ? ParryClash : 0) | (on && dh.forceParry ? ParryForce : 0)
                        | (dh.hazardType == HazardType.ENEMY ? ParryCounter : 0);
                can = EntityRegistry.CanCauseDamage(dh);
                // STEAM sources zero damageDealt and hurt through the multi-wounder FSM; TakeDamage makes STEAM 2.
                eff = slot.MultiWounder ? 2 : Effective(dealt, haz, flags);
            }
            else if (slot.Cog != null)
            {
                // CogMultiHitter: 0.35 s after contact, DamageHeroDirectly -> TakeDamage(1, SPIKES), through i-frames (m0:C3).
                dealt = 1;
                haz = (int)HazardType.SPIKES;
                eff = 1;
                can = EntityRegistry.CogCanDamage(slot.Cog);
            }
            else if (slot.MultiWounder)
            {
                // Multi-wounder FSM without a DamageHero: the amount and type live in the FSM (P11 FSM export).
                eff = -1;
                haz = -1;
                can = true;
            }
            else hasDamage = false;

            switch (slot.Shape)
            {
                case ColliderGeometry.Box:
                {
                    var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                    ColliderGeometry.AppendBox(verts, ref m, (BoxCollider2D)c);
                    cs.VN = verts.Count - cs.V0;
                    break;
                }
                case ColliderGeometry.Circle:
                {
                    var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                    cs.Radius = ColliderGeometry.AppendCircle(verts, ref m, (CircleCollider2D)c);
                    cs.VN = verts.Count - cs.V0;
                    break;
                }
                case ColliderGeometry.Capsule:
                {
                    var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                    ColliderGeometry.AppendCapsule(verts, ref m, (CapsuleCollider2D)c);
                    cs.VN = verts.Count - cs.V0;
                    break;
                }
                case ColliderGeometry.Edge:
                {
                    var edge = (EdgeCollider2D)c;
                    points.Clear();
                    edge.GetPoints(points);
                    var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                    ColliderGeometry.AppendPoints(verts, ref m, edge.offset, points);
                    cs.VN = verts.Count - cs.V0;
                    break;
                }
                case ColliderGeometry.Poly:
                {
                    // One entry per path: each is a separate closed outline.
                    var poly = (PolygonCollider2D)c;
                    var off = poly.offset;
                    var paths = poly.pathCount;
                    for (var p = 0; p < paths; p++)
                    {
                        points.Clear();
                        poly.GetPath(p, points);
                        var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                        ColliderGeometry.AppendPoints(verts, ref m, off, points);
                        cs.VN = verts.Count - cs.V0;
                    }
                    break;
                }
                default:
                {
                    var cs = BeginCol(slot.Shape, enabled, layer, hasDamage, dealt, eff, haz, flags, parry, can);
                    ColliderGeometry.AppendBounds(verts, c);
                    cs.VN = verts.Count - cs.V0;
                    break;
                }
            }
        }

        private string colName;  // GatherCollider's current slot, for BeginCol

        private ColSnap BeginCol(byte kind, bool enabled, int layer, bool hasDamage, int dealt, int eff, int haz, int flags, int parry, bool can)
        {
            var cs = NextCol();
            cs.Kind = kind;
            cs.Name = colName;
            cs.V0 = verts.Count;
            cs.VN = 0;
            cs.Enabled = enabled;
            cs.Layer = layer;
            cs.Radius = 0f;
            cs.HasDamage = hasDamage;
            cs.Dealt = dealt;
            cs.Eff = eff;
            cs.Haz = haz;
            cs.Flags = flags;
            cs.Parry = parry;
            cs.CanCause = can;
            return cs;
        }

        /// <summary>
        /// Damage one touch removes after HeroController.TakeDamage's hazard overrides (m0 §3 "Hazard damage";
        /// HeroController.cs:5288-5319), before Barbed Wire and boss-scene multipliers: SPIKES/ACID/COAL/
        /// COAL_SPIKES/ZAP 1, LAVA/STEAM 2, RESPAWN_PIT 0, else damageDealt forced to 2 by the Flame or Void flag.
        /// The overrides only apply when damageDealt > 0.
        /// </summary>
        public static int Effective(int dealt, int hazard, int flags)
        {
            if (dealt <= 0) return 0;
            switch ((HazardType)hazard)
            {
                case HazardType.SPIKES:
                case HazardType.ACID:
                case HazardType.COAL:
                case HazardType.COAL_SPIKES:
                case HazardType.ZAP:
                    return 1;
                case HazardType.LAVA:
                case HazardType.STEAM:
                    return 2;
                case HazardType.RESPAWN_PIT:
                    return 0;
                default:
                    return (flags & (int)(DamagePropertyFlags.Flame | DamagePropertyFlags.Void)) != 0 ? 2 : dealt;
            }
        }

        // ---- write (no Unity calls below this line) ------------------------------------------------------

        private void WriteEntity(Ipc.MsgPackWriter w, Snap s)
        {
            var e = s.E;
            w.MapHeader(17);
            w.Key("iid"); w.Int(e.Iid);
            w.Key("type_key"); w.Str(e.TypeKey);
            w.Key("category"); w.Str(e.Category);
            w.Key("src"); w.UInt((ulong)e.Src);
            w.Key("layer"); w.Int(s.Layer);
            w.Key("pos"); w.Vec3(s.Pos.x, s.Pos.y, s.Pos.z);
            w.Key("vel"); if (s.HasRb) w.Vec2(s.Vel.x, s.Vel.y); else w.Nil();
            w.Key("gravity_scale"); if (s.HasRb) w.Float(s.Grav); else w.Nil();
            w.Key("hp"); if (s.HasHp) w.Int(s.Hp); else w.Nil();
            w.Key("is_dead"); if (s.HasHp) w.Bool(s.Dead); else w.Nil();
            w.Key("inv"); if (s.HasHp) w.Bool(s.Inv); else w.Nil();
            w.Key("fsms");
            w.ArrayHeader(s.FN);
            for (var i = s.F0; i < s.F0 + s.FN; i++)
            {
                w.MapHeader(4);
                w.Key("name"); w.Str(fsmNames[i]);
                w.Key("state"); w.Str(fsmStates[i]);
                w.Key("t"); w.Float(fsmTimes[i]);
                w.Key("rt"); w.Float(fsmRealTimes[i]);
            }
            w.Key("anim");
            if (s.Clip != null)
            {
                w.MapHeader(3);
                w.Key("clip"); w.Str(s.Clip);
                w.Key("frame"); w.Int(s.Frame);
                w.Key("n"); w.Int(s.FrameCount);
            }
            else w.Nil();
            w.Key("flipX"); w.Bool(s.Flip);
            w.Key("render_aabb");
            if (s.HasAabb)
            {
                w.ArrayHeader(4);
                w.Float(s.MinX); w.Float(s.MinY); w.Float(s.MaxX); w.Float(s.MaxY);
            }
            else w.Nil();
            w.Key("hidden"); w.Bool(s.Hidden);
            w.Key("colliders");
            w.ArrayHeader(s.CN);
            for (var i = s.C0; i < s.C0 + s.CN; i++)
                WriteCollider(w, cols[i]);
        }

        private void WriteCollider(Ipc.MsgPackWriter w, ColSnap c)
        {
            var circle = c.Kind == ColliderGeometry.Circle;
            w.MapHeader(circle ? 7 : 6);
            w.Key("kind"); w.Str(ColliderGeometry.KindNames[c.Kind]);
            w.Key("name"); w.Str(c.Name ?? "");
            w.Key("verts_world");
            w.ArrayHeader(c.VN);
            for (var i = c.V0; i < c.V0 + c.VN; i++) w.Float(verts[i]);
            w.Key("enabled"); w.Bool(c.Enabled);
            w.Key("layer"); w.Int(c.Layer);
            if (circle)
            {
                w.Key("r"); w.Float(c.Radius);
            }
            w.Key("damage");
            if (c.HasDamage) WriteDamage(w, c);
            else w.Nil();
        }

        /// <summary>
        /// dealt: DamageHero.damageDealt as HeroBox reads it (0 while the component is disabled), or the
        /// 'damages_hero' FSM's damageDealt int. eff: see Effective; -1 when only an FSM knows. hazard_type:
        /// GlobalEnums.HazardType (-1 unknown). flags: DamagePropertyFlags (SilkAcid 1, NonLethal 2, Flame 4,
        /// Void 8, Acid 16, Self 32, MidChain 64). parry: Parry* bits; parryable = CLASH or FORCE (see Parryable).
        /// can_cause_damage: DamageHero.CanCauseDamage (false during the post-hit or down-spike cooldown).
        /// </summary>
        private static void WriteDamage(Ipc.MsgPackWriter w, ColSnap c)
        {
            w.MapHeader(7);
            w.Key("dealt"); w.Int(c.Dealt);
            w.Key("eff"); w.Int(c.Eff);
            w.Key("hazard_type"); w.Int(c.Haz);
            w.Key("flags"); w.Int(c.Flags);
            w.Key("parry"); w.Int(c.Parry);
            w.Key("parryable"); w.Bool(Parryable(c.Parry));
            w.Key("can_cause_damage"); w.Bool(c.CanCause);
        }
    }
}
