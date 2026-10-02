using System;
using System.Collections.Generic;
using HarmonyLib;
using SsOracle.Export;
using SsOracle.Ipc;
using UnityEngine;

namespace SsOracle.Hero
{
    /// <summary>
    /// STATE "hero" (DESIGN §3.1.2 hero; field sources m0 §3.1 groups "PlayerData" and "hero"). nil while there is
    /// no hero (menus, loads, Save &amp; Quit). Keys use the m0 §3.1 snake_case names. PlayerData keys are only present
    /// when GameManager.playerData exists; they come from ctx.Pd (= GameManager._instance.playerData), never from
    /// hero.playerData, which is a cache refreshed only on Start/Respawn (m0 §2.7).
    ///
    /// "hunter_meter" is the Hunter combo meter (HeroController.HunterUpgState.CurrentMeterHits): it counts nail hits
    /// that generate silk while Hunter_v2/v3 is equipped (nail damage multipliers from the Gameplay.HunterCombo* thresholds
    /// on, RPC gameplay.dump) and stays 0 for every other crest; each reset is a "hunter_meter" event (Events.HunterMeterTap).
    ///
    /// M2 keys (field list, sources, units and time bases: docs/facts/1.0.30000/state_fields_m2.md): "tm" (the private
    /// timers and step counters the kinematics and i-frame models otherwise reconstruct from history), "alpha" (physics
    /// phase), "wall" ([touchingWallL, touchingWallR]; the wall side, which facing only implies while wall-sliding),
    /// "tags" (pending damage-tag hits) and "tool_max" (capacity aligned with "tools"). The kinematics review found the
    /// frame-to-step jitter decides 0 or 1 physics steps per frame (fs 0 in 20.7% of trial frames), so the planner needs
    /// alpha live rather than estimated.
    ///
    /// Enum-valued keys are ints; names come from RPC "schema.hero". The cState bitset order comes from RPC
    /// "schema.cstate". Can*() predicates are limited to side-effect-free ones: CanJump() zeroes the ledge buffer
    /// and raycasts, CanDoubleJump() queues wall-jump interrupts, CanThrowTool() fires failure events, so they
    /// are not called (tool uses CanThrowTool(false), which skips GetWillThrowTool).
    /// </summary>
    internal sealed class HeroExporter : IExporter
    {
        public string Key => "hero";

        private static readonly AccessTools.FieldRef<SerializableNamedList<ToolCrestsData.SlotData, FloatingCrestSlotsData.NamedData>, Dictionary<string, ToolCrestsData.SlotData>> ExtraSlots =
            Refs.Field<SerializableNamedList<ToolCrestsData.SlotData, FloatingCrestSlotsData.NamedData>, Dictionary<string, ToolCrestsData.SlotData>>("RuntimeData");

        // Reused every frame (allocation-light per C14).
        private readonly List<string> toolNames = new List<string>(16);
        private readonly List<int> toolAmounts = new List<int>(16);

        // UnityEngine.Object.name allocates a new string per call: cache it per tool asset.
        private UnityEngine.Object maskToolRef;
        private string maskToolName;
        private int errorsLogged;

