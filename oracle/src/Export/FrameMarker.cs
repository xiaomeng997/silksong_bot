using System;
using System.Collections.Generic;
using System.Diagnostics;
using UnityEngine;

namespace SsOracle.Export
{
    /// <summary>
    /// Training-only frame marker (DESIGN §3.1.4 C4; the M1 alignment gate's ground truth): while it is on, every
    /// rendered image carries MarkerCode's pattern of Time.frameCount in one corner, the same number STATE "f" carries
    /// for that frame, so brain/ssbot/record/marker.py can read which frame each captured image shows. RPC
    /// "frame.marker" {on, corner?: tl|tr|bl|br, size?: cell px} turns it on or off; on is refused unless the profile
    /// allows probe tools and outside -ssbot-human (a person's session is training data). It turns itself off when the
    /// brain disconnects or the profile stops allowing probe tools, so a killed probe cannot leave it on. While it is
    /// on, STATE "mk" is non-nil ({drawn, corner, cell, rect, grid, us}; FrameExporter), and "marker" events mark the
    /// switches: a recording with the marker is identifiable and is never training data.
    ///
    /// Why OnGUI: the game renders with the built-in pipeline. The main camera may render into CameraRenderScaled's
    /// texture, which another camera blits to the screen; the HUD camera (clear flags Depth) draws the HUD's tk2d
    /// sprites and, in ScreenSpaceCamera mode, the UI and message canvases (GameCameras.MoveMenuToHUDCamera); and the
    /// game's own full-screen fades draw with IMGUI (CameraFade, GUI.depth -1000). IMGUI draws after every camera and
    /// after screen-space overlay canvases, and GUI.depth orders the OnGUI scripts: this one sets -100000 and so draws
    /// last, over fades and any other OnGUI (DebugMod's), whatever camera setup a scene uses. A camera's OnPostRender
    /// would sit under the HUD camera, the canvases and the fades. Within one player-loop iteration FramedServer.Update
    /// runs the RPC, the cameras render, OnGUI's Repaint draws the marker with Time.frameCount, then FrameExporter's
    /// WaitForEndOfFrame coroutine ("after Unity has rendered every Camera and GUI, just before displaying the frame")
    /// builds the STATE with the same Time.frameCount, and the frame is presented: the image of frame f shows the
    /// marker of f, and the STATE of f says it was drawn ("drawn": this frame's Repaint ran with the marker on).
    ///
    /// Cost: disabled while off (no OnGUI call at all); while on, one 14 x 4 texel texture filled in place
    /// (SetPixels32 of a reused array, Apply without mipmaps) and one GUI.DrawTexture per frame with point filtering,
    /// so each texel is one cell. No allocation per frame in this code; "us" in STATE "mk" is its cost.
    /// </summary>
    internal sealed class FrameMarker : MonoBehaviour
    {
        private const int GuiDepth = -100000;   // lower draws later, i.e. on top; CameraFade uses -1000
        private static readonly string[] CornerNames = { "tl", "tr", "bl", "br" };
        private static readonly Color32 White = new Color32(255, 255, 255, 255);
        private static readonly Color32 Black = new Color32(0, 0, 0, 255);

        private static FrameMarker instance;
        private static volatile bool on;
        private static int corner = 1;
        private static int cellArg;              // 0: MarkerCode.DefaultCell of the current screen height
        private static int cell;
        private static int rx0, ry0, rx1, ry1;   // client px of the last drawn marker
        private static long drawnFrame = -1;
        private static int ownerGeneration = -1;  // FramedServer.Generation of the brain that turned the marker on
        private static long costTicks;

        private readonly bool[] white = new bool[MarkerCode.GridW * MarkerCode.GridH];
        private readonly Color32[] texels = new Color32[MarkerCode.GridW * MarkerCode.GridH];
        private Texture2D tex;

        public static bool On => on;

        public static void Install(GameObject host)
        {
            instance = host.AddComponent<FrameMarker>();
            instance.enabled = false;
            Ipc.Rpc.Register("frame.marker", Rpc);
        }

        private void Awake() => useGUILayout = false;   // Repaint only: no layout pass

        private void OnDestroy()
        {
            if (tex != null) Destroy(tex);
        }

        private static bool Allowed(out string why)
        {
            why = null;
            if (!Core.Profile.Rules.ProbeTools) why = $"probe tools are disabled in profile {Core.Profile.Current}";
            else if (Core.RunMode.Human) why = "-ssbot-human: a person's session is training data";
            return why == null;
        }

