using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading;
using GlobalEnums;

namespace SsOracle.Guards
{
    /// <summary>
    /// SteelSoulSnapshot (DESIGN §3.1.1 Guards): copies one save slot of the sandbox save folder
    /// (SaveRedirect.SandboxRoot\default, where the Steam-less training copy saves) to
    /// SandboxRoot\snapshots\slot{N}\{name}\ and back. A slot is every file the game keeps for it (m0:C13, N31):
    /// user{N}.dat (slot 0: user.dat), its rotating backups user{N}.dat.bak{K} and .del, the per-version backups
    /// user{N}_*.dat (user{N}_1.0.30000.dat) and the Restore_Points{N} folder. After a Steel Soul death only the
    /// backups and restore points still hold the living state, so a snapshot is the way back.
    ///
    /// Every path is resolved and must lie under C:\ssbot\sandbox\; anything else is refused. Copies run on a worker
    /// thread (the RPC replies when done). Restores are refused while a game is running (the game would overwrite the
    /// files on its next save, and the save-select menu caches slot contents, P5) unless force=true.
    ///
    /// DESIGN §3.1.1: a Steel Soul training slot may only be used with a snapshot. SessionGate enforces it before any
    /// damage can happen: continuing a Steel Soul save whose slot has no snapshot first takes one named "auto" (on the
    /// main thread, during the menu fade; the files on disk are exactly the living state just loaded), and refuses the
    /// Continue if that fails. A new Steel Soul game has nothing on disk to protect yet; until slot.snapshot is taken
    /// for it the session counts as unprotected: reported once ("steel_soul_unprotected"), guards.set cannot take
    /// LethalBlock out of block, hurt.special refuses hits that could kill, and non-TRAIN profiles report a violation.
    /// </summary>
    internal static class SteelSoulSnapshot
    {
        public const string SandboxGuard = @"C:\ssbot\sandbox\";
        private static readonly Regex NameRe = new Regex("^[A-Za-z0-9_-]{1,40}$");
        private static int busy;

        public static string SaveDir => Path.Combine(SaveRedirect.SandboxRoot, "default");
        public static string SnapshotRoot => Path.Combine(SaveRedirect.SandboxRoot, "snapshots");

        public static void Install()
        {
            Ipc.Rpc.Register("slot.snapshot", Snapshot);
            Ipc.Rpc.Register("slot.restore", Restore);
            Ipc.Rpc.Register("slot.list", List);
        }

        public static string PrimaryName(int slot) => slot == 0 ? "user.dat" : $"user{slot}.dat";
        public static string PrimaryFile(int slot) => Path.Combine(SaveDir, PrimaryName(slot));

