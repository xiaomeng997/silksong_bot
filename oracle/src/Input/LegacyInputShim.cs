using System;
using System.Collections.Generic;
using System.Reflection;
using System.Reflection.Emit;
using HarmonyLib;

namespace SsOracle.Input
{
    /// <summary>
    /// Legacy-input shim (DESIGN §3.1.1 Input, m0:N36, m0 §3.3): the game still reads UnityEngine.Input.anyKeyDown for
    /// cutscene skips (InputHandler.CutsceneInput / StagCutsceneInput), the engage screen (GameManager.UpdateEngagement),
    /// the idle GC (IdleMemoryCleaner.HadAnyInputLastFrame), PlayMaker AnyKey / WaitAnyKey (ActionHelpers.AnyKeyDown) and
    /// BossDoorChallengeCompleteUI. Events queued into the Input System never reach the legacy Input manager, while the
    /// final copy's SendInput keys reach both, so without this shim TRAIN and FINAL would differ in cutscene skipping
    /// (including an accidental ENDING skip) and in the idle GC stall. Each call site is transpiled to AnyKeyDownAt(site),
    /// which ORs in the injected key-down edge of this frame. While the injector owns the keyboard the physical legacy
    /// keys and mouse are masked too, like the Input System side (a click that focuses a training window must not skip
    /// its cutscene).
    /// </summary>
    internal static partial class LegacyInputShim
    {
        private static uint previous;
        private static Func<bool> legacyAnyKeyDown;
        private static MethodInfo legacyGetter;
        private static int replacedTotal;

        /// <summary>Every legacy anyKeyDown call site in 1.0.30000 (grep of the decompiled Assembly-CSharp), one each.</summary>
        private static readonly (Type Type, string Method)[] Sites =
        {
            (typeof(InputHandler), "CutsceneInput"),
            (typeof(InputHandler), "StagCutsceneInput"),
            (typeof(GameManager), "UpdateEngagement"),
            (typeof(IdleMemoryCleaner), "HadAnyInputLastFrame"),
            (typeof(HutongGames.PlayMaker.ActionHelpers), "AnyKeyDown"),
            (typeof(BossDoorChallengeCompleteUI), "Update"),
        };

        private static readonly Dictionary<string, int> SiteIndex = new Dictionary<string, int>();
        private static readonly long[] SiteHits = new long[Sites.Length];
        private static readonly bool[] SitePatched = new bool[Sites.Length];

        /// <summary>True during the frame in which some injected button went from up to down.</summary>
        public static bool InjectedKeyDownThisFrame { get; private set; }

        public static int SitesPatched { get; private set; }
        public static int SitesExpected => Sites.Length;

        public static void OnLatched(uint mask)
        {
            InjectedKeyDownThisFrame = (mask & ~previous) != 0;
            previous = mask;
        }

        /// <summary>Replacement for the Input.anyKeyDown getter at call site <paramref name="site"/>.</summary>
        public static bool AnyKeyDownAt(int site)
        {
            if (InjectedKeyDownThisFrame)
            {
                if ((uint)site < (uint)SiteHits.Length) SiteHits[site]++;
                return true;
            }
            return !KeyboardInjector.OwnsKeyboard && legacyAnyKeyDown != null && legacyAnyKeyDown();
        }

        public static void Install(Harmony harmony)
        {
            // Input lives in UnityEngine.InputLegacyModule, which the project does not reference at compile time.
            var inputType = AccessTools.TypeByName("UnityEngine.Input");
            legacyGetter = inputType != null ? AccessTools.PropertyGetter(inputType, "anyKeyDown") : null;
            if (legacyGetter == null)
            {
                Core.Plugin.Log.LogError("LegacyInputShim: UnityEngine.Input.anyKeyDown not found; cutscene skips will differ from the final copy");
                return;
            }
            legacyAnyKeyDown = (Func<bool>)Delegate.CreateDelegate(typeof(Func<bool>), legacyGetter);

            var transpiler = new HarmonyMethod(typeof(LegacyInputShim), nameof(Transpiler));
            for (var i = 0; i < Sites.Length; i++)
            {
                var (type, name) = Sites[i];
                var method = AccessTools.Method(type, name);
                if (method == null)
                {
                    Core.Plugin.Log.LogError($"LegacyInputShim: {type.Name}.{name} not found");
                    continue;
                }
                SiteIndex[SiteKey(method)] = i;
                var before = replacedTotal;
                try
                {
                    harmony.Patch(method, transpiler: transpiler);
                }
                catch (Exception e)
                {
                    Core.Plugin.Log.LogError($"LegacyInputShim: patching {type.Name}.{name} failed: {e.Message}");
                    continue;
                }
                var replaced = replacedTotal - before;
                if (replaced != 1)
                {
                    Core.Plugin.Log.LogError($"LegacyInputShim: expected 1 Input.anyKeyDown call in {type.Name}.{name}, replaced {replaced}");
                    if (replaced == 0) continue;
                }
                SitePatched[i] = true;
                SitesPatched++;
            }
            if (SitesPatched == Sites.Length)
                Core.Plugin.Log.LogInfo($"LegacyInputShim: {SitesPatched}/{Sites.Length} Input.anyKeyDown call sites shimmed");
            else
                Core.Plugin.Log.LogError($"LegacyInputShim: only {SitesPatched}/{Sites.Length} Input.anyKeyDown call sites shimmed");
        }

        /// <summary>Swaps `call bool Input::get_anyKeyDown()` for `ldc.i4 site; call bool AnyKeyDownAt(int)`: same stack
        /// effect, labels and exception blocks move to the first new instruction.</summary>
        private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions, MethodBase original)
        {
            var site = original != null && SiteIndex.TryGetValue(SiteKey(original), out var s) ? s : -1;
            var replacement = AccessTools.Method(typeof(LegacyInputShim), nameof(AnyKeyDownAt));
            foreach (var ins in instructions)
            {
                if (ins.Calls(legacyGetter))
                {
                    replacedTotal++;
                    var load = new CodeInstruction(OpCodes.Ldc_I4, site);
                    load.labels.AddRange(ins.labels);
                    load.blocks.AddRange(ins.blocks);
                    yield return load;
                    yield return new CodeInstruction(OpCodes.Call, replacement);
                    continue;
                }
                yield return ins;
            }
        }

        private static string SiteKey(MethodBase m) => m.DeclaringType?.FullName + "::" + m.Name;

        /// <summary>For input.stats: per call site, whether it is shimmed and how often an injected edge answered it.</summary>
        public static Dictionary<string, object> Describe()
        {
            var sites = new Dictionary<string, object>();
            for (var i = 0; i < Sites.Length; i++)
            {
                sites[Sites[i].Type.Name + "." + Sites[i].Method] = new Dictionary<string, object>
                {
                    ["patched"] = SitePatched[i],
                    ["injected_hits"] = SiteHits[i],
                };
            }
            return new Dictionary<string, object>
            {
                ["sites_patched"] = SitesPatched,
                ["sites_expected"] = Sites.Length,
                ["sites"] = sites,
            };
        }
    }
}
