using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;

namespace SsOracle.Core
{
    /// <summary>
    /// SymbolCheck (DESIGN §3.1.1 Core, §3.10 compat item 3): resolves by name every type, field, property, method
    /// and event the oracle reads, patches or will patch (m0 §3.1 MVP fields and hook table, the guards, and the
    /// planned M1-M5 exporters), against the assemblies actually loaded. Names are strings on purpose: a typeof()
    /// against a changed game would throw at JIT time instead of producing a list of what is missing.
    ///
    /// A missing hard symbol is a hard failure: <see cref="Ok"/> is false (other modules and non-TRAIN profiles check
    /// it), a loud error lists every miss, and symbols.check returns the list. Soft symbols (DebugMod's savestate and
    /// cheat members, which only TRAIN loads) are reported but never fail the check. Runs once from Install
    /// (Plugin.Awake) and again on the first frame, when every other plugin has loaded; symbols.check returns the last
    /// report and re-runs the pass only on request ({refresh: true}).
    /// </summary>
    internal static class SymbolCheck
    {
        private enum Kind { Type, Field, Property, Member, Method, Event }

        private sealed class Sym
        {
            public Kind Kind;
            public string Type;
            public string Name;
            public string[] Params;   // null = any overload
            public bool Soft;

            public string Key => Kind == Kind.Type ? Type
                : Params == null ? $"{Type}.{Name}" : $"{Type}.{Name}({string.Join(",", Params)})";
        }

        private static Sym T(string type, bool soft = false) => new Sym { Kind = Kind.Type, Type = type, Soft = soft };
        private static Sym F(string type, string name, bool soft = false) => new Sym { Kind = Kind.Field, Type = type, Name = name, Soft = soft };
        private static Sym P(string type, string name, bool soft = false) => new Sym { Kind = Kind.Property, Type = type, Name = name, Soft = soft };
        private static Sym Mb(string type, string name) => new Sym { Kind = Kind.Member, Type = type, Name = name };
        private static Sym E(string type, string name) => new Sym { Kind = Kind.Event, Type = type, Name = name };
        private static Sym M(string type, string name, params string[] ps) => new Sym { Kind = Kind.Method, Type = type, Name = name, Params = ps };
        private static Sym MAny(string type, string name, bool soft = false) => new Sym { Kind = Kind.Method, Type = type, Name = name, Soft = soft };
        private static Sym MSoft(string type, string name, params string[] ps) => new Sym { Kind = Kind.Method, Type = type, Name = name, Params = ps, Soft = true };

        private const string GM = "GameManager", PD = "PlayerData", HC = "HeroController", HCS = "HeroControllerStates";
        private const string ActB = "Action<bool>";