        public void Write(MsgPackWriter w, FrameContext ctx)
        {
            var hero = ctx.Hero;
            var cs = hero != null ? hero.cState : null;
            if (hero == null || cs == null || !CStateSchema.Ready) { w.Nil(); return; }
            var pd = ctx.Pd;

            var pos = hero.transform.position;
            var body = hero.Body;
            var vel = body != null ? body.linearVelocity : Vector2.zero;

            var at = w.BeginMap16();
            var n = 0;
            K(w, "pos", ref n); w.Vec3(pos.x, pos.y, pos.z);
            K(w, "vel", ref n); if (body != null) w.Vec2(vel.x, vel.y); else w.Nil();
            K(w, "facing", ref n); w.Int(cs.facingRight ? 1 : -1);
            K(w, "box", ref n); WriteBox(w, hero);
            K(w, "hero_state", ref n); w.Int((int)hero.hero_state);
            K(w, "transition_state", ref n); w.Int((int)hero.transitionState);
            K(w, "damage_mode", ref n); w.Int((int)hero.damageMode);
            K(w, "lock_state", ref n); w.Int((int)hero.HeroLockState);
            K(w, "hero_accepting_input", ref n); w.Bool(hero.acceptingInput);
            K(w, "control_relinquished", ref n); w.Bool(hero.controlReqlinquished);
            K(w, "stunned", ref n); w.Bool(hero.IsStunned);
            K(w, "parry_invuln_timer", ref n); w.Float(hero.parryInvulnTimer);
            K(w, "can_take_damage", ref n); Pred(w, hero, CanTakeDamage);
            K(w, "lifeblood", ref n); w.Bool(hero.IsInLifebloodState);
            K(w, "invincibility_source", ref n); w.Bool(HeroInvincibilitySource.IsActive);
            K(w, "invulnerable", ref n); w.Bool(cs.Invulnerable);
            K(w, "invulnerable_count", ref n);
            if (CStateSchema.InvulnerableCount != null) w.Int(CStateSchema.InvulnerableCount(cs)); else w.Nil();
            K(w, "cstate", ref n); CStateSchema.WriteBits(w, cs);
            K(w, "cstate_int", ref n); CStateSchema.WriteInts(w, cs);
            K(w, "can", ref n); WriteCan(w, hero);
            K(w, "anim", ref n); WriteAnim(w, hero);
            K(w, "spell", ref n); WriteSpell(w, hero);
            K(w, "hunter_meter", ref n); w.Int(Events.HunterMeterTap.Meter(hero));
            K(w, "alpha", ref n); WriteAlpha(w);
            K(w, "wall", ref n); w.ArrayHeader(2); w.Bool(hero.touchingWallL); w.Bool(hero.touchingWallR);
            K(w, "tm", ref n); WriteTimers(w, hero, cs, body);
            K(w, "tags", ref n); WriteTags(w, hero);

            if (pd != null)
            {
                K(w, "health", ref n); w.Int(pd.health);
                K(w, "max_health", ref n); w.Int(pd.maxHealth);
                K(w, "health_blue", ref n); w.Int(pd.healthBlue);
                K(w, "silk", ref n); w.Int(pd.silk);
                K(w, "silk_max", ref n); WriteSilkMax(w, pd, hero);
                K(w, "silk_parts", ref n); w.Int(pd.silkParts);
                K(w, "silk_regen_max", ref n); w.Int(pd.silkRegenMax);
                K(w, "spool_broken", ref n); w.Bool(pd.IsSilkSpoolBroken);
                K(w, "geo", ref n); w.Int(pd.geo);
                K(w, "shell_shards", ref n); w.Int(pd.ShellShards);
                K(w, "crest", ref n); w.Str(pd.CurrentCrestID);
                K(w, "any_cursed", ref n); Pred(w, pd, AnyCursed);
                K(w, "is_invincible", ref n); w.Bool(pd.isInvincible);
                K(w, "fractured_mask", ref n); WriteFracturedMask(w, pd, hero);
                CollectTools(pd, out var extra);
                K(w, "tools", ref n);
                w.ArrayHeader(toolNames.Count);
                foreach (var t in toolNames) w.Str(t);
                K(w, "tool_amounts", ref n);
                w.ArrayHeader(toolAmounts.Count);
                for (var i = 0; i < toolAmounts.Count; i++)
                    if (toolNames[i] != null) w.Int(toolAmounts[i]); else w.Nil();
                K(w, "tools_extra", ref n); w.Int(extra);
                K(w, "tool_max", ref n); WriteToolMax(w, hero);
                K(w, "respawn", ref n);
                w.MapHeader(6);
                w.Key("scene"); w.Str(pd.respawnScene);
                w.Key("marker"); w.Str(pd.respawnMarkerName);
                w.Key("type"); w.Int(pd.respawnType);
                w.Key("temp_scene"); w.Str(pd.tempRespawnScene);
                w.Key("temp_marker"); w.Str(pd.tempRespawnMarker);
                w.Key("temp_type"); w.Int(pd.tempRespawnType);
                K(w, "hazard_respawn", ref n);
                var hz = pd.hazardRespawnLocation;
                w.ArrayHeader(3); w.Float(hz.x); w.Float(hz.y); w.Int((int)pd.hazardRespawnFacing);
            }
            w.EndMap16(at, n);
        }

