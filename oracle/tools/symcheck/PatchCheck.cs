using System.Reflection;

// Offline check that every Harmony prefix/postfix binds to its target: each ordinary parameter must exist on the
// target with the same name and type; __instance must accept the declaring type; __result must match the return type.
// Harmony binds prefix arguments by name, so a mismatch would only surface as a patch failure inside the game.
// Keep the list in sync with the Install methods in oracle/src/Guards (LethalBlock, AchievementGuard, SessionGate,
// SaveSuppression) and Events.HunterMeterTap.
static class PatchCheck
{
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

    static Type T(string name)
    {
        foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type t = null;
            try { t = a.GetType(name, false); } catch { }
            if (t != null) return t;
        }
        throw new Exception("type " + name);
    }

    static readonly (string type, string method, string[] ps, string owner, string patch)[] Patches =
    {
        ("PlayerData", "TakeHealth", new[] { "System.Int32", "System.Boolean", "System.Boolean" }, "SsOracle.Guards.LethalBlock", "TakeHealthPrefix"),
        ("PlayerData", "TakeHealth", new[] { "System.Int32", "System.Boolean", "System.Boolean" }, "SsOracle.Guards.LethalBlock", "TakeHealthPostfix"),
        ("HeroController", "Die", new[] { "System.Boolean", "System.Boolean" }, "SsOracle.Guards.LethalBlock", "DiePrefix"),
        ("GameManager", "PlayerDead", new[] { "System.Single" }, "SsOracle.Guards.LethalBlock", "PlayerDeadPrefix"),
        ("HeroController", "TakeDamage", new[] { "UnityEngine.GameObject", "GlobalEnums.CollisionSide", "System.Int32", "GlobalEnums.HazardType", "GlobalEnums.DamagePropertyFlags" }, "SsOracle.Guards.LethalBlock", "TakeDamagePrefix"),
        ("HeroController", "DoSpecialDamage", new[] { "System.Int32", "System.Boolean", "System.String", "System.Boolean", "System.Boolean", "System.Boolean", "System.Boolean" }, "SsOracle.Guards.LethalBlock", "SpecialPrefix"),
        ("HeroController", "TakeQuickDamage", new[] { "System.Int32", "System.Boolean", "System.Boolean" }, "SsOracle.Guards.LethalBlock", "QuickPrefix"),
        ("HeroController", "TakeFrostDamage", new[] { "System.Int32" }, "SsOracle.Guards.LethalBlock", "FrostPrefix"),
        ("HeroController", "TakeChompDamage", new string[0], "SsOracle.Guards.LethalBlock", "ChompPrefix"),
        ("HeroController", "ApplyTagDamage", new[] { "DamageTag+DamageTagInstance" }, "SsOracle.Guards.LethalBlock", "TagPrefix"),
        ("HeroController", "CriticalDamage", new string[0], "SsOracle.Guards.LethalBlock", "CriticalPrefix"),
        ("HeroController", "TakeHealth", new[] { "System.Int32" }, "SsOracle.Guards.LethalBlock", "HeroTakeHealthPrefix"),
        ("HeroController", "CheckDeathCatch", new string[0], "SsOracle.Guards.LethalBlock", "DeathCatchPrefix"),
        ("HeroController", "CheckDeathCatch", new string[0], "SsOracle.Guards.LethalBlock", "PopPostfix"),
        ("DesktopPlatform", "PushAchievementUnlock", new[] { "System.String" }, "SsOracle.Guards.AchievementGuard", "PushPrefix"),
        ("DesktopPlatform", "UpdateAchievementProgress", new[] { "System.String", "System.Int32", "System.Int32" }, "SsOracle.Guards.AchievementGuard", "PlatformProgressPrefix"),
        ("AchievementHandler", "AwardAchievementToPlayer", new[] { "System.String" }, "SsOracle.Guards.AchievementGuard", "AwardPrefix"),
        ("AchievementHandler", "UpdateAchievementProgress", new[] { "System.String", "System.Int32", "System.Int32" }, "SsOracle.Guards.AchievementGuard", "HandlerProgressPrefix"),
        ("MenuStyleUnlock", "Unlock", new[] { "System.String", "System.Boolean" }, "SsOracle.Guards.AchievementGuard", "MenuStylePrefix"),
        ("CustomSharedData", "SetBool", new[] { "System.String", "System.Boolean" }, "SsOracle.Guards.AchievementGuard", "SharedSetBoolPrefix"),
        ("GameManager", "StartNewGame", new[] { "System.Boolean", "System.Boolean" }, "SsOracle.Guards.SessionGate", "StartNewGamePrefix"),
        ("GameManager", "ContinueGame", new string[0], "SsOracle.Guards.SessionGate", "ContinueGamePrefix"),
        ("GameManager", "SaveGame", new[] { "System.Int32", "System.Action`1[System.Boolean]", "System.Boolean", "AutoSaveName" }, "SsOracle.Guards.SaveSuppression", "SaveGamePrefix"),
        ("GameManager", "CreateRestorePoint", new[] { "System.Int32", "AutoSaveName", "System.Action`1[System.Boolean]" }, "SsOracle.Guards.SaveSuppression", "RestorePointPrefix"),
        ("GameManager", "SaveGameData", new[] { "System.Int32", "SaveGameData", "System.Boolean", "System.Action`1[System.Boolean]" }, "SsOracle.Guards.SaveSuppression", "SaveGameDataPrefix"),
        ("GameManager", "PreparePlayerDataForSave", new[] { "System.Int32" }, "SsOracle.Guards.SaveSuppression", null),
        // Events.HunterMeterTap (P17): reset sites of the Hunter combo meter.
        ("HeroController", "TakeDamage", new[] { "UnityEngine.GameObject", "GlobalEnums.CollisionSide", "System.Int32", "GlobalEnums.HazardType", "GlobalEnums.DamagePropertyFlags" }, "SsOracle.Events.HunterMeterTap", "DamagePrefix"),
        ("HeroController", "DoSpecialDamage", new[] { "System.Int32", "System.Boolean", "System.String", "System.Boolean", "System.Boolean", "System.Boolean", "System.Boolean" }, "SsOracle.Events.HunterMeterTap", "SpecialPrefix"),
        ("HeroController", "MaxHealth", new string[0], "SsOracle.Events.HunterMeterTap", "MaxHealthPrefix"),
        ("HeroController", "SetIsMaggoted", new[] { "System.Boolean" }, "SsOracle.Events.HunterMeterTap", "MaggotedPrefix"),
        ("HeroController", "ResetAllCrestState", new[] { "System.Boolean" }, "SsOracle.Events.HunterMeterTap", "CrestResetPrefix"),
        ("ToolItemManager", "SendEquippedChangedEvent", new[] { "System.Boolean" }, "SsOracle.Events.HunterMeterTap", "EquipsPrefix"),
        ("ToolItemManager", "SendEquippedChangedEvent", new[] { "System.Boolean" }, "SsOracle.Events.HunterMeterTap", "ExitPostfix"),
        // M2: Events.HitTap ("hit" events) and Export.MenuExporter (STATE "menu").
        ("HealthManager", "TakeDamage", new[] { "HitInstance" }, "SsOracle.Events.HitTap", "HitPrefix"),
        ("HealthManager", "TakeDamage", new[] { "HitInstance" }, "SsOracle.Events.HitTap", "TakeDamagePostfix"),
        ("HealthManager", "ApplyExtraDamage", new[] { "HitInstance" }, "SsOracle.Events.HitTap", "HitPrefix"),
        ("HealthManager", "ApplyExtraDamage", new[] { "HitInstance" }, "SsOracle.Events.HitTap", "ExtraHitPostfix"),
        ("HealthManager", "ApplyExtraDamage", new[] { "System.Int32" }, "SsOracle.Events.HitTap", "ExtraIntPrefix"),
        ("HealthManager", "ApplyExtraDamage", new[] { "System.Int32" }, "SsOracle.Events.HitTap", "ExtraIntPostfix"),
        ("CameraController", "FadeOut", new[] { "GlobalEnums.CameraFadeType" }, "SsOracle.Export.MenuExporter", "FadeOutPostfix"),
        ("MenuButtonList", "SetupActive", new string[0], "SsOracle.Export.MenuExporter", "SetupActivePostfix"),
    };

    public static int Run()
    {
        var bad = 0;
        foreach (var (type, method, ps, owner, patch) in Patches)
        {
            var tt = T(type);
            var pts = ps.Select(T).ToArray();
            var target = tt.GetMethod(method, All, null, pts, null);
            if (target == null) { Console.WriteLine($"  PATCH TARGET MISSING {type}.{method}"); bad++; continue; }
            if (patch == null) continue;
            var pm = T(owner).GetMethod(patch, All);
            if (pm == null) { Console.WriteLine($"  PATCH METHOD MISSING {owner}.{patch}"); bad++; continue; }
            if (!pm.IsStatic) { Console.WriteLine($"  NOT STATIC {owner}.{patch}"); bad++; }
            var tps = target.GetParameters();
            foreach (var p in pm.GetParameters())
            {
                var pt = p.ParameterType.IsByRef ? p.ParameterType.GetElementType() : p.ParameterType;
                if (p.Name == "__instance")
                {
                    if (!pt.IsAssignableFrom(tt)) { Console.WriteLine($"  {patch}: __instance {pt} vs {tt}"); bad++; }
                    continue;
                }
                if (p.Name == "__state") continue;   // prefix -> postfix scratch, any type
                if (p.Name == "__result")
                {
                    if (pt != target.ReturnType || !p.ParameterType.IsByRef) { Console.WriteLine($"  {patch}: __result {p.ParameterType} vs {target.ReturnType}"); bad++; }
                    continue;
                }
                var tp = tps.FirstOrDefault(x => x.Name == p.Name);
                if (tp == null) { Console.WriteLine($"  {patch}: parameter '{p.Name}' not on {type}.{method}({string.Join(", ", tps.Select(x => x.ParameterType.Name + " " + x.Name))})"); bad++; continue; }
                if (tp.ParameterType != pt) { Console.WriteLine($"  {patch}: '{p.Name}' is {tp.ParameterType}, patch takes {pt}"); bad++; }
            }
            if (pm.ReturnType == typeof(bool) && !patch.EndsWith("Prefix")) { Console.WriteLine($"  {patch}: bool return on non-prefix"); bad++; }
        }
        Console.WriteLine($"patch signatures: {Patches.Length} checked, {bad} problems");
        return bad;
    }
}