        /// <summary>Everything the oracle uses or will use, grouped by owner (m0 §2.7, §3.1, §3.2 and the hook table).</summary>
        private static readonly Sym[] Table =
        {
            // --- GameManager: singleton, state, scenes, timers, saves, death, freezes (m0 §3.1) ---
            T(GM), F(GM, "_instance"), P(GM, "UnsafeInstance"), P(GM, "GameState"), F(GM, "isPaused"), P(GM, "TimeSlowed"),
            F(GM, "timeSlowedCount"), P(GM, "IsInSceneTransition"), P(GM, "HasFinishedEnteringScene"), F(GM, "sceneName"),
            F(GM, "nextSceneName"), F(GM, "entryGateName"), P(GM, "PlayTime"), F(GM, "sessionPlayTimer"), F(GM, "sessionStartTime"),
            F(GM, "playerData"), F(GM, "sceneData"), F(GM, "profileID"), F(GM, "gameConfig"), F(GM, "gameCams"), F(GM, "gameSettings"),
            P(GM, "inputHandler"), P(GM, "ui"), P(GM, "sm"), P(GM, "cameraCtrl"), P(GM, "hero_ctrl"), P(GM, "achievementHandler"),
            F(GM, "isSaveGameQueued"), F(GM, "isAutoSaveQueued"), F(GM, "queuedSaveFrameDelay"),
            M(GM, "IsMemoryScene"), M(GM, "SetState", "GlobalEnums.GameState"), M(GM, "FinishedEnteringScene"),
            M(GM, "FreezeMoment", "GlobalEnums.FreezeMomentTypes", "Action"), M(GM, "FreezeMoment", "float", "float", "float", "float", "Action"),
            M(GM, "SetIsInventoryOpen", "bool"), M(GM, "SaveGame", ActB), M(GM, "SaveGame", "int", ActB, "bool", "AutoSaveName"),
            M(GM, "SaveGameWithAutoSave", "AutoSaveName", ActB), M(GM, "CreateRestorePoint", "AutoSaveName", ActB),
            M(GM, "CreateRestorePoint", "int", "AutoSaveName", ActB), M(GM, "SaveGameData", "int", "SaveGameData", "bool", ActB),
            M(GM, "PreparePlayerDataForSave", "int"), M(GM, "SaveLevelState"), M(GM, "QueueSaveGame"), M(GM, "DoQueuedSaveGame"),
            M(GM, "PlayerDead", "float"), M(GM, "PlayerDeadFromHazard", "float"), M(GM, "HazardRespawn"),
            M(GM, "CheckCompletionAchievements"), M(GM, "AwardQueuedAchievements"), M(GM, "ReturnToMainMenu", "bool", ActB, "bool", "bool"),
            M(GM, "StartNewGame", "bool", "bool"), M(GM, "ContinueGame"), MAny(GM, "SetPlayerDataBool"), E(GM, "SceneTransitionBegan"),
            // FSM writers of health and freezes (EventTap health_changes / TimeSlowed, DESIGN §3.1.1).
            M(GM, "SetPlayerDataInt", "string", "int"), M(GM, "FreezeMoment", "int"),
            T("GlobalEnums.GameState"), T("GlobalEnums.FreezeMomentTypes"), T("AutoSaveName"), T("SaveGameData"), F("SaveGameData", "playerData"),
            T("GameConfig"), F("GameConfig", "disableSaveGame"), T("DemoHelper"), P("DemoHelper", "IsDemoMode"),
            T("Constants"), F("Constants", "GAME_VERSION"), T("CustomPlayerLoop"), P("CustomPlayerLoop", "FixedUpdateCycle"),
            T("CoreLoop"), M("CoreLoop", "InvokeNext", "Action"),

            // --- PlayerData: health, silk, currencies, run flags, pause blockers, respawn (m0 §2.7) ---
            T(PD), F(PD, "health"), F(PD, "maxHealth"), F(PD, "healthBlue"), F(PD, "damagedBlue"), F(PD, "damagedPurple"),
            F(PD, "silk"), F(PD, "silkMax"), F(PD, "silkParts"), F(PD, "geo"), F(PD, "ShellShards"), F(PD, "permadeathMode"),
            F(PD, "playTime"), F(PD, "disablePause"), F(PD, "disableSaveQuit"), F(PD, "disableInventory"), F(PD, "isInventoryOpen"),
            F(PD, "atBench"), F(PD, "isInvincible"), F(PD, "respawnScene"), F(PD, "respawnMarkerName"), F(PD, "respawnType"),
            F(PD, "tempRespawnScene"), F(PD, "tempRespawnMarker"), F(PD, "tempRespawnType"), F(PD, "CurrentCrestID"),
            F(PD, "hasDash"), F(PD, "hasDoubleJump"), F(PD, "completionPercentage"), F(PD, "CompletedEndings"), F(PD, "LastCompletedEnding"),
            F(PD, "Tools"), F(PD, "ToolEquips"), F(PD, "ExtraToolEquips"),
            P(PD, "CurrentMaxHealth"), P(PD, "CurrentSilkMax"), P(PD, "IsAnyCursed"), P(PD, "HasInstance"),
            M(PD, "TakeHealth", "int", "bool", "bool"), M(PD, "SetBool", "string", "bool"), M(PD, "SetInt", "string", "int"),
            M(PD, "GetToolData", "string"), M(PD, "CountGameCompletion"),
            T("GlobalEnums.PermadeathModes"),
            T("TeamCherry.SharedUtils.VariableExtensions"),
            M("TeamCherry.SharedUtils.VariableExtensions", "SetVariable", "TeamCherry.SharedUtils.IIncludeVariableExtensions", "string", "object", "Type"),

            // --- HeroController: damage entry points (LethalBlock), state, tuning constants (m0 §2.5, §3.1) ---
            T(HC), P(HC, "UnsafeInstance"), P(HC, "Body"), P(HC, "AnimCtrl"), P(HC, "IsInLifebloodState"), P(HC, "IsStunned"),
            P(HC, "HeroLockState"), F(HC, "cState"), F(HC, "playerData"), F(HC, "hero_state"), F(HC, "transitionState"), F(HC, "damageMode"),
            F(HC, "acceptingInput"), F(HC, "controlReqlinquished"), F(HC, "parryInvulnTimer"), F(HC, "takeNoDamage"),
            F(HC, "lastHazardRespawnTime"), F(HC, "frostAmount"), F(HC, "isHeroInPosition"), F(HC, "INVUL_TIME"), F(HC, "INVUL_TIME_PARRY"),
            F(HC, "DAMAGE_FREEZE_DOWN"), F(HC, "DAMAGE_FREEZE_WAIT"), F(HC, "DAMAGE_FREEZE_UP"), F(HC, "DAMAGE_FREEZE_SPEED"),
            F(HC, "RECOIL_DURATION"), F(HC, "DOWNSPIKE_INVULNERABILITY_STEPS"),
            M(HC, "CanTakeDamage"), M(HC, "TakeDamage", "UnityEngine.GameObject", "GlobalEnums.CollisionSide", "int", "GlobalEnums.HazardType", "GlobalEnums.DamagePropertyFlags"),
            M(HC, "DoSpecialDamage", "int", "bool", "string", "bool", "bool", "bool", "bool"), M(HC, "CriticalDamage"),
            M(HC, "TakeQuickDamage", "int", "bool"), M(HC, "TakeQuickDamage", "int", "bool", "bool"), M(HC, "TakeChompDamage"),
            M(HC, "TakeFrostDamage", "int"), M(HC, "ApplyTagDamage", "DamageTag+DamageTagInstance"), M(HC, "TakeHealth", "int"),
            M(HC, "Die", "bool", "bool"), M(HC, "DieFromHazard", "GlobalEnums.HazardType", "float"), M(HC, "CheckDeathCatch"),
            M(HC, "HazardRespawn"), M(HC, "FinishedEnteringScene", "bool", "bool"), M(HC, "StartRecoil", "GlobalEnums.CollisionSide", "int"),
            M(HC, "Invulnerable"), M(HC, "Awake"), M(HC, "CanBeBarnacleGrabbed"), E(HC, "OnDeath"),
            T("GlobalEnums.HazardType"), T("GlobalEnums.CollisionSide"), T("GlobalEnums.DamagePropertyFlags"), T("DamageTag+DamageTagInstance"),
            F("DamageTag+DamageTagInstance", "amount"), F("DamageTag+DamageTagInstance", "specialDamageType"),
            T(HCS), P(HCS, "Invulnerable"), F(HCS, "invulnerable"), F(HCS, "dead"), F(HCS, "onGround"), F(HCS, "facingRight"),
            F(HCS, "transitioning"), F(HCS, "isBinding"), F(HCS, "recoiling"), F(HCS, "parrying"), F(HCS, "parryAttack"), F(HCS, "hazardDeath"),
            F(HCS, "downTravelling"), F(HCS, "isFrostDeath"), F(HCS, "downspikeInvulnerabilitySteps"), F(HCS, "attackCount"),
            F(HCS, "toolThrowCount"), F(HCS, "throwingToolVertical"),
            T("HeroInvincibilitySource"), P("HeroInvincibilitySource", "IsActive"), T("HeroAnimationController"), Mb("HeroAnimationController", "animator"),

            // --- Cheats / damage gates exported as cheat_flags (m0:N11, N43) ---
            T("CheatManager"), P("CheatManager", "Invincibility"), P("CheatManager", "AllowSaving"), T("CheatManager+InvincibilityStates"),
            T("ToolItemManager"), P("ToolItemManager", "ActiveState"), M("ToolItemManager", "IsToolEquipped", "ToolItem", "ToolEquippedReadSource"),
            T("ManagerSingleton`1"), P("ManagerSingleton`1", "UnsafeInstance"),
            T("BossSceneController"), F("BossSceneController", "Instance"), P("BossSceneController", "IsBossScene"),
            T("CustomSceneManager"), P("CustomSceneManager", "HeroKeepHealth"),
            T("GlobalSettings.Gameplay"), P("GlobalSettings.Gameplay", "FracturedMaskTool"), P("GlobalSettings.Gameplay", "BarbedWireTool"),
            P("GlobalSettings.Gameplay", "BarbedWireDamageTakenMultiplier"),
            // HUD refresh after LethalBlock restores health.
            T("EventRegister"), M("EventRegister", "SendEvent", "int", "UnityEngine.GameObject"), T("EventRegisterEvents"),
            F("EventRegisterEvents", "HealthUpdate"),
            T("ToolItem"), P("ToolItem", "IsEquipped"), P("ToolItem", "SavedData"), T("ToolItemsData+Data"), F("ToolItemsData+Data", "AmountLeft"),

            // --- Pause and quit blockers (m0 §2.4, hook table) ---
            T("InputHandler"), F("InputHandler", "acceptingInput"), F("InputHandler", "inputActions"), P("InputHandler", "PauseAllowed"),
            M("InputHandler", "PreventPause"), M("InputHandler", "AllowPause"), M("InputHandler", "SetCursorEnabled", "bool"),
            T("UIManager"), F("UIManager", "uiState"), F("UIManager", "menuState"), P("UIManager", "IsFadingMenu"), MAny("UIManager", "ReturnToMainMenu"),
            M("UIManager", "UIGoToMainMenu"),
            T("ScenePreloader"), P("ScenePreloader", "HasPendingOperations"),
            T("GenericMessageCanvas"), P("GenericMessageCanvas", "IsActive"), MAny("GenericMessageCanvas", "Show"),
            T("InteractManager"), P("InteractManager", "BlockingInteractable"),
            T("UIMsgProxy"), M("UIMsgProxy", "SetIsInMsg", "bool"),
            T("InControl.InputManager"), P("InControl.InputManager", "SuspendInBackground"), P("InControl.InputManager", "IsSetup"),

            // --- Entities, FSMs, animation (m0 §2.7; EntityRegistry / FsmTap) ---
            T("HealthManager"), F("HealthManager", "hp"), F("HealthManager", "isDead"), P("HealthManager", "IsInvincible"),
            M("HealthManager", "EnumerateActiveEnemies"), M("HealthManager", "TakeDamage", "HitInstance"), M("HealthManager", "Hit", "HitInstance"),
            T("DamageHero"), F("DamageHero", "damageDealt"), F("DamageHero", "hazardType"), F("DamageHero", "damagePropertyFlags"),
            F("DamageHero", "noBounceCooldown"), F("DamageHero", "_damageHeroes"), P("DamageHero", "CanCauseDamage"),
            T("PlayMakerFSM"), P("PlayMakerFSM", "FsmList"), P("PlayMakerFSM", "Fsm"), P("PlayMakerFSM", "FsmName"), P("PlayMakerFSM", "ActiveStateName"),
            T("HutongGames.PlayMaker.Fsm"), M("HutongGames.PlayMaker.Fsm", "EnterState", "HutongGames.PlayMaker.FsmState"),
            T("HutongGames.PlayMaker.FsmState"), P("HutongGames.PlayMaker.FsmState", "StateTime"), P("HutongGames.PlayMaker.FsmState", "Name"),
            T("tk2dSpriteAnimator"), P("tk2dSpriteAnimator", "CurrentClip"), P("tk2dSpriteAnimator", "CurrentFrame"), P("tk2dSpriteAnimator", "ClipFps"),
            P("tk2dSpriteAnimator", "Playing"), P("tk2dSpriteAnimator", "ClipTimeSeconds"),
            T("tk2dSpriteAnimationClip"), F("tk2dSpriteAnimationClip", "name"), F("tk2dSpriteAnimationClip", "fps"), F("tk2dSpriteAnimationClip", "frames"),

            // --- Scenes, gates, camera (SceneDumper, CameraExporter) ---
            T("TransitionPoint"), P("TransitionPoint", "TransitionPoints"), F("TransitionPoint", "targetScene"), F("TransitionPoint", "entryPoint"),
            F("TransitionPoint", "isInactive"), F("TransitionPoint", "isADoor"), F("TransitionPoint", "nonHazardGate"), F("TransitionPoint", "respawnMarker"),
            P("TransitionPoint", "IsTransitionBlocked"), M("TransitionPoint", "GetGatePosition"),
            T("GameCameras"), F("GameCameras", "mainCamera"), F("GameCameras", "hudCamera"), F("GameCameras", "cameraController"),
            F("GameCameras", "forceCameraAspect"), F("GameCameras", "tk2dCam"), Mb("GameCameras", "silkSpool"),
            T("CameraController"), F("CameraController", "mode"), F("CameraController", "lookOffset"),
            T("ForceCameraAspect"), P("ForceCameraAspect", "CurrentViewportAspect"), P("ForceCameraAspect", "CurrentMainCamFov"),
            P("ForceCameraAspect", "CurrentMainCamHeightMult"),
            T("SilkSpool"), P("SilkSpool", "Instance"),
            F("CameraController", "xLimit"), F("CameraController", "yLimit"), F("CameraController", "atSceneBounds"),
            F("ForceCameraAspect", "fovOffset"), F(HC, "current_velocity"), E(HC, "OnHeroInstanceSet"),

            // --- SceneDumper, HudProbe, pause-menu Quit state (m0 §3.1-3.2, planned M1-M5) ---
            T("WorldInfo"), F("WorldInfo", "SubSceneNameSuffixes"), T("RespawnMarker"), P("RespawnMarker", "Markers"), T("TinkEffect"),
            F("CustomSceneManager", "mapZone"), P("CustomSceneManager", "ForceNotMemory"), P("CustomSceneManager", "FrostSpeed"),
            T("InGameCutsceneInfo"), P("InGameCutsceneInfo", "IsInCutscene"), T("BattleScene"), F("BattleScene", "noEndSlomo"),
            T("SceneData"), F("SceneData", "persistentBools"), F("SceneData", "persistentInts"), P("SceneData", "PersistentBools"),
            T("HudCanvas"), P("HudCanvas", "IsVisible"), P("GameCameras", "IsHudVisible"),
            T("HudGlobalHide"), P("HudGlobalHide", "IsHidden"), P("HudGlobalHide", "IsReduced"),
            T("MenuButtonSaveQuitListCondition"), M("MenuButtonSaveQuitListCondition", "IsFulfilled"),

            // --- Achievements, shared data, save files (AchievementGuard m0:C1/N26; SaveRedirect; snapshots m0:C13) ---
            T("Platform"), P("Platform", "Current"), P("Platform", "RoamingSharedData"),
            T("DesktopPlatform"), M("DesktopPlatform", "Awake"), M("DesktopPlatform", "PushAchievementUnlock", "string"),
            M("DesktopPlatform", "UpdateAchievementProgress", "string", "int", "int"), M("DesktopPlatform", "IsAchievementUnlocked", "string"),
            T("AchievementHandler"), M("AchievementHandler", "AwardAchievementToPlayer", "string"),
            M("AchievementHandler", "UpdateAchievementProgress", "string", "int", "int"), M("AchievementHandler", "AwardQueuedAchievements"),
            P("AchievementHandler", "AchievementsList"), T("AchievementsList"), M("AchievementsList", "FindAchievement", "string"),
            T("MenuStyleUnlock"), M("MenuStyleUnlock", "Unlock", "string", "bool"),
            T("CustomSharedData"), M("CustomSharedData", "SetBool", "string", "bool"), M("CustomSharedData", "SetInt", "string", "int"),
            T("SaveRestoreHandler"), M("SaveRestoreHandler", "GetDirectoryName", "int"),

            // --- abilities.grant / abilities.list (TRAIN): ability flags, silk skills, tools, crest slots (m0 §2.9) ---
            F(PD, "hasWalljump"), F(PD, "hasBrolly"), F(PD, "hasHarpoonDash"), F(PD, "hasSuperJump"), F(PD, "hasChargeSlash"),
            F(PD, "hasNeedolin"), F(PD, "hasNeedleThrow"), F(PD, "hasThreadSphere"), F(PD, "hasParry"), F(PD, "hasSilkCharge"),
            F(PD, "hasSilkBomb"), F(PD, "hasSilkBossNeedle"), P(PD, "SilkSkillCost"), M(PD, "SetToolData", "string", "ToolItemsData+Data"),
            M("ToolItemManager", "GetToolByName", "string"), M("ToolItemManager", "GetCrestByName", "string"), M("ToolItemManager", "GetAllTools"),
            MAny("ToolItemManager", "SetEquippedTools"), M("ToolItemManager", "SendEquippedChangedEvent", "bool"),
            M("ToolItemManager", "ReportAllBoundAttackToolsUpdated"), M("ToolItemManager", "GetToolStorageAmount", "ToolItem"),
            M("ToolItemManager", "GetBoundAttackTool", "AttackToolBinding", "ToolEquippedReadSource"), M("ToolItemManager", "IsToolEquipped", "string"),
            P("ToolItem", "Type"), P("ToolItem", "IsUnlockedNotHidden"), F("ToolItemsData+Data", "IsUnlocked"), F("ToolItemsData+Data", "IsHidden"),
            T("ToolItemType"), T("AttackToolBinding"), T("ToolEquippedReadSource"), T("ToolItemTypeExtensions"),
            T("ToolCrest"), P("ToolCrest", "Slots"), T("ToolCrest+SlotInfo"), F("ToolCrest+SlotInfo", "Type"),
            F("ToolCrest+SlotInfo", "AttackBinding"), F("ToolCrest+SlotInfo", "IsLocked"),
            T("ToolCrestsData+SlotData"), F("ToolCrestsData+SlotData", "EquippedTool"), F("ToolCrestsData+SlotData", "IsUnlocked"),
            P(HC, "Config"), T("HeroControllerConfig"), P("HeroControllerConfig", "CanHarpoonDash"), P("HeroControllerConfig", "CanDoubleJump"),
            P("HeroControllerConfig", "CanBrolly"), P("HeroControllerConfig", "CanNailCharge"), P("HeroControllerConfig", "CanPlayNeedolin"),

            // --- Crests, hero configs, attack objects, Hunter meter (P17: Crest.*, Events.HunterMeterTap) ---
            T("ToolCrest"), P("ToolCrest", "Slots"), P("ToolCrest", "HeroConfig"), P("ToolCrest", "IsHidden"), P("ToolCrest", "HasCustomAction"),
            F("ToolCrest", "previousVersion"), F("ToolCrest", "upgradedVersion"), M("ToolCrest", "Unlock"),
            T("ToolCrest+SlotInfo"), F("ToolCrest+SlotInfo", "Type"), F("ToolCrest+SlotInfo", "AttackBinding"), F("ToolCrest+SlotInfo", "IsLocked"),
            F("ToolCrest+SlotInfo", "Position"), T("ToolCrestsData"), F("ToolCrestsData", "RuntimeData"), T("ToolCrestsData+Data"),
            F("ToolCrestsData+Data", "IsUnlocked"), F("ToolCrestsData+Data", "Slots"), F("ToolCrestsData+Data", "DisplayNewIndicator"),
            T("ToolCrestsData+SlotData"), F("ToolCrestsData+SlotData", "EquippedTool"), F("ToolCrestsData+SlotData", "IsUnlocked"),
            M("ToolItemManager", "GetAllCrests"), M("ToolItemManager", "GetCrestByName", "string"), M("ToolItemManager", "SetEquippedCrest", "string"),
            M("ToolItemManager", "SendEquippedChangedEvent", "bool"), P("ToolItemManager", "IsCursed"), M("ToolItemManager", "GetAllTools"),
            M(PD, "SetToolData", "string", "ToolItemsData+Data"), M(PD, "AddSilk", "int"),
            M("SilkSpool", "RefreshSilk", "SilkSpool+SilkAddSource", "SilkSpool+SilkTakeSource"),
            F(PD, "PreviousCrestID"), F(PD, "IsCurrentCrestTemp"), F(PD, "nailUpgrades"), P(PD, "nailDamage"),
            T("HeroControllerConfig"), T("HeroControllerConfig+DownSlashTypes"), F("HeroControllerConfig", "attackDuration"),
            F("HeroControllerConfig", "attackCooldownTime"), F("HeroControllerConfig", "attackRecoveryTime"), F("HeroControllerConfig", "quickAttackSpeedMult"),
            F("HeroControllerConfig", "quickAttackCooldownTime"), F("HeroControllerConfig", "downSlashType"), F("HeroControllerConfig", "downspikeAnticTime"),
            F("HeroControllerConfig", "downspikeTime"), F("HeroControllerConfig", "downspikeRecoveryTime"), P("HeroControllerConfig", "AttackDuration"),
            P("HeroControllerConfig", "DownSlashType"), T("HeroControllerConfigWarrior"), F("HeroControllerConfigWarrior", "rageAttackDuration"),
            T("HeroController+ConfigGroup"), F("HeroController+ConfigGroup", "Config"), F("HeroController+ConfigGroup", "DashStab"),
            F("HeroController+ConfigGroup", "ChargeSlash"), F("HeroController+ConfigGroup", "DownSlashObject"),
            F("HeroController+ConfigGroup", "AltDownSlashObject"), P("HeroControllerConfig", "DownSlashEvent"), F(HC, "configs"), F(HC, "specialConfigs"), F(HC, "crestConfig"),
            P(HC, "CurrentConfigGroup"), P(HC, "Config"), P(HC, "WarriorState"), P(HC, "ReaperState"), P(HC, "WandererState"),
            P(HC, "IsWandererLucky"), M(HC, "GetLuckModifier"), F(HC, "DASHCOMBO_WINDOW_TIME"), P(HC, "Bounds"),
            F(HC, "normalSlash"), F(HC, "normalSlashDamager"), F(HC, "alternateSlash"), F(HC, "alternateSlashDamager"), F(HC, "upSlash"),
            F(HC, "upSlashDamager"), F(HC, "altUpSlash"), F(HC, "altUpSlashDamager"), F(HC, "downSlash"), F(HC, "downSpike"),
            F(HC, "downSlashDamager"), F(HC, "altDownSlash"), F(HC, "altDownSpike"), F(HC, "altDownSlashDamager"), F(HC, "wallSlash"),
            F(HC, "wallSlashDamager"),
            P(HC, "HunterUpgState"), F(HC, "hunterUpgState"), T("HeroController+HunterUpgCrestStateInfo"),
            F("HeroController+HunterUpgCrestStateInfo", "CurrentMeterHits"), M(HC, "ResetHunterUpgCrestState"), M(HC, "ResetAllCrestState", "bool"),
            M(HC, "MaxHealth"), M(HC, "SetIsMaggoted", "bool"), M(HC, "NailHitEnemy", "HealthManager", "HitInstance"),
            T("DamageEnemies"), F("DamageEnemies", "attackType"), F("DamageEnemies", "useNailDamage"), F("DamageEnemies", "nailDamageMultiplier"),
            F("DamageEnemies", "damageDealt"), F("DamageEnemies", "damageMultPerHit"), F("DamageEnemies", "multiHitter"), F("DamageEnemies", "stepsPerHit"),
            F("DamageEnemies", "hitsUntilDeath"), F("DamageEnemies", "magnitudeMult"), F("DamageEnemies", "silkGeneration"), F("DamageEnemies", "doesNotParry"),
            F("DamageEnemies", "doesNotCriticalHit"), F("DamageEnemies", "doesNotTink"), F("DamageEnemies", "direction"), P("DamageEnemies", "DamageMultiplier"),
            T("NailAttackBase"), P("NailAttackBase", "CanHitSpikes"), F("NailAttackBase", "scale"), T("NailSlash"), F("NailSlash", "animName"),
            T("Downspike"), F("Downspike", "animName"), F("Downspike", "horizontalKnockbackDamager"), F("Downspike", "verticalKnockbackDamager"),
            T("HeroDownAttack"), M("tk2dSpriteAnimator", "GetClipByName", "string"), T("tk2dSpriteAnimationFrame"),
            F("tk2dSpriteAnimationFrame", "triggerEvent"), F("tk2dSpriteAnimationFrame", "eventInfo"),
            M("GlobalSettings.Gameplay", "Get"), P("GlobalSettings.Gameplay", "HunterComboHits"), P("GlobalSettings.Gameplay", "HunterCombo2Hits"),
            P("GlobalSettings.Gameplay", "WandererCritChance"), P("GlobalSettings.Gameplay", "WeightedAnkletDmgInvulnMult"),
            P("GlobalSettings.Gameplay", "MossCreep1Tool"), P("GlobalSettings.Gameplay", "LongNeedleMultiplier"), P("GlobalSettings.Gameplay", "WarriorCrest"),

            // --- M2 exports (docs/facts/1.0.30000/state_fields_m2.md): hero.tm / alpha / wall / tags / tool_max ---
            F(HC, "invulnerableDuration"), F(HC, "invulnerableFreezeDuration"), F(HC, "recoilTimer"), F(HC, "recoilStepsLeft"),
            F(HC, "dashCooldownTimer"), F(HC, "attack_cooldown"), F(HC, "attack_time"), F(HC, "throwToolCooldown"),
            F(HC, "jump_steps"), F(HC, "jumped_steps"), F(HC, "downSpikeTimer"), F(HC, "downSpikeRecoveryTimer"),
            F(HC, "jumpQueueSteps"), F(HC, "attackQueueSteps"), F(HC, "toolThrowQueueSteps"), F(HC, "touchingWallL"),
            F(HC, "touchingWallR"), F(HC, "tagDamageTaker"), F(HCS, "recoilFrozen"),
            T("TagDamageTaker"), P("TagDamageTaker", "TaggedDamage"), T("DamageTag"), F("DamageTag", "damageAmount"),
            P("DamageTag", "TotalHitLimit"), T("DamageTagInfo"), F("DamageTagInfo", "HitsLeft"), F("DamageTagInfo", "NextHitTime"),
            F("DamageTagInfo", "RemoveAfterNextHit"), F("DamageTag", "isToolDamage"), P("DamageTag", "SpecialDamageType"),
            T("DamageTag+SpecialDamageTypes"), P("GlobalSettings.Gameplay", "ToolKitDamageIncrease"), F(PD, "ToolKitUpgrades"),
            T("UnityEngine.Time"), P("UnityEngine.Time", "timeAsDouble"), P("UnityEngine.Time", "fixedTimeAsDouble"),
            // ents[].hidden, colliders[].name, tk2d's lazily added sprite colliders (EntityRegistry.SpritesChanged)
            T("tk2dBaseSprite"), F("tk2dBaseSprite", "boxCollider2D"), F("tk2dBaseSprite", "polygonCollider2D"),
            F("tk2dBaseSprite", "edgeCollider2D"), MAny("tk2dBaseSprite", "UpdateCollider"),
            // "hit" events (Events.HitTap)
            P("HealthManager", "SendDamageTo"), M("HealthManager", "ApplyExtraDamage", "HitInstance"),
            M("HealthManager", "ApplyExtraDamage", "int"), T("HitInstance"), F("HitInstance", "DamageDealt"), F("HitInstance", "AttackType"),
            F("HitInstance", "Source"), F("HitInstance", "CriticalHit"), T("AttackTypes"),
            // STATE "menu" (Export.MenuExporter)
            T("UnityEngine.UI.PauseMenuButton"), F("UnityEngine.UI.PauseMenuButton", "pauseButtonType"),
            T("UnityEngine.UI.PauseMenuButton+PauseButtonType"), T("UnityEngine.UI.MenuButton"), F("UnityEngine.UI.MenuButton", "OnSubmitPressed"),
            T("MenuScreen"), F("MenuScreen", "backButton"), F("UIManager", "modalDimmer"), F("UIManager", "ignoreUnpause"),
            F("UIManager", "fadingMenuScreen"), F("UIManager", "pauseMenuScreen"), F("UIManager", "returnMainMenuPrompt"),
            T("MenuButtonList"), M("MenuButtonList", "SetupActive"), M("CameraController", "FadeOut", "GlobalEnums.CameraFadeType"),
            T("GlobalEnums.CameraFadeType"), T("GlobalEnums.UIState"),
            T("UnityEngine.EventSystems.EventSystem"), P("UnityEngine.EventSystems.EventSystem", "current"),
            P("UnityEngine.EventSystems.EventSystem", "currentSelectedGameObject"), T("UnityEngine.EventSystems.EventTrigger"),
            P("UnityEngine.EventSystems.EventTrigger", "triggers"), T("UnityEngine.UI.Selectable"), P("UnityEngine.UI.Selectable", "interactable"),
            T("UnityEngine.CanvasGroup"), P("UnityEngine.CanvasGroup", "alpha"),
            // room.gates (SceneDump.GateWatch)
            F("BattleScene", "gates"),
            // room.battles (SceneDump.BattleWatch)
            F("BattleScene", "waves"), F("BattleScene", "currentWave"), F("BattleScene", "currentEnemies"),
            F("BattleScene", "enemiesToNext"), F("BattleScene", "started"), F("BattleScene", "completed"),
            // STATE "allies" (Entities.AllyWatch)
            T("ClockworkHatchling"), F("ClockworkHatchling", "hpCurrent"), P("ClockworkHatchling", "CurrentState"),

            // --- DebugMod 1.1.2 (soft: TRAIN only; savestates and cheat switches) ---
            T("DebugMod.DebugMod", soft: true), F("DebugMod.DebugMod", "infiniteHP", soft: true), F("DebugMod.DebugMod", "infiniteSilk", soft: true),
            F("DebugMod.DebugMod", "infiniteTools", soft: true), F("DebugMod.DebugMod", "playerInvincible", soft: true),
            F("DebugMod.DebugMod", "noclip", soft: true), F("DebugMod.DebugMod", "forcePaused", soft: true), F("DebugMod.DebugMod", "stateOnDeath", soft: true),
            T("DebugMod.SaveStates.SaveStateManager", soft: true), MSoft("DebugMod.SaveStates.SaveStateManager", "LoadState", "DebugMod.SaveStates.SaveState"),
            MSoft("DebugMod.SaveStates.SaveStateManager", "GetQuickState"), MSoft("DebugMod.SaveStates.SaveStateManager", "SaveNewState"),
            T("DebugMod.SaveStates.SaveState", soft: true), P("DebugMod.SaveStates.SaveState", "loadingSavestate", soft: true),
            F("DebugMod.SaveStates.SaveState", "data", soft: true), MAny("DebugMod.SaveStates.SaveState", "IsSet", soft: true),
        };

