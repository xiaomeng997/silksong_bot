using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace SsOracle.Ipc
{
    /// <summary>
    /// M0 line protocol on 127.0.0.1 (one client at a time). Replaced by the framed TCP protocol in M1.
    ///   keys [k1,k2,...]   hold exactly these keys from the next frame on (no argument = release all)
    ///   own on|off         whether injected keys replace the physical keyboard
    ///   state              latest per-frame snapshot (JSON)
    /// Every command gets one reply line: "ok", "err ...", or the JSON.
    /// </summary>
    internal sealed class Server
    {
        public const int DefaultPort = 47631;

        private readonly int port;
        private Thread thread;
        private volatile bool running;
        private TcpListener listener;

        public Server(int port) => this.port = port;

        public void Start()
        {
            running = true;
            listener = new TcpListener(IPAddress.Loopback, port);
            listener.Start();
            thread = new Thread(AcceptLoop) { IsBackground = true, Name = "SsOracle.Ipc" };
            thread.Start();
            Core.Plugin.Log.LogInfo($"IPC listening on 127.0.0.1:{port}");
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
                    var names = arg.Length == 0 ? new string[0] : arg.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                    return Input.KeyboardInjector.TrySetKeys(names, out var error) ? "ok" : "err " + error;
                case "own":
                    if (arg != "on" && arg != "off") return "err own takes on|off";
                    Input.KeyboardInjector.OwnsKeyboard = arg == "on";
                    return "ok";
                case "state":
                    return Export.StateProbe.Latest ?? "{}";
                default:
                    return "err unknown command";
            }
        }
    }
}
