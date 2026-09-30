using System;
using System.Collections.Generic;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;

namespace SsOracle.Input
{
    /// <summary>
    /// Training-only input sink. While it owns the keyboard, it queues one full KeyboardState event per
    /// dynamic input update, so the game reads exactly the injected key set through the same path as real
    /// keys (Input System -> InControl KeyBindingSource -> HeroActions): level-sampled isPressed, the same
    /// WasPressed edges, the same keyboard menu aliases. Queued last in the update, it also masks whatever
    /// the physical keyboard is doing, so typing in another window never reaches a training instance.
    /// Does not reach the legacy Input.anyKeyDown callers (cutscene skip, stag skip); see M1.
    /// </summary>
    internal static class KeyboardInjector
    {
        // Our key names (shared with brain/ssbot/io/sinks) -> Input System physical keys.
        private static readonly Dictionary<string, Key> Map = new Dictionary<string, Key>(StringComparer.OrdinalIgnoreCase)
        {
            ["jump"] = Key.Z, ["attack"] = Key.X, ["dash"] = Key.C, ["bind"] = Key.A,
            ["clawline"] = Key.S, ["needolin"] = Key.D, ["quickcast"] = Key.F, ["taunt"] = Key.V,
            ["inventory"] = Key.I, ["map"] = Key.M, ["tools"] = Key.Q, ["journal"] = Key.J, ["quests"] = Key.T,
            ["quickmap"] = Key.Tab, ["pause"] = Key.Escape, ["enter"] = Key.Enter,
            ["paneleft"] = Key.LeftBracket, ["paneright"] = Key.RightBracket,
            ["up"] = Key.UpArrow, ["down"] = Key.DownArrow, ["left"] = Key.LeftArrow, ["right"] = Key.RightArrow,
        };

        private static volatile Key[] requested = new Key[0];
        private static Key[] latched = new Key[0];

        /// <summary>When false, the real keyboard works as usual (for playing the training copy by hand).</summary>
        public static volatile bool OwnsKeyboard = true;

        /// <summary>The key set the game saw in the current frame (main thread only).</summary>
        public static Key[] Latched => latched;

        public static void Install() => InputSystem.onBeforeUpdate += OnBeforeUpdate;

        /// <summary>Thread-safe: replace the held key set; takes effect at the next dynamic input update.</summary>
        public static bool TrySetKeys(IEnumerable<string> names, out string error)
        {
            var keys = new List<Key>();
            foreach (var name in names)
            {
                if (!Map.TryGetValue(name, out var key))
                {
                    error = $"unknown key '{name}'";
                    return false;
                }
                if (!keys.Contains(key)) keys.Add(key);
            }
            if (keys.Contains(Key.LeftArrow) && keys.Contains(Key.RightArrow))
            {
                error = "left and right together are rejected (MoveVector cancels but Left/Right.IsPressed stay true)";
                return false;
            }
            requested = keys.ToArray();
            error = null;
            return true;
        }

        private static void OnBeforeUpdate()
        {
            // Latch once per frame on the main thread; fixed and before-render updates reuse the frame's set.
            if (InputState.currentUpdateType != InputUpdateType.Dynamic) return;
            latched = requested;
            if (!OwnsKeyboard) return;
            var keyboard = Keyboard.current;
            if (keyboard == null) return;
            InputSystem.QueueStateEvent(keyboard, new KeyboardState(latched));
        }
    }
}