        /// <summary>False until the check ran and every hard symbol resolved.</summary>
        public static bool Ok { get; private set; }
        public static List<string> Missing { get; private set; } = new List<string> { "<not run>" };
        public static List<string> SoftMissing { get; private set; } = new List<string>();
        public static int ResolvedCount { get; private set; }
        public static int Total => Table.Length;

        private static readonly Dictionary<string, MemberInfo> Resolved = new Dictionary<string, MemberInfo>();

        /// <summary>A resolved member by its table key, e.g. "GameManager.sessionPlayTimer" or
        /// "HeroController.Die(bool,bool)"; null when missing or not in the table.</summary>
        public static MemberInfo Get(string key)
        {
            lock (Resolved) return Resolved.TryGetValue(key, out var m) ? m : null;
        }

        internal sealed class Report
        {
            public bool Ok;
            public List<string> Missing = new List<string>();
            public List<string> SoftMissing = new List<string>();
            public int Resolved;
            public int Total;
            public long Micros;
        }

        /// <summary>Pure resolution pass (no logging, no Unity calls), so it can also run offline against the DLLs.</summary>
        public static Report Evaluate()
        {
            var sw = Stopwatch.StartNew();
            var r = new Report { Total = Table.Length };
            lock (typeCache)
            {
                typeCache.Clear();
                searchOrder = null;
            }
            var found = new Dictionary<string, MemberInfo>();
            foreach (var s in Table)
            {
                MemberInfo m = null;
                string why = null;
                try
                {
                    m = Resolve(s, out why);
                }
                catch (Exception e)
                {
                    why = e.GetType().Name + ": " + e.Message;
                }
                if (m != null)
                {
                    r.Resolved++;
                    found[s.Key] = m;
                    continue;
                }
                var line = why == null ? s.Key : $"{s.Key} ({why})";
                if (s.Soft) r.SoftMissing.Add(line);
                else r.Missing.Add(line);
            }
            lock (Resolved)
            {
                Resolved.Clear();
                foreach (var kv in found) Resolved[kv.Key] = kv.Value;
            }
            r.Ok = r.Missing.Count == 0;
            r.Micros = sw.ElapsedTicks * 1_000_000 / Stopwatch.Frequency;
            return r;
        }