        /// <summary>Resolves a path and refuses anything outside the sandbox (instance ids come from the command line).</summary>
        private static string Sandboxed(string path)
        {
            var full = Path.GetFullPath(path);
            if (!full.StartsWith(SandboxGuard, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"refusing path outside {SandboxGuard}: {full}");
            return full;
        }

        private static int Slot(Dictionary<string, object> args)
        {
            if (!args.ContainsKey("slot")) throw new ArgumentException("slot is required (0-4; 0 = user.dat)");
            var slot = Ipc.Rpc.Long(args, "slot", -1);
            if (slot < 0 || slot > 4) throw new ArgumentException($"slot {slot} out of range 0-4");
            return (int)slot;
        }

        private static string Name(Dictionary<string, object> args)
        {
            var name = Ipc.Rpc.Str(args, "name", "latest");
            if (!NameRe.IsMatch(name)) throw new ArgumentException("name must match [A-Za-z0-9_-]{1,40}");
            return name;
        }

        private static string SnapshotDir(int slot, string name) => Sandboxed(Path.Combine(SnapshotRoot, $"slot{slot}", name));

        /// <summary>The slot has at least one complete snapshot (a directory holding the primary file; not a .tmp).</summary>
        public static bool HasSnapshot(int slot)
        {
            var dir = Sandboxed(Path.Combine(SnapshotRoot, $"slot{slot}"));
            if (!Directory.Exists(dir)) return false;
            foreach (var d in Directory.GetDirectories(dir))
                if (!d.EndsWith(".tmp", StringComparison.Ordinal) && File.Exists(Path.Combine(d, PrimaryName(slot))))
                    return true;
            return false;
        }

        /// <summary>The slot's files and folders inside <paramref name="dir"/> (names relative to it).</summary>
        private static List<string> SlotEntries(string dir, int slot)
        {
            var list = new List<string>();
            if (!Directory.Exists(dir)) return list;
            var primary = PrimaryName(slot);
            var versioned = $"user{slot}_";
            foreach (var f in Directory.GetFiles(dir))
            {
                var n = Path.GetFileName(f);
                if (n == primary || n.StartsWith(primary + ".bak", StringComparison.Ordinal) || n.StartsWith(primary + ".del", StringComparison.Ordinal) ||
                    (n.StartsWith(versioned, StringComparison.Ordinal) && n.EndsWith(".dat", StringComparison.Ordinal)))
                    list.Add(n);
            }
            var rp = $"Restore_Points{slot}";
            if (Directory.Exists(Path.Combine(dir, rp))) list.Add(rp + Path.DirectorySeparatorChar);
            return list;
        }

        private static void CopyEntries(string from, string to, List<string> entries)
        {
            Directory.CreateDirectory(to);
            foreach (var e in entries)
            {
                if (e.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal))
                    CopyDir(Sandboxed(Path.Combine(from, e.TrimEnd(Path.DirectorySeparatorChar))), Sandboxed(Path.Combine(to, e.TrimEnd(Path.DirectorySeparatorChar))));
                else
                    File.Copy(Sandboxed(Path.Combine(from, e)), Sandboxed(Path.Combine(to, e)), overwrite: true);
            }
        }

        private static void CopyDir(string from, string to)
        {
            Directory.CreateDirectory(to);
            foreach (var f in Directory.GetFiles(from))
                File.Copy(f, Sandboxed(Path.Combine(to, Path.GetFileName(f))), overwrite: true);
            foreach (var d in Directory.GetDirectories(from))
                CopyDir(d, Sandboxed(Path.Combine(to, Path.GetFileName(d))));
        }

        private static void DeleteEntries(string dir, List<string> entries)
        {
            foreach (var e in entries)
            {
                var p = Sandboxed(Path.Combine(dir, e.TrimEnd(Path.DirectorySeparatorChar)));
                if (Directory.Exists(p)) Directory.Delete(p, recursive: true);
                else if (File.Exists(p)) File.Delete(p);
            }
        }

        /// <summary>
        /// Runs file work off the main thread, one operation at a time. The event, the reply and
        /// <paramref name="onMain"/> (bookkeeping read by the monitor) run back on the main thread: Emit reads
        /// Time.frameCount, which Unity only allows there.
        /// </summary>
        private static void RunIo(Ipc.Rpc.Reply reply, string what, Func<Dictionary<string, object>> work, Action onMain = null)
        {
            if (Interlocked.CompareExchange(ref busy, 1, 0) != 0) { reply.Fail("another slot operation is running"); return; }
            ThreadPool.QueueUserWorkItem(_ =>
            {
                Dictionary<string, object> result = null;
                Exception error = null;
                try
                {
                    result = work();
                    Core.Plugin.Log.LogInfo($"{what}: {result["dir"]}");
                }
                catch (Exception e)
                {
                    error = e;
                    Core.Plugin.Log.LogError($"{what} failed: {e}");
                }
                finally
                {
                    Interlocked.Exchange(ref busy, 0);
                }
                GuardsMonitor.Post(() =>
                {
                    if (error != null)
                    {
                        reply.Fail(error.GetType().Name + ": " + error.Message);
                        return;
                    }
                    onMain?.Invoke();
                    if (what != "slot_list") Export.FrameExporter.Emit(what, result);  // only changes are events
                    reply.Ok(result);
                });
            });
        }

        /// <summary>slot.snapshot {slot, name="latest"}: replace snapshot {name} of the slot with the slot's current files.</summary>
        private static void Snapshot(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            var slot = Slot(args);
            var name = Name(args);
            RunIo(reply, "slot_snapshot", () => SnapshotNow(slot, name), () =>
            {
                if (sessionSlot == slot) sessionHasSnapshot = true;
            });
        }

