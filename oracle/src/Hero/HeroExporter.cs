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

            if (pd != null)
            {
                K(w, "health", ref n); w.Int(pd.health);
                K(w, "max_health", ref n); w.Int(pd.maxHealth);
                K(w, "health_blue", ref n); w.Int(pd.healthBlue);
                K(w, "silk", ref n); w.Int(pd.silk);
                K(w, "silk_max", ref n); Int(w, pd, SilkMax);
                K(w, "silk_parts", ref n); w.Int(pd.silkParts);
                K(w, "silk_regen_max", ref n); w.Int(pd.silkRegenMax);
                K(w, "spool_broken", ref n); w.Bool(pd.IsSilkSpoolBroken);
                K(w, "geo", ref n); w.Int(pd.geo);
                K(w, "shell_shards", ref n); w.Int(pd.ShellShards);
                K(w, "crest", ref n); w.Str(pd.CurrentCrestID);
                K(w, "any_cursed", ref n); Pred(w, pd, AnyCursed);
                K(w, "is_invincible", ref n); w.Bool(pd.isInvincible);
                K(w, "fractured_mask", ref n); WriteFracturedMask(w, pd);
                CollectTools(pd, out var extra);
                K(w, "tools", ref n);
                w.ArrayHeader(toolNames.Count);
                foreach (var t in toolNames) w.Str(t);
                K(w, "tool_amounts", ref n);
                w.ArrayHeader(toolAmounts.Count);
                foreach (var a in toolAmounts) w.Int(a);
                K(w, "tools_extra", ref n); w.Int(extra);
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
        private static readonly Func<PlayerData, int> SilkMax = pd => pd.CurrentSilkMax;

        /// <summary>Evaluate before writing, so an exception (e.g. a null Config mid-load) costs only this value.</summary>
        private void Pred<T>(MsgPackWriter w, T target, Func<T, bool> f)
        {
            bool v;
            try { v = f(target); }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.Bool(v);
        }

        private void Int<T>(MsgPackWriter w, T target, Func<T, int> f)
        {
            int v;
            try { v = f(target); }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.Int(v);
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
        /// IsEquipped goes through ManagerSingleton&lt;ToolItemManager&gt;.Instance, so it is only read when the
        /// manager exists (otherwise the getter would search the scene).
        /// </summary>
        private void WriteFracturedMask(MsgPackWriter w, PlayerData pd)
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
                equipped = ManagerSingleton<ToolItemManager>.UnsafeInstance != null ? tool.IsEquipped : (bool?)null;
                amount = pd.GetToolData(maskToolName).AmountLeft;
            }
            catch (Exception e) { LogOnce(e); w.Nil(); return; }
            w.MapHeader(2);
            w.Key("equipped"); if (equipped.HasValue) w.Bool(equipped.Value); else w.Nil();
            w.Key("amount_left"); w.Int(amount);
        }

        /// <summary>
        /// Equipped tools = the slots of ToolEquips[CurrentCrestID] (the list GetEquippedToolsForCrest maps) followed
        /// by the filled ExtraToolEquips slots, each with its saved AmountLeft (m0 §2.7). Read straight from PlayerData
        /// to avoid the LINQ/ToList allocations of ToolItemManager.GetEquippedToolsForCrest. Empty slots are skipped.
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
                            if (Add(pd, kv.Value.EquippedTool)) extra++;
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

        private bool Add(PlayerData pd, string tool)
        {
            if (string.IsNullOrEmpty(tool)) return false;
            toolNames.Add(tool);
            toolAmounts.Add(pd.GetToolData(tool).AmountLeft);
            return true;
        }
    }
}