        /// <summary>The last full pass (startup, first frame, or an explicit refresh) and when it ran.</summary>
        private static Report lastReport;
        private static string lastWhen;

        /// <summary>
        /// symbols.check {refresh=false}: the report of the last pass. A pass takes ~27 ms on the main thread (a visible
        /// hitch in gameplay), and the loaded assemblies do not change after the first frame, so only {refresh: true}
        /// runs it again.
        /// </summary>
        public static void Install()
        {
            Run("startup");
            Ipc.Rpc.Register("symbols.check", args =>
            {
                var refresh = Ipc.Rpc.Bool(args, "refresh");
                var r = refresh || lastReport == null ? Run("rpc") : lastReport;
                return new Dictionary<string, object>
                {
                    ["ok"] = r.Ok,
                    ["missing"] = r.Missing,
                    ["soft_missing"] = r.SoftMissing,
                    ["resolved_count"] = r.Resolved,
                    ["total"] = r.Total,
                    ["us"] = r.Micros,
                    ["when"] = lastWhen,
                    ["cached"] = !refresh,
                };
            });
        }

        private static bool lateChecked;

        /// <summary>First frame: DebugMod and other plugins have loaded now, so the soft entries can resolve.</summary>
        internal static void LateCheck()
        {
            if (lateChecked) return;
            lateChecked = true;
            Run("first frame");
        }

