using System.Collections.Generic;
using System.Runtime.CompilerServices;
using HarmonyLib;

namespace SsOracle.Events
{
    /// <summary>
    /// "pause_gate" edges for the pause/quit blockers the brain cannot see directly (DESIGN §3.1.1 EventTap,
    /// m0 §2.4). Hooks name the writer: InputHandler.PreventPause/AllowPause, GameManager.SetIsInventoryOpen,
    /// UIMsgProxy.SetIsInMsg, GenericMessageCanvas, and the name-based PlayerData setters that FSMs use for
    /// disablePause/disableSaveQuit/disableInventory (SetBool and SetVariable, m0 §2.4). C# code also writes
    /// disablePause directly (Die, StartRecoil, doors: m0:N15); the per-frame poll reports those as src "poll".
    /// Observe-only: this class never writes any gate (m0:N43).
    /// </summary>
    internal static class GateTap
    {
        public const int DisablePause = 0, DisableSaveQuit = 1, DisableInventory = 2, InventoryOpen = 3, PauseAllowed = 4, MsgCanvas = 5, Count = 6;

        public static readonly string[] Names =
            { "disable_pause", "disable_save_quit", "disable_inventory", "inventory_open", "pause_allowed", "msg_canvas" };

        // -1 = unknown (the next poll baselines silently), else 0/1.
        private static readonly sbyte[] Last = { -1, -1, -1, -1, -1, -1 };
        private static int gmId, pdId;

        /// <summary>Current gate values as bits (1 << gate), for the "tap" STATE section.</summary>
        public static uint Bits
        {
            get
            {
                uint b = 0;
                for (var i = 0; i < Count; i++)
                    if (Last[i] > 0) b |= 1u << i;
                return b;
            }
        }

        public static void Install(Harmony h)
        {
            Tap.Patch(h, typeof(InputHandler), "PreventPause", new System.Type[0], typeof(GateTap), postfix: nameof(PreventPausePostfix));
            Tap.Patch(h, typeof(InputHandler), "AllowPause", new System.Type[0], typeof(GateTap), postfix: nameof(AllowPausePostfix));
            Tap.Patch(h, typeof(GameManager), "SetIsInventoryOpen", new[] { typeof(bool) }, typeof(GateTap), postfix: nameof(SetIsInventoryOpenPostfix));
            Tap.Patch(h, typeof(UIMsgProxy), "SetIsInMsg", new[] { typeof(bool) }, typeof(GateTap), postfix: nameof(SetIsInMsgPostfix));
            Tap.Patch(h, typeof(PlayerData), "SetBool", new[] { typeof(string), typeof(bool) }, typeof(GateTap), postfix: nameof(SetBoolPostfix));
            Tap.Patch(h, typeof(PlayerData), "OnUpdatedVariable", new[] { typeof(string) }, typeof(GateTap), postfix: nameof(OnUpdatedVariablePostfix));
            Tap.Patch(h, typeof(PlayerData), "ResetCutsceneBools", new System.Type[0], typeof(GateTap), postfix: nameof(ResetCutsceneBoolsPostfix));
            Tap.Patch(h, typeof(GenericMessageCanvas), "Show", new[] { typeof(string), typeof(System.Action) }, typeof(GateTap), postfix: nameof(MsgShowPostfix));
            Tap.Patch(h, typeof(GenericMessageCanvas), "OkButtonClicked", new System.Type[0], typeof(GateTap), postfix: nameof(MsgOkPostfix));
        }

        /// <summary>Forget every gate (brain reconnected): the next poll baselines without emitting.</summary>
        public static void Reset()
        {
            for (var i = 0; i < Count; i++) Last[i] = -1;
        }

        /// <summary>
        /// Record a gate value; emits on a change. <paramref name="silentIfUnknown"/> is for the poll, whose first
        /// look after a reset is a baseline; hooks report even then because they saw an explicit write.
        /// </summary>
        public static void Observe(int gate, bool value, string src, bool silentIfUnknown, bool withCaller, Dictionary<string, object> extra = null)
        {
            var v = (sbyte)(value ? 1 : 0);
            var old = Last[gate];
            Last[gate] = v;
            if (old == v || (old < 0 && silentIfUnknown) || !Tap.Active) return;
            var d = extra ?? Tap.Data(8);
            d["gate"] = Names[gate];
            d["value"] = value;
            d["src"] = src;
            Tap.Attribute(d, withCaller);
            Tap.Emit("pause_gate", d);
        }

