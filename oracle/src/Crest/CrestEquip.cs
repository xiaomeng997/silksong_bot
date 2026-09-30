using System;
using System.Collections.Generic;
using GlobalSettings;
using UnityEngine;

namespace SsOracle.Crest
{
    /// <summary>
    /// RPC "crest.equip" (training probe tool, TRAIN profile only; P17 compares crests on one early save):
    /// <list type="bullet">
    /// <item>{name, unlock=false, force=false}: equip crest <c>name</c> the way the bench inventory does it
    /// (InventoryToolCrestList.SetCurrentCrest -> ToolItemManager.SetEquippedCrest, then the SendToolEquipChanged action ->
    /// SendEquippedChangedEvent, whose "TOOL EQUIPS CHANGED" makes HeroController.ResetAllCrestState load the crest's
    /// HeroConfig). The crest keeps its own saved tool equips. A crest this save has not unlocked is refused unless
    /// unlock=true, which runs ToolCrest.Unlock first (as picking it up does: previous versions too, and an upgrade of
    /// the equipped crest is equipped right away; the crest achievements it reports are blocked by AchievementGuard,
    /// which must be on). The Cursed and Cloakless crests need force=true.</item>
    /// <item>{restore: true}: undo every crest.equip since the first one on this PlayerData: equip the crest that was
    /// equipped then (same path), put PreviousCrestID and IsCurrentCrestTemp back, and relock what unlock=true unlocked
    /// (its PlayerData.ToolEquips entry goes back to what it was, or away).</item>
    /// </list>
    /// Refused unless the profile allows probe tools, saves are redirected to the sandbox (the change reaches disk with
    /// the next save), the guards are not refused, a Steel Soul session has a snapshot, a hero exists and the inventory is
    /// closed. The edit is in memory only; the probe keeps SaveSuppression on while it runs so nothing it did is saved.
    /// Reply: {frame, crest, from, previous, temp, unlocked: [names], at_bench, config, group} or, for restore,
    /// {frame, restored, crest, previous, temp, relocked: [names], config, group}; config/group = the hero's config
    /// right after the switch (the "TOOL EQUIPS CHANGED" handlers run synchronously).
    /// </summary>
    internal static class CrestEquip
    {
        private sealed class Unlocked
        {
            public string Name;
            public bool Present;
            public ToolCrestsData.Data Data;
        }

        /// <summary>What crest.equip changed on one PlayerData instance (weakly held: never kept alive, m0:N42).</summary>
        private sealed class Snapshot
        {
            public WeakReference<PlayerData> Pd;
            public string Crest, Previous;
            public bool Temp;
            public readonly List<Unlocked> Unlocked = new List<Unlocked>();

            public bool Of(PlayerData pd) => Pd.TryGetTarget(out var p) && ReferenceEquals(p, pd);
        }

        private static Snapshot snap;

        public static object Equip(Dictionary<string, object> args)
        {
            if (!Core.Profile.Rules.ProbeTools) throw new InvalidOperationException($"probe tools are disabled in profile {Core.Profile.Current}");
            if (!Guards.SaveRedirect.Redirected) throw new InvalidOperationException("saves are not redirected to the sandbox; crest.equip refused");
            if (Guards.GuardState.Refused) throw new InvalidOperationException("guards are refused: " + string.Join("; ", Guards.GuardState.Refusals.ToArray()));
            if (Guards.SteelSoulSnapshot.Unprotected(out var slot))
                throw new InvalidOperationException($"the Steel Soul session in slot {slot} has no snapshot (slot.snapshot first)");
            var pd = CrestModule.RequirePd();
            var hero = CrestModule.RequireHero();
            // ToolCrest.Unlock and SaveData go through PlayerData.instance: it must be the game's PlayerData.
            if (!PlayerData.HasInstance || !ReferenceEquals(PlayerData.instance, pd))
                throw new InvalidOperationException("PlayerData.instance is not GameManager's playerData");
            if (pd.isInventoryOpen) throw new InvalidOperationException("close the inventory first");

            if (Ipc.Rpc.Bool(args, "restore")) return Restore(pd, hero);

            var name = Ipc.Rpc.Str(args, "name");
            if (string.IsNullOrEmpty(name)) throw new ArgumentException("name (a ToolCrest name, e.g. Wanderer) or restore=true");
            var crest = ToolItemManager.GetCrestByName(name);
            if (crest == null) throw new ArgumentException($"no crest '{name}'");
            if ((crest == Gameplay.CursedCrest || crest == Gameplay.CloaklessCrest) && !Ipc.Rpc.Bool(args, "force"))
                throw new InvalidOperationException($"'{name}' is a story crest (curse / Slab); pass force=true");

