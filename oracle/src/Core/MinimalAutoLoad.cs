using GlobalEnums;
using UnityEngine;

namespace SsOracle.Core
{
    /// <summary>
    /// Minimal mode (RunMode.Minimal) with "-ssbot-minimal-load N": once the main menu is up and settled, load save slot
    /// N the way the save-select screen does (GameManager.LoadGameFromUI), then remove itself, so nothing of the oracle
    /// runs per frame during the measurement.
    /// </summary>
    internal sealed class MinimalAutoLoad : MonoBehaviour
    {
        private float readySince = -1f;

        private void Update()
        {
            var gm = GameManager._instance;
            var ui = gm != null ? gm.ui : null;
            if (ui == null || gm.GameState != GameState.MAIN_MENU || ui.menuState != MainMenuState.MAIN_MENU || ui.IsFadingMenu)
            {
                readySince = -1f;
                return;
            }
            if (readySince < 0f) readySince = Time.unscaledTime;
            if (Time.unscaledTime - readySince < 2f) return;   // let the title settle
            Plugin.Log.LogWarning($"minimal mode: loading save slot {RunMode.MinimalLoadSlot}");
            gm.LoadGameFromUI(RunMode.MinimalLoadSlot);
            Destroy(this);
        }
    }
}
