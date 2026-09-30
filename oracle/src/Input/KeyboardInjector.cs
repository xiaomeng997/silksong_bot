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
    /// The legacy Input.anyKeyDown callers are covered by LegacyInputShim.
    /// </summary>
    internal static class KeyboardInjector
    {
        /// <summary>Button names in bit order of the ACTION `buttons` mask (shared with brain/ssbot/ipc).</summary>
        public static readonly string[] ButtonNames =
        {
            "jump", "attack", "dash", "bind", "clawline", "needolin", "quickcast", "taunt",
            "inventory", "map", "tools", "journal", "quests", "quickmap", "pause", "enter",
            "paneleft", "paneright", "up", "down", "left", "right",
        };

        private static readonly Key[] ButtonKeys =
        {
            Key.Z, Key.X, Key.C, Key.A, Key.S, Key.D, Key.F, Key.V,
            Key.I, Key.M, Key.Q, Key.J, Key.T, Key.Tab, Key.Escape, Key.Enter,
            Key.LeftBracket, Key.RightBracket, Key.UpArrow, Key.DownArrow, Key.LeftArrow, Key.RightArrow,
        };

        private const uint LeftBit = 1u << 20, RightBit = 1u << 21;

        private static readonly Dictionary<string, int> Bit = BuildBitIndex();

        private static volatile uint requested;
        private static uint latched;
        private static Key[] latchedKeys = new Key[0];

        /// <summary>When false, the real keyboard works as usual (for playing the training copy by hand).</summary>
        public static volatile bool OwnsKeyboard = true;

        /// <summary>The button mask the game saw in the current frame (main thread only).</summary>
        public static uint LatchedMask => latched;
        public static Key[] Latched => latchedKeys;

        public static void Install() => InputSystem.onBeforeUpdate += OnBeforeUpdate;

        /// <summary>Thread-safe: replace the held button set; takes effect at the next dynamic input update.</summary>
        public static bool TrySetMask(uint mask, out string error)
        {
            if ((mask & LeftBit) != 0 && (mask & RightBit) != 0)
            {
                error = "left and right together are rejected (MoveVector cancels but Left/Right.IsPressed stay true)";
                return false;
            }
            if (mask >> ButtonNames.Length != 0)
            {
                error = $"unknown button bits 0x{mask >> ButtonNames.Length << ButtonNames.Length:x}";
                return false;
            }
            requested = mask;
            error = null;
            return true;
        }

        /// <summary>Thread-safe name-based variant (debug line protocol).</summary>
        public static bool TrySetKeys(IEnumerable<string> names, out string error)
        {
            uint mask = 0;
            foreach (var name in names)
            {
                if (!Bit.TryGetValue(name, out var b))
                {
                    error = $"unknown key '{name}'";
                    return false;
                }
                mask |= 1u << b;
            }
            return TrySetMask(mask, out error);
        }

        public static void ReleaseAll() => requested = 0;

        private static void OnBeforeUpdate()
        {
            // Latch once per frame on the main thread; fixed and before-render updates reuse the frame's set.
            if (InputState.currentUpdateType != InputUpdateType.Dynamic) return;
            ActionScheduler.Tick(UnityEngine.Time.frameCount);
            var mask = requested;
            if (mask != latched)
            {
                latched = mask;
                latchedKeys = ToKeys(mask);
            }
            LegacyInputShim.OnLatched(latched);
            if (!OwnsKeyboard) return;
            var keyboard = Keyboard.current;
            if (keyboard == null) return;
            InputSystem.QueueStateEvent(keyboard, new KeyboardState(latchedKeys));
        }

        private static Key[] ToKeys(uint mask)
        {
            var keys = new List<Key>(4);
            for (var i = 0; i < ButtonKeys.Length; i++)
                if ((mask & (1u << i)) != 0) keys.Add(ButtonKeys[i]);
            return keys.ToArray();
        }

        private static Dictionary<string, int> BuildBitIndex()
        {
            var d = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (var i = 0; i < ButtonNames.Length; i++) d[ButtonNames[i]] = i;
            return d;
        }
    }
}