        private static Report Run(string when)
        {
            var r = Evaluate();
            lastReport = r;
            lastWhen = when;
            var wasOk = Ok;
            Ok = r.Ok;
            Missing = r.Missing;
            SoftMissing = r.SoftMissing;
            ResolvedCount = r.Resolved;
            if (!r.Ok)
            {
                Plugin.Log.LogError($"SYMBOLCHECK FAILED ({when}): {r.Missing.Count} of {r.Total} symbols missing on game {Plugin.GameVersion}. " +
                                    "Exports and guards that use them are broken; non-TRAIN profiles are refused. Missing:\n  " +
                                    string.Join("\n  ", r.Missing.ToArray()));
            }
            else if (!wasOk || when == "startup")
            {
                Plugin.Log.LogInfo($"SymbolCheck ({when}): {r.Resolved}/{r.Total} resolved in {r.Micros} us" +
                                   (r.SoftMissing.Count > 0 ? $"; soft missing ({r.SoftMissing.Count}): {string.Join(", ", r.SoftMissing.ToArray())}" : ""));
            }
            return r;
        }

        // ---- resolution ----------------------------------------------------------------------------------------

        private const BindingFlags Declared = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance |
                                              BindingFlags.Static | BindingFlags.DeclaredOnly;

        /// <summary>
        /// Same lookup rules as Harmony's AccessTools.Field/Property/Method (walk the type and its base types, any
        /// visibility), done with plain reflection so the table can also be validated offline, outside Unity, where
        /// Harmony's runtime cannot initialize.
        /// </summary>
        private static MemberInfo Resolve(Sym s, out string why)
        {
            why = null;
            var t = ResolveType(s.Type);
            if (t == null) { why = "type not found"; return null; }
            switch (s.Kind)
            {
                case Kind.Type:
                    return t;
                case Kind.Field:
                    return FindField(t, s.Name);
                case Kind.Property:
                    return FindProperty(t, s.Name);
                case Kind.Member:
                    return (MemberInfo)FindField(t, s.Name) ?? FindProperty(t, s.Name);
                case Kind.Event:
                    for (var x = t; x != null; x = x.BaseType)
                    {
                        var e = x.GetEvent(s.Name, Declared);
                        if (e != null) return e;
                    }
                    return null;
                case Kind.Method:
                    if (s.Params == null)
                    {
                        for (var x = t; x != null; x = x.BaseType)
                            foreach (var m in x.GetMethods(Declared))
                                if (m.Name == s.Name) return m;
                        return null;
                    }
                    var ps = new Type[s.Params.Length];
                    for (var i = 0; i < ps.Length; i++)
                    {
                        ps[i] = ResolveType(s.Params[i]);
                        if (ps[i] == null) { why = $"parameter type {s.Params[i]} not found"; return null; }
                    }
                    for (var x = t; x != null; x = x.BaseType)
                    {
                        var m = x.GetMethod(s.Name, Declared, null, ps, null);
                        if (m != null) return m;
                    }
                    return null;
            }
            return null;
        }