        private static void K(MsgPackWriter w, string key, ref int n)
        {
            w.Key(key);
            n++;
        }

        // Static delegates: no allocation per call.
        private static readonly Func<HeroController, bool> CanTakeDamage = h => h.CanTakeDamage();
        private static readonly Func<HeroController, bool> CanDash = h => h.CanDash();
        private static readonly Func<HeroController, bool> CanAttack = h => h.CanAttack();
        private static readonly Func<HeroController, bool> CanThrowTool = h => h.CanThrowTool(false);
        private static readonly Func<HeroController, bool> CanBind = h => h.CanBind();
        private static readonly Func<HeroController, bool> CanHarpoonDash = h => h.CanHarpoonDash();
        private static readonly Func<HeroController, bool> CanSuperJump = h => h.CanSuperJump();
        private static readonly Func<HeroController, bool> CanCast = h => h.CanCast();
        private static readonly Func<HeroController, bool> CanInput = h => h.CanInput();
        private static readonly Func<PlayerData, bool> AnyCursed = pd => pd.IsAnyCursed;

        /// <summary>Evaluate before writing, so an exception (e.g. a null Config mid-load) costs only this value.</summary>
        private void Pred<T>(MsgPackWriter w, T target, Func<T, bool> f)
        {
            bool v;
            try { v = f(target); }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.Bool(v);
        }

        /// <summary>
        /// PlayerData.CurrentSilkMax, or nil while ToolItemManager (or PlayerData.instance) is missing: the getter
        /// goes through the spool extender's IsEquipped, which would search the scene then (SafeReads).
        /// </summary>
        private void WriteSilkMax(MsgPackWriter w, PlayerData pd, HeroController hero)
        {
            bool ok;
            int v;
            try { ok = SafeReads.TrySilkMax(pd, hero, out v); }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            if (ok) w.Int(v); else w.Nil();
        }

        private void LogOnce(Exception e)
        {
            if (errorsLogged++ < 5) Core.Plugin.Log.LogWarning("hero exporter: " + e.GetType().Name + ": " + e.Message);
        }

        private static void WriteBox(MsgPackWriter w, HeroController hero)
        {
            Bounds b;
            try { b = hero.Bounds; }
            catch (Exception) { w.Nil(); return; }
            var min = b.min;
            var max = b.max;
            w.ArrayHeader(4); w.Float(min.x); w.Float(min.y); w.Float(max.x); w.Float(max.y);
        }

        private void WriteCan(MsgPackWriter w, HeroController hero)
        {
            w.MapHeader(8);
            w.Key("dash"); Pred(w, hero, CanDash);
            w.Key("attack"); Pred(w, hero, CanAttack);
            w.Key("tool"); Pred(w, hero, CanThrowTool);
            // CanBind reads ManagerSingleton<HeroChargeEffects>.Instance, which runs FindAnyObjectByType when missing.
            w.Key("bind");
            if (ManagerSingleton<HeroChargeEffects>.UnsafeInstance != null) Pred(w, hero, CanBind);
            else w.Nil();
            w.Key("harpoon"); Pred(w, hero, CanHarpoonDash);
            w.Key("super_jump"); Pred(w, hero, CanSuperJump);
            w.Key("cast"); Pred(w, hero, CanCast);
            w.Key("input"); Pred(w, hero, CanInput);
        }

