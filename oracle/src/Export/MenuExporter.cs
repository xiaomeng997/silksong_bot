using System;
using System.Collections.Generic;
using GlobalEnums;
using HarmonyLib;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.Events;
using UnityEngine.UI;

namespace SsOracle.Export
{
    /// <summary>
    /// STATE "menu" (M2 cross-module decision 5; the safety supervisor's pause-and-quit loop, DESIGN §3.7.5): the pause
    /// menu as the player sees it, written while the game is paused (UIManager.uiState PAUSED or GameManager.isPaused),
    /// while the pause menu is still fading out after an unpause (modal dimmer alpha > 0), and from the quit fade until
    /// the GameManager goes; nil otherwise. Keys:
    ///   sel             role of EventSystem.current.currentSelectedGameObject: "continue" / "options" / "quit"
    ///                   (PauseMenuButton.pauseButtonType), "yes" / "no" (the return-to-menu prompt's buttons, by the
    ///                   UIManager method their persistent listeners call: UIReturnToMainMenu / UILeaveExitToMenuPrompt;
    ///                   failing that, by height inside UIManager.returnMainMenuPrompt, Yes above No as probe P7 saw),
    ///                   "back" (a MenuScreen's backButton, e.g. Options), "ok" (GenericMessageCanvas, e.g. SAVE_FAILED),
    ///                   nil for nothing selected or anything else
    ///   quit_ok         the pause menu's Quit PauseMenuButton.interactable, once MenuButtonList.SetupActive of the
    ///                   pause menu has run in this pause (ShowMenu runs it one frame after the pause; it greys Quit
    ///                   while disableSaveQuit or ScenePreloader.HasPendingOperations, m0:C8); nil before that, because
    ///                   until then the value is the previous pause's
    ///   dim             UIManager.modalDimmer.alpha (fades to 0.8 on pause, to 0 on unpause)
    ///   alpha           alpha of the CanvasGroup of the menu screen shown last (UIManager.fadingMenuScreen: set when
    ///                   ShowMenu starts, before menuState changes; the person's session read menuState stale for 8
    ///                   paused frames)
    ///   ignore_unpause  UIManager.ignoreUnpause (true while GoToPauseMenu runs: Continue / Cancel are ignored then)
    ///   quitting        CameraController.FadeOut(TO_MENU) has been called on this GameManager: ReturnToMainMenu got
    ///                   past its save (a failed save stops before the fade, m0:C9) and the quit can no longer be undone
    /// Per frame while not paused: one field read and one CanvasGroup.alpha get. While paused: a cached role lookup by
    /// instance id, two CanvasGroup.alpha gets and two field reads; GetComponent only when the selection changes.
    /// </summary>
    internal sealed class MenuExporter : IExporter
    {
        public string Key => "menu";

        private static readonly AccessTools.FieldRef<UIManager, bool> IgnoreUnpause = Hero.Refs.Field<UIManager, bool>("ignoreUnpause");
        private static readonly AccessTools.FieldRef<UIManager, MenuScreen> FadingMenuScreen = Hero.Refs.Field<UIManager, MenuScreen>("fadingMenuScreen");

        public static void Install(Harmony harmony)
        {
            FrameExporter.Register(new MenuExporter());
            Events.Tap.Patch(harmony, typeof(CameraController), "FadeOut", new[] { typeof(CameraFadeType) }, typeof(MenuExporter), postfix: nameof(FadeOutPostfix));
            Events.Tap.Patch(harmony, typeof(MenuButtonList), "SetupActive", new Type[0], typeof(MenuExporter), postfix: nameof(SetupActivePostfix));
        }

        // ---- hooks (main thread) -----------------------------------------------------------------------------

        private static int quitGm;                 // GameManager instance id the TO_MENU fade started on; 0 = none
        private static MenuButtonList lastSetup;   // the MenuButtonList whose SetupActive ran last, and when
        private static int lastSetupFrame = int.MinValue;

        private static void FadeOutPostfix(CameraFadeType type)
        {
            if (type != CameraFadeType.TO_MENU) return;
            var gm = GameManager._instance;
            quitGm = gm != null ? gm.GetInstanceID() : 0;
        }

        private static void SetupActivePostfix(MenuButtonList __instance)
        {
            lastSetup = __instance;
            lastSetupFrame = Time.frameCount;
        }

        // ---- per frame ---------------------------------------------------------------------------------------

        private UIManager uiSeen;               // the UIManager the caches below belong to
        private PauseMenuButton quitButton;
        private MenuButtonList pauseList;
        private MenuScreen alphaScreen;
        private CanvasGroup alphaGroup;
        private int pauseStart = int.MinValue;  // first frame of the current pause
        private bool wasPaused;
        private readonly Dictionary<int, string> roles = new Dictionary<int, string>();
        private static readonly List<Selectable> SelScratch = new List<Selectable>(8);
        private int errorsLogged;