        private static FieldInfo FindField(Type t, string name)
        {
            for (var x = t; x != null; x = x.BaseType)
            {
                var f = x.GetField(name, Declared);
                if (f != null) return f;
            }
            return null;
        }

        private static PropertyInfo FindProperty(Type t, string name)
        {
            for (var x = t; x != null; x = x.BaseType)
            {
                foreach (var p in x.GetProperties(Declared))
                    if (p.Name == name) return p;
            }
            return null;
        }

        private static readonly Dictionary<string, Type> Aliases = new Dictionary<string, Type>
        {
            ["int"] = typeof(int), ["bool"] = typeof(bool), ["float"] = typeof(float), ["double"] = typeof(double),
            ["string"] = typeof(string), ["object"] = typeof(object), ["Type"] = typeof(Type),
            ["Action"] = typeof(Action), [ActB] = typeof(Action<bool>),
        };

        /// <summary>Assemblies searched first, in this order; the rest of the AppDomain after them.</summary>
        private static readonly string[] PreferredAssemblies =
        {
            "Assembly-CSharp", "PlayMaker", "TeamCherry.TK2D", "TeamCherry.SharedUtils", "Assembly-CSharp-firstpass",
            "UnityEngine.CoreModule", "UnityEngine.Physics2DModule", "Unity.InputSystem", "UnityEngine.UI", "UnityEngine.UIModule",
            "DebugMod",
        };