        /// <summary>
        /// tk2d animator of the hero (HeroController.AnimCtrl.animator). CurrentFrame does not null-check the clip
        /// and returns frames.Length for a finished Once clip, so it is guarded and clamped (m0 §2.7).
        /// </summary>
        private void WriteAnim(MsgPackWriter w, HeroController hero)
        {
            string clipName;
            int frame, count, spriteId;
            float fps, t;
            bool playing;
            try
            {
                var ctrl = hero.AnimCtrl;
                var an = ctrl != null ? ctrl.animator : null;
                var clip = an != null ? an.CurrentClip : null;
                if (clip == null) { w.Nil(); return; }
                clipName = clip.name;
                var frames = clip.frames;
                count = frames != null ? frames.Length : 0;
                frame = count > 0 ? Mathf.Clamp(an.CurrentFrame, 0, count - 1) : -1;
                spriteId = frame >= 0 && frames[frame] != null ? frames[frame].spriteId : -1;
                fps = an.ClipFps > 0f ? an.ClipFps : clip.fps;
                t = fps > 0f ? an.ClipTimeSeconds : 0f;
                playing = an.Playing;
            }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.MapHeader(7);
            w.Key("clip"); w.Str(clipName);
            w.Key("frame"); w.Int(frame);
            w.Key("n"); w.Int(count);
            w.Key("fps"); w.Float(fps);
            w.Key("t"); w.Float(t);
            w.Key("sid"); w.Int(spriteId);
            w.Key("playing"); w.Bool(playing);
        }

        /// <summary>
        /// ["state", state_time] of the hero's "Spell Control" FSM, which runs Bind and the silk skills. The bool
        /// cState.isBinding is in the bitset; this adds the phase and its elapsed time (DESIGN hero.bind{active,t}).
        /// </summary>
        private void WriteSpell(MsgPackWriter w, HeroController hero)
        {
            string state;
            float time;
            try
            {
                var fsmComp = hero.spellControl;
                if (fsmComp == null) { w.Nil(); return; }
                var fsm = fsmComp.Fsm;
                var st = fsm != null ? fsm.ActiveState : null;
                if (st == null) { w.Nil(); return; }
                state = st.Name;
                time = st.StateTime;
            }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.ArrayHeader(2); w.Str(state); w.Float(time);
        }

        /// <summary>
        /// {equipped, amount_left} with the same predicate PlayerData.TakeHealth uses: FracturedMaskTool.IsEquipped
        /// (false while cursed or while tools are in the Cutscene state) and its saved AmountLeft (m0:C2).
        /// IsEquipped goes through ManagerSingleton&lt;ToolItemManager&gt;.Instance, HeroController.instance and
        /// PlayerData.instance, so it is only read when SafeReads.ToolsReadable (otherwise nil).
        /// </summary>
        private void WriteFracturedMask(MsgPackWriter w, PlayerData pd, HeroController hero)
        {
            bool? equipped;
            int amount;
            try
            {
                var tool = GlobalSettings.Gameplay.FracturedMaskTool;
                if (tool == null) { w.Nil(); return; }
                if (!ReferenceEquals(tool, maskToolRef))
                {
                    maskToolRef = tool;
                    maskToolName = tool.name;
                }
                equipped = SafeReads.ToolsReadable(hero) ? tool.IsEquipped : (bool?)null;
                amount = pd.GetToolData(maskToolName).AmountLeft;
            }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.MapHeader(2);
            w.Key("equipped"); if (equipped.HasValue) w.Bool(equipped.Value); else w.Nil();
            w.Key("amount_left"); w.Int(amount);
        }