        private void OnGUI()
        {
            if (Event.current.type != EventType.Repaint) return;
            var t0 = Stopwatch.GetTimestamp();
            GUI.depth = GuiDepth;
            var server = Ipc.FramedServer.Instance;
            // The connection that turned it on must still be the current one: another brain queued on the port gets
            // connected within a frame of the old one closing, so Connected alone would hand it the marker.
            if (server == null || !server.Connected || server.Generation != ownerGeneration)
            {
                SetOff("brain disconnected");
                return;
            }
            if (!Allowed(out var why))
            {
                SetOff(why);
                return;
            }
            var sw = Screen.width;
            var sh = Screen.height;
            cell = cellArg > 0 ? cellArg : MarkerCode.DefaultCell(sh);
            MarkerCode.Place(sw, sh, corner, cell, out var x0, out var y0);
            long frame = Time.frameCount;
            MarkerCode.Fill(frame, white);
            const int w = MarkerCode.GridW, h = MarkerCode.GridH;
            for (var gr = 0; gr < h; gr++)
                for (var gc = 0; gc < w; gc++)
                    texels[(h - 1 - gr) * w + gc] = white[gr * w + gc] ? White : Black;   // texture rows run bottom-up
            tex.SetPixels32(texels);
            tex.Apply(false);
            var color = GUI.color;
            GUI.color = Color.white;
            GUI.DrawTexture(new Rect(x0, y0, w * cell, h * cell), tex, ScaleMode.StretchToFill, false);
            GUI.color = color;
            rx0 = x0;
            ry0 = y0;
            rx1 = x0 + w * cell;
            ry1 = y0 + h * cell;
            drawnFrame = frame;
            costTicks = Stopwatch.GetTimestamp() - t0;
        }

        /// <summary>STATE "mk" (FrameExporter base section): nil while off.</summary>
        public static void Write(Ipc.MsgPackWriter w, long frame)
        {
            if (!on) { w.Nil(); return; }
            w.MapHeader(6);
            w.Key("drawn"); w.Bool(drawnFrame == frame);
            w.Key("corner"); w.Str(CornerNames[corner]);
            w.Key("cell"); w.Int(cell);
            w.Key("rect"); w.ArrayHeader(4); w.Float(rx0); w.Float(ry0); w.Float(rx1); w.Float(ry1);
            w.Key("grid"); w.ArrayHeader(2); w.Int(MarkerCode.Rows); w.Int(MarkerCode.Cols);
            w.Key("us"); w.Float((float)(costTicks * 1_000_000.0 / Stopwatch.Frequency));
        }

        /// <summary>RPC "frame.marker" {on, corner?, size?} (main thread).</summary>
        private static object Rpc(Dictionary<string, object> args)
        {
            if (!args.ContainsKey("on")) throw new ArgumentException("on (bool) is required");
            if (!Ipc.Rpc.Bool(args, "on"))
            {
                SetOff("rpc");
                return Describe();
            }
            if (!Allowed(out var why)) throw new InvalidOperationException(why);
            var name = Ipc.Rpc.Str(args, "corner", CornerNames[corner]);
            var c = Array.IndexOf(CornerNames, name);
            if (c < 0) throw new ArgumentException("corner must be tl|tr|bl|br");
            var size = (int)Ipc.Rpc.Long(args, "size", 0);
            if (size != 0 && (size < 2 || size > 64)) throw new ArgumentException("size must be 2..64 px per cell (0: default)");
            if (instance.tex == null)
            {
                instance.tex = new Texture2D(MarkerCode.GridW, MarkerCode.GridH, TextureFormat.RGBA32, false, true)
                {
                    filterMode = FilterMode.Point,
                    wrapMode = TextureWrapMode.Clamp,
                    anisoLevel = 0,
                    hideFlags = HideFlags.HideAndDontSave,
                    name = "SsOracle.FrameMarker",
                };
            }
            corner = c;
            cellArg = size;
            cell = size > 0 ? size : MarkerCode.DefaultCell(Screen.height);
            var was = on;
            on = true;
            ownerGeneration = Ipc.FramedServer.Instance != null ? Ipc.FramedServer.Instance.Generation : -1;
            instance.enabled = true;
            if (!was)
            {
                Core.Plugin.Log.LogWarning($"frame marker ON ({CornerNames[corner]}, {cell} px cells): validation only, never training data");
                FrameExporter.Emit("marker", new Dictionary<string, object>
                {
                    ["on"] = true, ["corner"] = CornerNames[corner], ["cell"] = cell,
                });
            }
            return Describe();
        }

        private static void SetOff(string why)
        {
            if (instance != null) instance.enabled = false;
            if (!on) return;
            on = false;
            drawnFrame = -1;
            Core.Plugin.Log.LogInfo($"frame marker off ({why})");
            FrameExporter.Emit("marker", new Dictionary<string, object> { ["on"] = false, ["why"] = why });
        }

        private static Dictionary<string, object> Describe() => new Dictionary<string, object>
        {
            ["on"] = on,
            ["corner"] = CornerNames[corner],
            ["cell"] = on ? cell : cellArg,
            ["rect"] = on && drawnFrame >= 0 ? new List<object> { rx0, ry0, rx1, ry1 } : null,
            ["grid"] = new List<object> { MarkerCode.Rows, MarkerCode.Cols },
            ["bits"] = new List<object> { MarkerCode.DataBits, MarkerCode.CheckBits },
        };
    }
}
