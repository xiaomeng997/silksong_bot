using HarmonyLib;
using UnityEngine;
using UnityEngine.InputSystem;

namespace SsOracle.Core
{
    /// <summary>
    /// Makes the training copy a polite desktop citizen: it keeps simulating while unfocused, never hides
    /// or locks the OS cursor, and ignores the mouse entirely (hovering over a menu would otherwise move
    /// the selection). Training only; the final copy is vanilla.
    /// </summary>
    internal sealed class TrainingEnvironment : MonoBehaviour
    {
        public static void Install(GameObject host, Harmony harmony)
        {
            harmony.Patch(
                AccessTools.Method(typeof(InputHandler), "SetCursorEnabled"),
                prefix: new HarmonyMethod(typeof(TrainingEnvironment), nameof(SetCursorEnabledPrefix)));

            InputSystem.onDeviceChange += (device, change) =>
            {
                if (device is Mouse && (change == InputDeviceChange.Added || change == InputDeviceChange.Enabled))
                    InputSystem.DisableDevice(device);
            };
            foreach (var device in InputSystem.devices)
            {
                if (device is Mouse && device.enabled)
                    InputSystem.DisableDevice(device);
            }

            // The default (ResetAndDisableNonBackgroundDevices) disables the keyboard on focus loss, which
            // would drop injected key events in unfocused instances.
            InputSystem.settings.backgroundBehavior = InputSettings.BackgroundBehavior.IgnoreFocus;

            host.AddComponent<TrainingEnvironment>();
        }

        // InputHandler hides and locks the cursor during gameplay; skip it.
        private static bool SetCursorEnabledPrefix()
        {
            ReleaseCursor();
            return false;
        }

        private bool loggedOriginals;

        // A PlayMaker action and the language selector also touch the cursor, so re-assert every frame.
        private void LateUpdate()
        {
            if (!loggedOriginals && InControl.InputManager.IsSetup)
            {
                loggedOriginals = true;
                Plugin.Log.LogInfo($"serialized input settings: InControl.SuspendInBackground={InControl.InputManager.SuspendInBackground}, " +
                                   $"InputSystem.updateMode={InputSystem.settings.updateMode}, runInBackground(before)={Application.runInBackground}");
            }

            // With SuspendInBackground, InControl stops updating while unfocused, so no action sees injected keys.
            if (InControl.InputManager.SuspendInBackground)
                InControl.InputManager.SuspendInBackground = false;
            if (!Application.runInBackground)
                Application.runInBackground = true;
            if (!Cursor.visible || Cursor.lockState != CursorLockMode.None)
                ReleaseCursor();
        }

        private static void ReleaseCursor()
        {
            Cursor.visible = true;
            Cursor.lockState = CursorLockMode.None;
        }
    }
}