        /// <summary>
        /// Equipped tools with the semantics of ToolItemManager.GetCurrentEquippedTools (m0 §2.7): one entry per slot
        /// of ToolEquips[CurrentCrestID] in slot order, nil for an empty slot (GetEquippedToolsForCrest keeps nulls, and
        /// the slot index is what fixes the slot's type and Up/Neutral/Down binding), followed by the filled
        /// ExtraToolEquips slots (counted by tools_extra). Amounts are the saved AmountLeft, nil for an empty slot.
        /// Read straight from PlayerData to avoid the LINQ/ToList allocations of the ToolItemManager methods.
        /// </summary>
        private void CollectTools(PlayerData pd, out int extra)
        {
            toolNames.Clear();
            toolAmounts.Clear();
            extra = 0;
            try
            {
                var crest = pd.CurrentCrestID;
                if (!string.IsNullOrEmpty(crest) && pd.ToolEquips != null)
                {
                    var slots = pd.ToolEquips.GetData(crest).Slots;
                    if (slots != null)
                        for (var i = 0; i < slots.Count; i++)
                            Add(pd, slots[i].EquippedTool);
                }
                if (pd.ExtraToolEquips != null && ExtraSlots != null)
                {
                    var dict = ExtraSlots(pd.ExtraToolEquips);
                    if (dict != null)
                        foreach (var kv in dict)
                            if (!string.IsNullOrEmpty(kv.Value.EquippedTool))
                            {
                                Add(pd, kv.Value.EquippedTool);
                                extra++;
                            }
                }
            }
            catch (Exception e)
            {
                LogOnce(e);
                toolNames.Clear();
                toolAmounts.Clear();
                extra = 0;
            }
        }

        /// <summary>One slot: an empty slot is kept as a null name (written as nil in both arrays).</summary>
        private void Add(PlayerData pd, string tool)
        {
            if (string.IsNullOrEmpty(tool))
            {
                toolNames.Add(null);
                toolAmounts.Add(0);
                return;
            }
            toolNames.Add(tool);
            toolAmounts.Add(pd.GetToolData(tool).AmountLeft);
        }

        // ---- M2 additions: timers, physics phase, walls, damage tags, tool capacity ---------------------------

        private static readonly AccessTools.FieldRef<HeroController, float> InvulnDuration = Refs.Field<HeroController, float>("invulnerableDuration");
        private static readonly AccessTools.FieldRef<HeroController, float> InvulnFreeze = Refs.Field<HeroController, float>("invulnerableFreezeDuration");
        private static readonly AccessTools.FieldRef<HeroController, float> RecoilTimer = Refs.Field<HeroController, float>("recoilTimer");
        private static readonly AccessTools.FieldRef<HeroController, int> RecoilSteps = Refs.Field<HeroController, int>("recoilStepsLeft");
        private static readonly AccessTools.FieldRef<HeroController, float> DashCooldown = Refs.Field<HeroController, float>("dashCooldownTimer");
        private static readonly AccessTools.FieldRef<HeroController, float> AttackCooldown = Refs.Field<HeroController, float>("attack_cooldown");
        private static readonly AccessTools.FieldRef<HeroController, float> AttackTime = Refs.Field<HeroController, float>("attack_time");
        private static readonly AccessTools.FieldRef<HeroController, float> ToolCooldown = Refs.Field<HeroController, float>("throwToolCooldown");
        private static readonly AccessTools.FieldRef<HeroController, int> JumpSteps = Refs.Field<HeroController, int>("jump_steps");
        private static readonly AccessTools.FieldRef<HeroController, int> JumpedSteps = Refs.Field<HeroController, int>("jumped_steps");
        private static readonly AccessTools.FieldRef<HeroController, int> JumpQueue = Refs.Field<HeroController, int>("jumpQueueSteps");
        private static readonly AccessTools.FieldRef<HeroController, int> AttackQueue = Refs.Field<HeroController, int>("attackQueueSteps");
        private static readonly AccessTools.FieldRef<HeroController, int> ToolQueue = Refs.Field<HeroController, int>("toolThrowQueueSteps");
        private static readonly AccessTools.FieldRef<HeroController, TagDamageTaker> TagTaker = Refs.Field<HeroController, TagDamageTaker>("tagDamageTaker");
        private static readonly AccessTools.FieldRef<DamageTag, int> TagAmount = Refs.Field<DamageTag, int>("damageAmount");

