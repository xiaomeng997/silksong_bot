namespace SsOracle.Hero
{
    /// <summary>
    /// Guards for game getters that end in a singleton search, so per-frame code never triggers one (m0 §2.7).
    /// ToolItem.IsEquipped runs ToolItemManager.IsToolEquipped, which reads ManagerSingleton&lt;ToolItemManager&gt;.Instance
    /// (= SilentInstance: FindAnyObjectByType when missing, then a NullReferenceException on .customToolOverride).
    /// On a toolCache miss it also calls CollectableItemManager.IsInHiddenMode -> HeroController.instance
    /// (FindObjectOfType, then OnHeroInstanceSet and HeroUtility.Reset when it finds a hero) and reads
    /// PlayerData.instance (creates a new PlayerData when there is none). PlayerData.CurrentSilkMax reaches the same
    /// path through Gameplay.SpoolExtenderTool.IsEquipped.
    /// </summary>
    internal static class SafeReads
    {
        /// <summary>True when ToolItem.IsEquipped can run without reaching any of those searches.</summary>
        public static bool ToolsReadable(HeroController hero) =>
            hero != null && ManagerSingleton<ToolItemManager>.UnsafeInstance != null && PlayerData.HasInstance;

        /// <summary>
        /// PlayerData.CurrentSilkMax (CurrentSilkMaxBasic plus SpoolExtenderSilk when the spool extender is equipped)
        /// when ToolsReadable; false otherwise. Wherever the game itself reads CurrentSilkMax the manager exists (the
        /// getter would throw without it), so this only fails in menus, loads and the Save &amp; Quit teardown.
        /// </summary>
        public static bool TrySilkMax(PlayerData pd, HeroController hero, out int silkMax)
        {
            if (pd == null || !ToolsReadable(hero))
            {
                silkMax = 0;
                return false;
            }
            silkMax = pd.CurrentSilkMax;
            return true;
        }
    }
}