            if (snap == null || !snap.Of(pd))
                snap = new Snapshot { Pd = new WeakReference<PlayerData>(pd), Crest = pd.CurrentCrestID, Previous = pd.PreviousCrestID, Temp = pd.IsCurrentCrestTemp };
            var from = pd.CurrentCrestID;
            var unlocked = new List<string>();
            if (!CrestModule.SavedCrest(pd, crest.name, out _).IsUnlocked)
            {
                if (!Ipc.Rpc.Bool(args, "unlock")) throw new InvalidOperationException($"crest '{name}' is not unlocked on this save (pass unlock=true)");
                if (!Guards.GuardState.AchievementGuard || !Guards.GuardState.AchievementHealthy)
                    throw new InvalidOperationException("unlocking a crest reports crest achievements: achievement_guard must be on and healthy");
                Unlock(crest, pd, unlocked);
            }
            Core.Plugin.Log.LogWarning($"crest.equip {from} -> {crest.name}{(unlocked.Count > 0 ? " (unlocked " + string.Join(", ", unlocked.ToArray()) + ")" : "")} (training probe)");
            ToolItemManager.SetEquippedCrest(crest.name);
            ToolItemManager.SendEquippedChangedEvent();
            return new Dictionary<string, object>
            {
                ["frame"] = Time.frameCount,
                ["crest"] = pd.CurrentCrestID,
                ["from"] = from,
                ["previous"] = pd.PreviousCrestID,
                ["temp"] = pd.IsCurrentCrestTemp,
                ["unlocked"] = unlocked,
                ["at_bench"] = pd.atBench,
                ["config"] = CrestModule.Name(hero.Config),
                ["group"] = CrestDump.CurrentGroupIndex(hero),
            };
        }

        /// <summary>ToolCrest.Unlock, recording first the saved data of every crest in the upgrade chain it may unlock.</summary>
        private static void Unlock(ToolCrest crest, PlayerData pd, List<string> unlocked)
        {
            var chain = new List<ToolCrest>();
            foreach (var c in ToolItemManager.GetAllCrests())
                if (c != null && !CrestModule.SavedCrest(pd, c.name, out _).IsUnlocked) chain.Add(c);
            var before = new List<Unlocked>();
            foreach (var c in chain)
            {
                var data = CrestModule.SavedCrest(pd, c.name, out var present);
                before.Add(new Unlocked { Name = c.name, Present = present, Data = Copy(data) });
            }
            crest.Unlock();
            foreach (var b in before)
            {
                if (!CrestModule.SavedCrest(pd, b.Name, out _).IsUnlocked) continue;
                unlocked.Add(b.Name);
                if (snap.Unlocked.Find(u => u.Name == b.Name) == null) snap.Unlocked.Add(b);
            }
        }

        private static object Restore(PlayerData pd, HeroController hero)
        {
            if (snap == null) throw new InvalidOperationException("nothing to restore: crest.equip changed nothing on this PlayerData");
            if (!snap.Of(pd))
            {
                snap = null;
                throw new InvalidOperationException("PlayerData was replaced since crest.equip (savestate, reload or quit): nothing to restore");
            }
            var s = snap;
            var changed = pd.CurrentCrestID != s.Crest || s.Unlocked.Count > 0 || pd.PreviousCrestID != s.Previous || pd.IsCurrentCrestTemp != s.Temp;
            Core.Plugin.Log.LogWarning($"crest.equip restore {pd.CurrentCrestID} -> {s.Crest}, relock {s.Unlocked.Count} (training probe)");
            ToolItemManager.SetEquippedCrest(s.Crest);
            var relocked = new List<string>();
            var dict = CrestModule.ToolEquipsData != null ? CrestModule.ToolEquipsData(pd.ToolEquips) : null;
            foreach (var u in s.Unlocked)
            {
                if (u.Present) pd.ToolEquips.SetData(u.Name, u.Data);
                else if (dict != null) dict.Remove(u.Name);
                else pd.ToolEquips.SetData(u.Name, default);
                relocked.Add(u.Name);
            }
            pd.PreviousCrestID = s.Previous;
            pd.IsCurrentCrestTemp = s.Temp;
            if (changed) ToolItemManager.SendEquippedChangedEvent(force: true);
            snap = null;
            return new Dictionary<string, object>
            {
                ["frame"] = Time.frameCount,
                ["restored"] = true,
                ["crest"] = pd.CurrentCrestID,
                ["previous"] = pd.PreviousCrestID,
                ["temp"] = pd.IsCurrentCrestTemp,
                ["relocked"] = relocked,
                ["config"] = CrestModule.Name(hero.Config),
                ["group"] = CrestDump.CurrentGroupIndex(hero),
            };
        }

        private static ToolCrestsData.Data Copy(ToolCrestsData.Data d) => new ToolCrestsData.Data
        {
            IsUnlocked = d.IsUnlocked,
            Slots = d.Slots != null ? new List<ToolCrestsData.SlotData>(d.Slots) : null,
            DisplayNewIndicator = d.DisplayNewIndicator,
        };
    }
}