        /// <summary>
        /// hero.alpha: (Time.time - Time.fixedTime) / Time.fixedDeltaTime at end of frame, the phase of the physics
        /// clock inside the current fixed step (in [0, 1) unless Unity capped the fixed steps of a long frame). Doubles,
        /// because the float clocks lose a fifth of a 0.02 s step to rounding after about a day of play time.
        /// </summary>
        private static void WriteAlpha(MsgPackWriter w)
        {
            var fdt = Time.fixedDeltaTime;
            if (!(fdt > 0f)) { w.Nil(); return; }
            w.Float((float)((Time.timeAsDouble - Time.fixedTimeAsDouble) / fdt));
        }

        private static void FloatOrNil(MsgPackWriter w, AccessTools.FieldRef<HeroController, float> f, HeroController h)
        {
            if (f != null) w.Float(f(h)); else w.Nil();
        }

        private static void IntOrNil(MsgPackWriter w, AccessTools.FieldRef<HeroController, int> f, HeroController h)
        {
            if (f != null) w.Int(f(h)); else w.Nil();
        }

        /// <summary>
        /// hero.tm: HeroController's private timers and step counters (all FieldRef reads, no Unity call except the
        /// rigidbody's gravityScale). Time values are seconds of scaled game time (they count Time.deltaTime), step
        /// values count FixedUpdate steps or input frames as the game does. inv = what StartInvulnerable's coroutine
        /// has left (invulnerableFreezeDuration + invulnerableDuration, each floored at 0; after a hit INVUL_TIME 1.0,
        /// times Gameplay.WeightedAnkletDmgInvulnMult with the anklet); the other i-frame sources stay in their own keys
        /// (parry_invuln_timer, invulnerable_count, the downspike steps in cstate_int). recoil = damage recoil left:
        /// RECOIL_DURATION - recoilTimer while cState.recoiling, the full RECOIL_DURATION while recoilFrozen (the hit's
        /// FreezeMoment runs first), else 0.
        /// </summary>
        private static void WriteTimers(MsgPackWriter w, HeroController h, HeroControllerStates cs, Rigidbody2D body)
        {
            w.MapHeader(15);
            w.Key("inv");
            if (InvulnDuration != null && InvulnFreeze != null)
                w.Float(Mathf.Max(0f, InvulnFreeze(h)) + Mathf.Max(0f, InvulnDuration(h)));
            else w.Nil();
            w.Key("recoil");
            if (RecoilTimer != null)
                w.Float(cs.recoiling ? Mathf.Max(0f, h.RECOIL_DURATION - RecoilTimer(h)) : cs.recoilFrozen ? h.RECOIL_DURATION : 0f);
            else w.Nil();
            w.Key("recoil_steps"); IntOrNil(w, RecoilSteps, h);
            w.Key("dash_cd"); FloatOrNil(w, DashCooldown, h);
            w.Key("atk_cd"); FloatOrNil(w, AttackCooldown, h);
            w.Key("atk_t"); FloatOrNil(w, AttackTime, h);
            w.Key("tool_cd"); FloatOrNil(w, ToolCooldown, h);
            w.Key("jump_steps"); IntOrNil(w, JumpSteps, h);
            w.Key("jumped_steps"); IntOrNil(w, JumpedSteps, h);
            w.Key("ds"); w.Float(h.downSpikeTimer);
            w.Key("ds_rec"); w.Float(h.downSpikeRecoveryTimer);
            w.Key("grav"); if (body != null) w.Float(body.gravityScale); else w.Nil();
            w.Key("qj"); IntOrNil(w, JumpQueue, h);
            w.Key("qa"); IntOrNil(w, AttackQueue, h);
            w.Key("qt"); IntOrNil(w, ToolQueue, h);
        }

        private struct TagSnap
        {
            public string Kind;
            public int DmgLeft;
            public float TLeft;
        }

        private readonly List<TagSnap> tagSnaps = new List<TagSnap>(4);
        private readonly Dictionary<DamageTag, string> tagNames = new Dictionary<DamageTag, string>(Entities.RefComparer<DamageTag>.Instance);

