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
    /// Between the requested set and the latch sits the HoldFilter (minimum press / release, left-right exclusion;
    /// DESIGN C19, m0:N37), which the final SendInput sink enforces too, so both paths drop the same taps.
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
        public const uint PauseBit = 1u << 14;

        private static readonly Dictionary<string, int> Bit = BuildBitIndex();

        private static volatile uint requested;
        private static uint latched;
        private static Key[] latchedKeys = new Key[0];

        /// <summary>Main thread only (OnBeforeUpdate and RPC handlers).</summary>
        public static readonly HoldFilter Filter = new HoldFilter(LeftBit, RightBit);

        /// <summary>When false, the real keyboard works as usual (for playing the training copy by hand).</summary>
        public static volatile bool OwnsKeyboard = true;

        /// <summary>The button mask the game saw in the current frame (main thread only).</summary>
        public static uint LatchedMask => latched;
        public static Key[] Latched => latchedKeys;
        /// <summary>The button set last asked for (by an ACTION, the debug protocol or the harness).</summary>
        public static uint RequestedMask => requested;

        public static void Install() => InputSystem.onBeforeUpdate += OnBeforeUpdate;

        /// <summary>Thread-safe: replace the held button set; takes effect at the next dynamic input update
        /// (subject to the minimum press / release frames). Only the last set before that update is seen.</summary>
        public static bool TrySetMask(uint mask, out string error)
        {
            if (!Validate(mask, out error)) return false;
            requested = mask;
            return true;
        }

        /// <summary>Main thread only (ActionScheduler, before the latch): like TrySetMask, but the set's key edges are
        /// queued in the HoldFilter at once, so every set applied within one input update keeps its edges (a press
        /// followed by its release in the same update is still latched for the minimum press, as inputd holds it).</summary>
        public static bool TryQueueMask(uint mask, out string error)
        {
            if (!Validate(mask, out error)) return false;
            // a plain ACTION: the next EXCLUSIVE one cuts every key it does not ask for; a set another caller made
            // since the last latch keeps its edges too
            Filter.QueuePlain(requested, mask);
            requested = mask;
            return true;
        }

        /// <summary>Main thread only (ActionScheduler, before the latch): the EXCLUSIVE ACTION flag. Every key outside
        /// <paramref name="mask"/> is released on this latch (below its minimum press if need be) and loses its queued
        /// edges (HoldFilter.Exclusive); the mask's own edges are queued as TryQueueMask does. Keys an earlier
        /// EXCLUSIVE ACTION of the same stretch asked for (the pause loop's own taps) are not cut: they keep the
        /// minimum press (HoldFilter.QueueExclusive).</summary>
        public static bool TryQueueMaskExclusive(uint mask, out string error)
        {
            if (!Validate(mask, out error)) return false;
            Filter.QueueExclusive(mask);
            requested = mask;
            return true;
        }

        /// <summary>Main thread only: hold exactly <paramref name="mask"/> from the next latch, every other key released
        /// at once and its queued edges dropped (the brain-lost Pause tap: the lost brain's keys are all cut, the pause
        /// loop's included).</summary>
        public static bool SetMaskExclusive(uint mask, out string error)
        {
            if (!Validate(mask, out error)) return false;
            Filter.QueueExclusiveCutAll(mask);
            requested = mask;
            return true;
        }

        private static bool Validate(uint mask, out string error)
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

        /// <summary>Thread-safe: request an empty set, an ordinary release edge (edges already queued in the HoldFilter
        /// still play out).</summary>
        public static void ReleaseAll() => requested = 0;

        /// <summary>Main thread only: release every key as soon as the minimum press allows and drop every edge still
        /// queued in the HoldFilter, so no press requested earlier fires later (brain lost, input.release, harness
        /// operations and their no-input waits).</summary>
        public static void ReleaseAllNow()
        {
            requested = 0;
            Filter.ReleaseAll();
        }

        private static void OnBeforeUpdate()
        {
            // Latch once per frame on the main thread; fixed and before-render updates reuse the frame's set.
            if (InputState.currentUpdateType != InputUpdateType.Dynamic) return;
            ActionScheduler.Tick(UnityEngine.Time.frameCount);
            var mask = Filter.Step(requested);
            if (mask != latched)
            {
                latched = mask;
                latchedKeys = ToKeys(mask);
            }
            // REHEARSAL profiles drive the final sink (SendInput), never the in-engine injector.
            var owns = OwnsKeyboard && Core.Profile.Rules.Injection;
            // The legacy shim must only report edges the game actually receives.
            LegacyInputShim.OnLatched(owns ? latched : 0);
            if (!owns) return;
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

        /// <summary>Counters for the input.stats RPC (main thread).</summary>
        public static Dictionary<string, object> DescribeFilter() => new Dictionary<string, object>
        {
            ["min_press_frames"] = Filter.MinPressFrames,
            ["min_release_frames"] = Filter.MinReleaseFrames,
            ["holds_extended"] = Filter.HoldsExtended,
            ["presses_deferred"] = Filter.PressesDeferred,
            ["lr_deferred"] = Filter.ExclusiveDeferred,
            ["taps_collapsed"] = Filter.TapsCollapsed,
            ["released_early"] = Filter.ReleasedEarly,
            ["pending_edges"] = Filter.PendingToggles,
        };
    }
}