        /// <summary>Copies the slot's files into snapshot {name} (through a .tmp directory, so a failed copy never
        /// replaces a good snapshot). Any thread; the caller holds <see cref="busy"/>.</summary>
        private static Dictionary<string, object> SnapshotNow(int slot, string name)
        {
            var src = Sandboxed(SaveDir);
            var dst = SnapshotDir(slot, name);
            var entries = SlotEntries(src, slot);
            if (!entries.Contains(PrimaryName(slot)))
                throw new FileNotFoundException($"slot {slot} has no {PrimaryName(slot)} in {src}");
            var tmp = Sandboxed(dst + ".tmp");
            if (Directory.Exists(tmp)) Directory.Delete(tmp, recursive: true);
            CopyEntries(src, tmp, entries);
            if (Directory.Exists(dst)) Directory.Delete(dst, recursive: true);
            Directory.Move(tmp, dst);
            return new Dictionary<string, object> { ["slot"] = slot, ["name"] = name, ["dir"] = dst, ["entries"] = entries };
        }

        /// <summary>Name of the snapshot SessionGate takes for an unprotected Steel Soul Continue.</summary>
        public const string AutoName = "auto";

        /// <summary>
        /// SessionGate, main thread, GameManager.ContinueGame prefix (LoadGame has already set gm.playerData and
        /// gm.profileID): null when the session may start, else why not. A Steel Soul save whose slot has no snapshot
        /// gets one named "auto" first.
        /// </summary>
        internal static string EnsureForContinue(GameManager gm)
        {
            var pd = gm != null ? gm.playerData : null;
            if (pd == null || pd.permadeathMode != PermadeathModes.On) return null;
            var slot = gm.profileID;
            try
            {
                if (HasSnapshot(slot)) return null;
                if (Interlocked.CompareExchange(ref busy, 1, 0) != 0)
                    return $"Steel Soul slot {slot} has no snapshot and another slot operation is running; try again";
                Dictionary<string, object> result;
                try
                {
                    result = SnapshotNow(slot, AutoName);
                }
                finally
                {
                    Interlocked.Exchange(ref busy, 0);
                }
                result["auto"] = true;
                Core.Plugin.Log.LogWarning($"Steel Soul slot {slot} had no snapshot: took '{AutoName}' before Continue ({result["dir"]})");
                Export.FrameExporter.Emit("slot_snapshot", result);
                return null;
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError($"automatic snapshot of Steel Soul slot {slot} failed: {e}");
                return $"Steel Soul slot {slot} has no snapshot and taking one failed ({e.GetType().Name}: {e.Message}); " +
                       "a Steel Soul training slot may only be used with a snapshot";
            }
        }

        /// <summary>slot.restore {slot, name="latest", force=false}: replace the slot's files with the snapshot.</summary>
        private static void Restore(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            var slot = Slot(args);
            var name = Name(args);
            var force = Ipc.Rpc.Bool(args, "force");
            if (GuardState.Refused) { reply.Fail("guards are refused: " + string.Join("; ", GuardState.Refusals.ToArray())); return; }
            var gm = GameManager._instance;
            var inGame = gm != null && gm.GameState != GameState.MAIN_MENU && gm.GameState != GameState.INACTIVE && HeroController.UnsafeInstance != null;
            if (inGame && !force)
            {
                reply.Fail("a game is running (it would overwrite the restored files); restore from the main menu or pass force=true");
                return;
            }
            var src = SnapshotDir(slot, name);
            var dst = Sandboxed(SaveDir);
            RunIo(reply, "slot_restore", () =>
            {
                var entries = SlotEntries(src, slot);
                if (!entries.Contains(PrimaryName(slot)))
                    throw new FileNotFoundException($"no snapshot '{name}' for slot {slot} at {src}");
                var old = SlotEntries(dst, slot);
                DeleteEntries(dst, old);
                // Stale temp file from an interrupted write; the game deletes it anyway (DesktopPlatform.WriteSaveSlot).
                var tempNew = Path.Combine(dst, PrimaryName(slot) + ".new");
                if (File.Exists(tempNew)) File.Delete(Sandboxed(tempNew));
                CopyEntries(src, dst, entries);
                return new Dictionary<string, object>
                {
                    ["slot"] = slot, ["name"] = name, ["dir"] = src, ["removed"] = old, ["entries"] = entries, ["in_game"] = inGame,
                    ["note"] = "re-enter the save-select menu before loading: it caches slot contents",
                };
            });
        }