        /// <summary>
        /// hero.tags: the hero's active damage tags (TagDamageTaker.TaggedDamage: acid, frost water, ...), each
        /// {kind: the DamageTag asset name, dmg_left: masks still to come = hits left x the tag's damageAmount (before
        /// Barbed Wire and the Fractured Mask; -1 for a tag without a hit limit, which ticks until its source removes it,
        /// e.g. while swimming in frost water), t_left: seconds of scaled game time (the Time.timeAsDouble clock the tag
        /// uses) until its next hit lands}. dmg_left and t_left are the conservative pair for hits_to_death: all the
        /// damage still pending and the earliest moment any of it lands. nil without a TagDamageTaker.
        /// </summary>
        private void WriteTags(MsgPackWriter w, HeroController hero)
        {
            tagSnaps.Clear();
            try
            {
                var taker = TagTaker != null ? TagTaker(hero) : null;
                if (taker == null) { w.Nil(); return; }
                if (taker.TaggedDamage is Dictionary<DamageTag, DamageTagInfo> dict && dict.Count > 0)
                {
                    var now = Time.timeAsDouble;
                    foreach (var kv in dict)
                    {
                        var tag = kv.Key;
                        var info = kv.Value;
                        if (tag == null || info == null) continue;
                        if (!tagNames.TryGetValue(tag, out var kind))
                        {
                            if (tagNames.Count > 64) tagNames.Clear();   // assets only; bound it anyway
                            tagNames[tag] = kind = tag.name;
                        }
                        tagSnaps.Add(new TagSnap
                        {
                            Kind = kind,
                            DmgLeft = TagDmgLeft(info.RemoveAfterNextHit, tag.TotalHitLimit, info.HitsLeft, TagAmount != null ? TagAmount(tag) : 1),
                            TLeft = (float)Math.Max(0.0, info.NextHitTime - now),
                        });
                    }
                }
            }
            catch (Exception e)
            {
                LogOnce(e);
                w.Nil();
                return;
            }
            w.ArrayHeader(tagSnaps.Count);
            foreach (var t in tagSnaps)
            {
                w.MapHeader(3);
                w.Key("kind"); w.Str(t.Kind);
                w.Key("dmg_left"); w.Int(t.DmgLeft);
                w.Key("t_left"); w.Float(t.TLeft);
            }
        }

        /// <summary>
        /// Damage a tag still deals (TagDamageTaker.Tick): a tag marked RemoveAfterNextHit hits once more; one with a
        /// TotalHitLimit hits HitsLeft more times; one without a limit (HitsLeft stays 0) keeps hitting until its source
        /// removes it, reported as -1 (unbounded).
        /// </summary>
        public static int TagDmgLeft(bool removeAfterNextHit, int totalHitLimit, int hitsLeft, int amount)
        {
            var hits = removeAfterNextHit ? 1 : totalHitLimit > 0 ? hitsLeft : -1;
            return hits < 0 ? -1 : hits * amount;
        }

        private readonly List<int> toolMax = new List<int>(16);

        /// <summary>
        /// hero.tool_max, aligned with hero.tools: ToolItemManager.GetToolStorageAmount of each equipped tool (base
        /// storage plus Tool Pouch upgrades and the Shell Satchel; the custom override amount for an overridden tool),
        /// nil for an empty slot or an unknown tool name. The whole key is nil while SafeReads.ToolsReadable is false
        /// (the getter goes through ToolItemManager.Instance and IsEquippedHud).
        /// </summary>
        private void WriteToolMax(MsgPackWriter w, HeroController hero)
        {
            toolMax.Clear();
            try
            {
                if (!SafeReads.ToolsReadable(hero)) { w.Nil(); return; }
                for (var i = 0; i < toolNames.Count; i++)
                {
                    var name = toolNames[i];
                    var tool = name != null ? ToolItemManager.GetToolByName(name) : null;
                    toolMax.Add(tool != null ? ToolItemManager.GetToolStorageAmount(tool) : -1);
                }
            }
            catch (Exception e)
            {
                LogOnce(e);
                w.Nil();
                return;
            }
            w.ArrayHeader(toolMax.Count);
            foreach (var m in toolMax)
                if (m >= 0) w.Int(m); else w.Nil();
        }
    }
}
