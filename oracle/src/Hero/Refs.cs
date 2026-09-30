using System;
using HarmonyLib;

namespace SsOracle.Hero
{
    /// <summary>
    /// Private-field accessors resolved once. A missing symbol logs an error and yields null instead of throwing
    /// from a static initializer (which would abort Modules.InstallAll and take the whole oracle down); callers
    /// treat null as "value unavailable". SymbolCheck turns these into hard failures.
    /// </summary>
    internal static class Refs
    {
        public static AccessTools.FieldRef<T, F> Field<T, F>(string name)
        {
            try
            {
                return AccessTools.FieldRefAccess<T, F>(name);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError($"missing field {typeof(T).Name}.{name} ({typeof(F).Name}): {e.Message}");
                return null;
            }
        }
    }
}