        public void Write(Ipc.MsgPackWriter w, FrameContext ctx)
        {
            var gm = ctx.Gm;
            var ui = gm != null ? gm.ui : null;
            if (gm == null || ui == null)
            {
                wasPaused = false;
                w.Nil();
                return;
            }
            string sel = null;
            bool? quitOk = null;
            float dim, alpha = 0f;
            bool ignore, quitting;
            try
            {
                if (quitGm != 0 && (quitGm != gm.GetInstanceID() || gm.GameState == GameState.MAIN_MENU)) quitGm = 0;
                quitting = quitGm != 0;
                var paused = ui.uiState == UIState.PAUSED || gm.isPaused;
                if (paused && !wasPaused) pauseStart = (int)ctx.Frame;
                wasPaused = paused;
                dim = ui.modalDimmer != null ? ui.modalDimmer.alpha : 0f;
                if (!paused && !quitting && !(dim > 0f))
                {
                    w.Nil();
                    return;
                }
                if (!ReferenceEquals(ui, uiSeen) || quitButton == null) Rebind(ui);
                var es = EventSystem.current;
                var go = es != null ? es.currentSelectedGameObject : null;
                sel = go != null ? RoleOf(go, ui) : null;
                if (quitButton != null && pauseList != null && ReferenceEquals(lastSetup, pauseList) && lastSetupFrame >= pauseStart)
                    quitOk = quitButton.interactable;
                var screen = FadingMenuScreen != null ? FadingMenuScreen(ui) : null;
                if (!ReferenceEquals(screen, alphaScreen))
                {
                    alphaScreen = screen;
                    alphaGroup = screen != null ? screen.GetComponent<CanvasGroup>() : null;
                }
                alpha = alphaGroup != null ? alphaGroup.alpha : 0f;
                ignore = IgnoreUnpause != null && IgnoreUnpause(ui);
            }
            catch (Exception e)
            {
                if (errorsLogged++ < 5) Core.Plugin.Log.LogWarning("menu exporter: " + e.GetType().Name + ": " + e.Message);
                w.Nil();
                return;
            }
            w.MapHeader(6);
            w.Key("sel"); w.Str(sel);
            w.Key("quit_ok"); if (quitOk.HasValue) w.Bool(quitOk.Value); else w.Nil();
            w.Key("dim"); w.Float(dim);
            w.Key("alpha"); w.Float(alpha);
            w.Key("ignore_unpause"); w.Bool(ignore);
            w.Key("quitting"); w.Bool(quitting);
        }

        /// <summary>A new UIManager (after Save &amp; Quit everything is rebuilt, m0:N42): find the pause menu's Quit
        /// button and MenuButtonList once, and forget the role cache.</summary>
        private void Rebind(UIManager ui)
        {
            uiSeen = ui;
            roles.Clear();
            quitButton = null;
            pauseList = null;
            alphaScreen = null;
            alphaGroup = null;
            var pm = ui.pauseMenuScreen;
            if (pm == null) return;
            pauseList = pm.GetComponent<MenuButtonList>();
            foreach (var b in pm.GetComponentsInChildren<PauseMenuButton>(true))
                if (b.pauseButtonType == PauseMenuButton.PauseButtonType.Quit) quitButton = b;
        }

        private string RoleOf(GameObject go, UIManager ui)
        {
            var id = go.GetInstanceID();
            if (roles.TryGetValue(id, out var role)) return role;
            role = ComputeRole(go, ui);
            if (roles.Count > 256) roles.Clear();
            roles[id] = role;
            return role;
        }

        private static string ComputeRole(GameObject go, UIManager ui)
        {
            var pmb = go.GetComponent<PauseMenuButton>();
            if (pmb != null) return PauseRole(pmb.pauseButtonType);
            if (go.GetComponentInParent<GenericMessageCanvas>(true) != null) return "ok";
            var mb = go.GetComponent<MenuButton>();
            if (mb != null)
            {
                var byListener = ListenerRole(mb.OnSubmitPressed);
                var trigger = go.GetComponent<EventTrigger>();
                if (byListener == null && trigger != null && trigger.triggers != null)
                    foreach (var t in trigger.triggers)
                        if (byListener == null && t != null) byListener = ListenerRole(t.callback);
                if (byListener != null) return byListener;
                var screen = go.GetComponentInParent<MenuScreen>(true);
                if (screen != null && ReferenceEquals(screen.backButton, mb)) return "back";
            }
            var prompt = ui.returnMainMenuPrompt;
            if (prompt != null && go.transform.IsChildOf(prompt.transform)) return PromptRoleByHeight(go, prompt);
            return null;
        }

        private static string ListenerRole(UnityEventBase ev)
        {
            if (ev == null) return null;
            var n = ev.GetPersistentEventCount();
            for (var i = 0; i < n; i++)
            {
                var role = MethodRole(ev.GetPersistentMethodName(i));
                if (role != null) return role;
            }
            return null;
        }

        /// <summary>Yes above No (probe P7): the higher interactable selectable of the prompt is Yes.</summary>
        private static string PromptRoleByHeight(GameObject go, MenuScreen prompt)
        {
            SelScratch.Clear();
            prompt.GetComponentsInChildren(false, SelScratch);
            float y = go.transform.position.y, best = float.MinValue;
            var others = 0;
            foreach (var s in SelScratch)
            {
                if (s == null || s.gameObject == go) continue;
                others++;
                best = Mathf.Max(best, s.transform.position.y);
            }
            SelScratch.Clear();
            if (others == 0) return null;
            return y > best ? "yes" : "no";
        }

        // ---- pure mapping (oracle/tests/ExportsCheck) --------------------------------------------------------

        public static string PauseRole(PauseMenuButton.PauseButtonType t)
        {
            switch (t)
            {
                case PauseMenuButton.PauseButtonType.Continue: return "continue";
                case PauseMenuButton.PauseButtonType.Options: return "options";
                case PauseMenuButton.PauseButtonType.Quit: return "quit";
                default: return null;
            }
        }

        /// <summary>The role a button has from the UIManager method its persistent listener calls.</summary>
        public static string MethodRole(string method)
        {
            switch (method)
            {
                case "UIReturnToMainMenu": return "yes";
                case "UILeaveExitToMenuPrompt": return "no";
                case "UIGoBack": return "back";
                default: return null;
            }
        }
    }
}