        /// <summary>slot.list {slot?}: snapshots with their entries and times.</summary>
        private static void List(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            var only = args.ContainsKey("slot") ? Slot(args) : -1;
            var root = Sandboxed(SnapshotRoot);
            RunIo(reply, "slot_list", () =>
            {
                var slots = new List<object>();
                for (var s = 0; s <= 4; s++)
                {
                    if (only >= 0 && s != only) continue;
                    var dir = Path.Combine(root, $"slot{s}");
                    if (!Directory.Exists(dir)) continue;
                    foreach (var d in Directory.GetDirectories(dir))
                    {
                        if (d.EndsWith(".tmp", StringComparison.Ordinal)) continue;
                        slots.Add(new Dictionary<string, object>
                        {
                            ["slot"] = s,
                            ["name"] = Path.GetFileName(d),
                            ["entries"] = SlotEntries(d, s),
                            ["time_utc"] = Directory.GetLastWriteTimeUtc(d).ToString("o"),
                        });
                    }
                }
                return new Dictionary<string, object> { ["dir"] = root, ["save_dir"] = SaveDir, ["snapshots"] = slots };
            });
        }

        // ---- Steel Soul session check --------------------------------------------------------------------------

        private static int sessionSlot = -1;
        private static bool sessionSteel, sessionHasSnapshot;
        private static int sessionPdId;

        /// <summary>Once per PlayerData instance while PLAYING: a Steel Soul slot must have a snapshot (one directory probe).</summary>
        internal static void Tick(GameManager gm, PlayerData pd)
        {
            if (gm == null || pd == null || gm.GameState != GameState.PLAYING) return;
            var id = System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(pd);
            if (id == sessionPdId) return;
            sessionPdId = id;
            sessionSlot = gm.profileID;
            sessionSteel = pd.permadeathMode == PermadeathModes.On;
            if (!sessionSteel) return;
            string dir;
            try
            {
                dir = Sandboxed(Path.Combine(SnapshotRoot, $"slot{sessionSlot}"));
                sessionHasSnapshot = HasSnapshot(sessionSlot);
            }
            catch (Exception e)
            {
                Core.Plugin.Log.LogError("snapshot check failed: " + e.Message);
                sessionHasSnapshot = false;
                return;
            }
            if (!sessionHasSnapshot)
            {
                Core.Plugin.Log.LogWarning($"Steel Soul session in slot {sessionSlot} has no snapshot (slot.snapshot before risky training)");
                Export.FrameExporter.Emit("steel_soul_unprotected", new Dictionary<string, object> { ["slot"] = sessionSlot, ["dir"] = dir });
            }
        }

        /// <summary>
        /// Main thread: a Steel Soul session is running (a hero exists) and its slot has no snapshot. DESIGN §3.1.1: a
        /// Steel Soul training slot may only be used with a snapshot, so non-TRAIN profiles treat this as a violation,
        /// guards.set keeps LethalBlock blocking and hurt.special refuses hits that could kill.
        /// </summary>
        internal static bool Unprotected(out int slot)
        {
            slot = sessionSlot;
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            return sessionSteel && !sessionHasSnapshot && pd != null && HeroController.UnsafeInstance != null &&
                   System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(pd) == sessionPdId;
        }

        internal static Dictionary<string, object> SessionInfo() => new Dictionary<string, object>
        {
            ["slot"] = sessionSlot,
            ["steel_soul"] = sessionSteel,
            ["has_snapshot"] = sessionHasSnapshot,
            ["save_dir"] = SaveDir,
        };
    }
}