        /// <summary>Per frame (EventsRunner.LateUpdate): catch direct field writes and re-baseline when the core objects change.</summary>
        public static void Poll(GameManager gm, PlayerData pd)
        {
            var ih = gm != null ? gm.inputHandler : null;
            if (gm == null || pd == null || ih == null)
            {
                Reset();
                return;
            }
            var g = gm.GetInstanceID();
            var p = RuntimeHelpers.GetHashCode(pd);
            if (g != gmId || p != pdId)
            {
                gmId = g;
                pdId = p;
                Reset();
            }
            Observe(DisablePause, pd.disablePause, "poll", true, false);
            Observe(DisableSaveQuit, pd.disableSaveQuit, "poll", true, false);
            Observe(DisableInventory, pd.disableInventory, "poll", true, false);
            Observe(InventoryOpen, pd.isInventoryOpen, "poll", true, false);
            Observe(PauseAllowed, ih.PauseAllowed, "poll", true, false);
            Observe(MsgCanvas, GenericMessageCanvas.IsActive, "poll", true, false);
        }

        private static PlayerData Pd()
        {
            var gm = GameManager._instance;
            return gm != null ? gm.playerData : null;
        }

        private static void PreventPausePostfix(InputHandler __instance) =>
            Observe(PauseAllowed, __instance.PauseAllowed, "InputHandler.PreventPause", false, true);

        private static void AllowPausePostfix(InputHandler __instance) =>
            Observe(PauseAllowed, __instance.PauseAllowed, "InputHandler.AllowPause", false, true);

        private static void SetIsInventoryOpenPostfix()
        {
            var pd = Pd();
            if (pd != null) Observe(InventoryOpen, pd.isInventoryOpen, "GameManager.SetIsInventoryOpen", false, false);
        }

        /// <summary>Item/UI messages set disablePause directly and restore the old value on close (m0:N15).</summary>
        private static void SetIsInMsgPostfix(UIMsgProxy __instance, bool value)
        {
            if (Tap.Active)
            {
                var d = Tap.Data(8);
                d["gate"] = "in_msg";
                d["value"] = value;
                d["src"] = "UIMsgProxy.SetIsInMsg";
                d["object"] = __instance != null ? __instance.name : null;
                Tap.Attribute(d, false);
                Tap.Emit("pause_gate", d);
            }
            var pd = Pd();
            if (pd != null) Observe(DisablePause, pd.disablePause, "UIMsgProxy.SetIsInMsg", false, false);
        }

        private static int GateOf(string name)
        {
            switch (name)
            {
                case "disablePause": return DisablePause;
                case "disableSaveQuit": return DisableSaveQuit;
                case "disableInventory": return DisableInventory;
                default: return -1;
            }
        }

        private static bool Read(PlayerData pd, int gate)
        {
            switch (gate)
            {
                case DisablePause: return pd.disablePause;
                case DisableSaveQuit: return pd.disableSaveQuit;
                default: return pd.disableInventory;
            }
        }

        private static void SetBoolPostfix(PlayerData __instance, string boolName)
        {
            var gate = GateOf(boolName);
            if (gate >= 0) Observe(gate, Read(__instance, gate), "PlayerData.SetBool", false, true);
        }

        private static void OnUpdatedVariablePostfix(PlayerData __instance, string variableName)
        {
            var gate = GateOf(variableName);
            if (gate >= 0) Observe(gate, Read(__instance, gate), "PlayerData.SetVariable", false, true);
            else HpTap.OnUpdatedVariable(__instance, variableName);
        }

        private static void ResetCutsceneBoolsPostfix(PlayerData __instance)
        {
            Observe(DisablePause, __instance.disablePause, "PlayerData.ResetCutsceneBools", false, true);
            Observe(DisableSaveQuit, __instance.disableSaveQuit, "PlayerData.ResetCutsceneBools", false, false);
            Observe(DisableInventory, __instance.disableInventory, "PlayerData.ResetCutsceneBools", false, false);
        }

        private static void MsgShowPostfix(string errorKey)
        {
            var d = Tap.Data(8);
            d["key"] = errorKey;
            Observe(MsgCanvas, GenericMessageCanvas.IsActive, "GenericMessageCanvas.Show", false, true, d);
        }

        private static void MsgOkPostfix() =>
            Observe(MsgCanvas, GenericMessageCanvas.IsActive, "GenericMessageCanvas.OkButtonClicked", false, false);
    }
}