        private static readonly Dictionary<string, Type> typeCache = new Dictionary<string, Type>();
        private static List<Assembly> searchOrder;
        private static int searchOrderAssemblies;

        /// <summary>Type by full name (nested types with '+', generics with '`N') from the loaded assemblies; null when absent.</summary>
        public static Type ResolveType(string name)
        {
            if (Aliases.TryGetValue(name, out var alias)) return alias;
            lock (typeCache)
            {
                var asms = AppDomain.CurrentDomain.GetAssemblies();
                if (searchOrder == null || searchOrderAssemblies != asms.Length)
                {
                    // A plugin loaded since the last lookup: rebuild the order and forget cached misses.
                    searchOrder = Order(asms);
                    searchOrderAssemblies = asms.Length;
                    typeCache.Clear();
                }
                if (typeCache.TryGetValue(name, out var cached)) return cached;
                Type found = null;
                foreach (var a in searchOrder)
                {
                    found = TryGetType(a, name);
                    if (found != null) break;
                }
                typeCache[name] = found;
                return found;
            }
        }

        private static List<Assembly> Order(Assembly[] asms)
        {
            var names = new string[asms.Length];
            for (var i = 0; i < asms.Length; i++) names[i] = asms[i].GetName().Name;
            var order = new List<Assembly>(asms.Length);
            foreach (var pref in PreferredAssemblies)
                for (var i = 0; i < asms.Length; i++)
                    if (names[i] == pref) order.Add(asms[i]);
            foreach (var a in asms)
                if (!order.Contains(a)) order.Add(a);
            return order;
        }

        private static Type TryGetType(Assembly a, string name)
        {
            try
            {
                return a.GetType(name, false);
            }
            catch (Exception)
            {
                return null;
            }
        }
    }
}
