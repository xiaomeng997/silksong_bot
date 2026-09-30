using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace SsOracle.Ipc
{
    /// <summary>
    /// Debug line protocol on 127.0.0.1:47631 (one client at a time), kept next to IPC v1 for manual probes.
    ///   keys [k1,k2,...]   hold exactly these keys from the next frame on (no argument = release all)
    ///   own on|off         whether injected keys replace the physical keyboard
    ///   state              latest per-frame snapshot (JSON)
    ///   constants          engine timing settings + every primitive HeroController field (P11)
    ///   pdget f / pdset f v  read / write a primitive PlayerData field (training-only probe setup)
    ///   hurt n Hazard [side] HeroController.TakeDamage(n, Hazard) through the real damage path (P7/P15)
    /// Every command gets one reply line: "ok", "err ...", or the JSON.
    /// </summary>
    internal sealed class DebugServer
    {
        public const int DefaultPort = 47631;

        private readonly int port;
        private Thread thread;
        private volatile bool running;
        private TcpListener listener;

        public DebugServer(int port) => this.port = port;

        public void Start()
        {
            running = true;
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            thread = new Thread(AcceptLoop) { IsBackground = true, Name = "SsOracle.DebugIpc" };
            thread.Start();
            Core.Plugin.Log.LogInfo($"debug IPC listening on 127.0.0.1:{port}");
        }

        public void Stop()
        {
            running = false;
            listener?.Stop();
        }

        private void AcceptLoop()
        {
            while (running)
            {
                try
                {
                    using (var client = listener.AcceptTcpClient())
                    {
                        client.NoDelay = true;
                        Serve(client);
                    }
                }
                catch (Exception e) when (running)
                {
                    Core.Plugin.Log.LogWarning($"IPC client error: {e.Message}");
                }
                catch
                {
                    return;
                }
            }
        }

        private static void Serve(TcpClient client)
        {
            var stream = client.GetStream();
            var reader = new StreamReader(stream, Encoding.UTF8);
            var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                writer.WriteLine(Handle(line.Trim()));
            }
            // A dropped client must not leave keys held.
            Input.KeyboardInjector.TrySetKeys(new string[0], out _);
        }

        private static string Handle(string line)
        {
            var space = line.IndexOf(' ');
            var cmd = space < 0 ? line : line.Substring(0, space);
            var arg = space < 0 ? "" : line.Substring(space + 1).Trim();
            switch (cmd)
            {
                case "keys":
                    if (!Core.Profile.Rules.Injection) return $"err key injection is disabled in profile {Core.Profile.Current}";
                    var names = arg.Length == 0 ? new string[0] : arg.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                    return Input.KeyboardInjector.TrySetKeys(names, out var error) ? "ok" : "err " + error;
                case "own":
                    if (arg != "on" && arg != "off") return "err own takes on|off";
                    Input.KeyboardInjector.OwnsKeyboard = arg == "on";
                    return "ok";
                case "state":
                    return Core.MainThread.Run(Export.StateProbe.Snapshot);
                case "constants":
                    return Core.MainThread.Run(Export.ConstantsDump.Build);
                case "trace":
                    return int.TryParse(arg, out var n) && n > 0 ? Export.StateProbe.StartTrace(n) : "err trace takes <frames>";
                case "hurt":
                    if (!Core.Profile.Rules.ProbeTools) return $"err probe tools are disabled in profile {Core.Profile.Current}";
                    return Core.MainThread.Run(() => Train.HeroDamage.Hurt(arg));
                case "pdget":
                    return Core.MainThread.Run(() => Train.PlayerDataEdit.Get(arg));
                case "pdset":
                    if (!Core.Profile.Rules.ProbeTools) return $"err probe tools are disabled in profile {Core.Profile.Current}";
                    var parts = arg.Split(new[] { ' ' }, 2);
                    if (parts.Length != 2) return "err pdset takes <field> <value>";
                    // The line server must never be a way around the guards: no Steel Soul state edits, and no lethal
                    // health unless LethalBlock is blocking (with it off or observing, 0 HP is not restored).
                    if (parts[0] == "permadeathMode") return "err permadeathMode is never edited through the debug server";
                    if (parts[0] == "health" && int.TryParse(parts[1], out var hp) && hp <= 0 && Guards.GuardState.Lethal != Guards.LethalMode.Block)
                        return "err health <= 0 is refused unless lethal_block is 'block'";
                    return Core.MainThread.Run(() => Train.PlayerDataEdit.Set(parts[0], parts[1]));
                default:
                    return "err unknown command";
            }
        }
    }
}
