using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using GlobalEnums;
using UnityEngine;
using Geometry = SsOracle.Entities.ColliderGeometry;
using Rpc = SsOracle.Ipc.Rpc;

namespace SsOracle.Train
{
    /// <summary>
    /// Projection calibration against DebugMod's hitbox display (DESIGN §3.1.3; M1 exit "projection IoU >= 0.95, vertex
    /// error <= 1.5 px"), driven by brain/ssbot/probes/m1_projection.py. DebugModBridge's hitbox section describes what
    /// DebugMod draws and when.
    ///   hitbox.show {on?, mode?, ui?, panels?, timeout? = 3}
    ///       Training probe tool (Profile ProbeTools): sets DebugMod's ShowHitBoxes (on -> 1 / 0, or mode 0..2) and shows
    ///       or hides its UI panels (ui: all of them; panels: {MainPanelVisible: bool, ...} as "panels" reports them, to
    ///       restore a previous state); answers once HitboxViewer has (un)loaded and a new HitboxRender has
    ///       started (outside gameplay scenes at once, since DebugMod draws nothing there), or at the timeout with
    ///       settled false. Reply {show, state, render, colliders, line_width, gameplay, panels, settled, frames, version}
    ///       plus prev {show, panels} when it changed something. Without arguments it only reports (any profile). Both
    ///       settings persist in the sandbox's DebugModData\Settings.json, so callers switch them back: a hitbox overlay
    ///       left on would leak into every later capture (DESIGN §3.1.8 L1; non-TRAIN profiles refuse it).
    ///   projection.sample {source? = auto|debugmod|physics, max? = 2000}
    ///       Read-only. Unity's own Camera.WorldToScreenPoint of collider outlines for the frame the request arrives in,
    ///       so the brain can compare it with ssbot/tools/projector.py on the STATE of that frame ("frame" = STATE "f"):
    ///       source debugmod (auto picks it while the display runs): the colliders HitboxRender draws in that frame,
    ///       under its own filter (live, isActiveAndEnabled, not IGNORE_RAYCAST, bounds overlapping Camera.main's
    ///       viewport at end of frame); physics: every collider Physics2D.OverlapArea finds in the main camera's view of
    ///       the z = 0 plane. Per collider (one entry per polygon path):
    ///         id (Collider2D instance id = TERRAIN solid/hazard id), path, go, type (DebugMod HitboxType name) and
    ///         color [r, g, b] (0..1) or nil, kind (box|circle|poly|capsule|edge|aabb), closed, layer, trigger,
    ///         er (box/edge edgeRadius), r (circle radius as the ents export computes it),
    ///         w: the outline DebugMod draws, world x0, y0, ... at z = 0 (box TL, TR, BR, BL without edgeRadius; poly path;
    ///            edge chain; circle centre and centre + radius along local x; capsule/other: same as o),
    ///         o: the outline as STATE "ents" exports it (Entities.ColliderGeometry: box with edgeRadius, circle as the
    ///            circumscribed octagon, ...), float-identical to ents verts_world for the same collider and frame,
    ///         s: WorldToScreenPoint of w (x, y pairs; Unity screen pixels, bottom-left origin, in the camera's target:
    ///            a render texture when "cam".rt) taken in the main camera's Camera.onPreRender, i.e. with the V/P that
    ///            STATE "cam" carries when its src is 1 (camera shake included); nil if the camera did not render,
    ///         e: the same with Camera.main at end of frame, the pose DebugMod's OnGUI projects with (shake removed),
    ///         moved: largest change of w between the render callback and end of frame (world units), plus we (the
    ///            end-of-frame w) when it is not 0.
    ///       Also frame, q (raw QPC at end of frame), source, dm {show, state, line_width, version} | nil, cam (the main
    ///       camera at render time: id, name, is_main, pixel_rect, rect, target [w, h], rt, screen, V, P, pos, render),
    ///       dm_cam (Camera.main at end of frame, same keys), n {candidates, cols, truncated}, us {render, eof}.
    ///       Costs one frame a few milliseconds while DebugMod's dictionary holds thousands of colliders; never runs
    ///       unless asked.
    /// </summary>
    internal sealed class ProjectionSample : MonoBehaviour
    {
        private const int IgnoreRaycastLayer = (int)PhysLayers.IGNORE_RAYCAST;
        /// <summary>Viewport margin for render-time candidates, so a collider the end-of-frame (unshaken) view still
        /// overlaps is not lost to the shake.</summary>
        private const float CandidateMargin = 0.1f;
        private const int DefaultMax = 2000;

        private sealed class Col
        {
            public Collider2D C;
            public int Id, Path;
            public string Type;
            public Color Color;
            public byte Kind;
            public float Radius, EdgeRadius;
            public float[] W, O, S;
        }

        private sealed class Pending
        {
            public Rpc.Reply Reply;
            public bool DebugMod;
            public int Max;
            public int Frame;
            public Camera Cam;
            public bool Rendered;
            public Dictionary<string, object> CamInfo;
            public readonly List<Col> Cols = new List<Col>();
            public int Candidates;
            public bool Truncated;
            public long RenderTicks;
        }

        private static ProjectionSample instance;
        private static Pending pending;
        private static readonly WaitForEndOfFrame Eof = new WaitForEndOfFrame();
        private static readonly List<DebugModBridge.HitboxEntry> Entries = new List<DebugModBridge.HitboxEntry>();
        private static readonly List<Vector2> Points = new List<Vector2>(256);
        private static readonly List<float> Scratch = new List<float>(256);

        public static void Install(GameObject host)
        {
            instance = host.AddComponent<ProjectionSample>();
            Rpc.Register("hitbox.show", Show);
            Rpc.Register("projection.sample", Sample);
        }

        // ---- hitbox.show -------------------------------------------------------------------------------------------

        private static void Show(Dictionary<string, object> args, Rpc.Reply reply)
        {
            if (!DebugModBridge.ResolveHitboxes()) { reply.Fail(DebugModBridge.HitboxError); return; }
            var change = args.ContainsKey("on") || args.ContainsKey("mode") || args.ContainsKey("ui") || args.ContainsKey("panels");
            if (!change) { reply.Ok(Status(true, 0)); return; }
            if (!Core.Profile.Rules.ProbeTools) { reply.Fail($"probe tools are disabled in profile {Core.Profile.Current}"); return; }

            var before = DebugModBridge.ShowHitboxes;
            var mode = args.ContainsKey("mode") ? (int)Rpc.Long(args, "mode")
                : args.ContainsKey("on") ? (Rpc.Bool(args, "on") ? 1 : 0) : before;
            if (mode < 0 || mode > 2) { reply.Fail("mode must be 0 (off), 1 (hitboxes) or 2 (all hitboxes)"); return; }
            var prev = new Dictionary<string, object> { ["show"] = before, ["panels"] = DebugModBridge.Panels() };
            var old = DebugModBridge.HitboxRenderer;
            var reload = mode != 0 && DebugModBridge.HitboxViewerState != mode;
            if (before != mode)
            {
                DebugModBridge.ShowHitboxes = mode;
                Core.Plugin.Log.LogWarning($"hitbox.show: DebugMod ShowHitBoxes {before} -> {mode} (training probe; saved in the sandbox Settings.json)");
            }
            if (args.ContainsKey("ui"))
            {
                var ui = Rpc.Bool(args, "ui");
                DebugModBridge.SetPanels(_ => ui);
            }
            if (args.TryGetValue("panels", out var pv) && pv is Dictionary<string, object> panels)
                DebugModBridge.SetPanels(name => panels.TryGetValue(name, out var v) && v is bool b ? b : (bool?)null);
            instance.StartCoroutine(instance.WaitShown(mode, reload, old, Rpc.Double(args, "timeout", 3.0), prev, reply));
        }

        private IEnumerator WaitShown(int mode, bool reload, UnityEngine.Object old, double timeoutS, Dictionary<string, object> prev, Rpc.Reply reply)
        {
            var clock = Stopwatch.StartNew();
            var frames = 0;
            while (true)
            {
                Dictionary<string, object> status = null;
                try
                {
                    var settled = Settled(mode, reload, old);
                    if (settled || clock.Elapsed.TotalSeconds > timeoutS)
                    {
                        status = Status(settled, frames);
                        status["prev"] = prev;
                    }
                }
                catch (Exception e)
                {
                    reply.Fail("hitbox.show: " + e.Message);
                    yield break;
                }
                if (status != null)
                {
                    reply.Ok(status);
                    yield break;
                }
                frames++;
                yield return null;
            }
        }

        /// <summary>GUIController.Update has applied the mode: the viewer state matches and the renderer is gone (off) or a
        /// started one exists (on; a new one when the viewer reloads, since the old component is destroyed only at the end
        /// of that frame). Outside gameplay scenes DebugMod never creates a renderer, so there is nothing to wait for.</summary>
        private static bool Settled(int mode, bool reload, UnityEngine.Object old)
        {
            var gm = GameManager._instance;
            if (gm == null || !gm.IsGameplayScene()) return true;
            if (DebugModBridge.HitboxViewerState != mode) return false;
            var renderer = DebugModBridge.HitboxRenderer;
            if (mode == 0) return renderer == null;
            return renderer != null && (!reload || !ReferenceEquals(renderer, old));
        }

        private static Dictionary<string, object> Status(bool settled, int frames)
        {
            var renderer = DebugModBridge.HitboxRenderer;
            var count = -1;
            if (renderer != null)
            {
                Entries.Clear();
                DebugModBridge.HitboxColliders(renderer, Entries);
                count = Entries.Count;
                Entries.Clear();
            }
            var gm = GameManager._instance;
            return new Dictionary<string, object>
            {
                ["show"] = DebugModBridge.ShowHitboxes,
                ["state"] = DebugModBridge.HitboxViewerState,
                ["render"] = renderer != null,
                ["colliders"] = count,
                ["line_width"] = DebugModBridge.HitboxLineWidth,
                ["gameplay"] = gm != null && gm.IsGameplayScene(),
                ["panels"] = DebugModBridge.Panels(),
                ["settled"] = settled,
                ["frames"] = frames,
                ["version"] = DebugModBridge.Version,
            };
        }

        // ---- projection.sample -------------------------------------------------------------------------------------

        private static void Sample(Dictionary<string, object> args, Rpc.Reply reply)
        {
            if (pending != null) { reply.Fail("a projection sample is already pending"); return; }
            var gm = GameManager._instance;
            var gc = gm != null ? gm.gameCams : null;
            var cam = gc != null ? gc.mainCamera : null;
            if (cam == null) cam = Camera.main;
            if (cam == null) { reply.Fail("no main camera"); return; }

            var source = Rpc.Str(args, "source", "auto");
            var dmOn = DebugModBridge.ResolveHitboxes() && DebugModBridge.HitboxRenderer != null;
            bool useDm;
            switch (source)
            {
                case "auto": useDm = dmOn; break;
                case "debugmod":
                    if (!dmOn)
                    {
                        reply.Fail(DebugModBridge.HitboxError ?? "DebugMod's hitbox display is not running (hitbox.show {on: true} in a gameplay scene)");
                        return;
                    }
                    useDm = true;
                    break;
                case "physics": useDm = false; break;
                default: reply.Fail("source must be auto, debugmod or physics"); return;
            }

            var p = new Pending
            {
                Reply = reply,
                DebugMod = useDm,
                Max = Math.Max(1, (int)Rpc.Long(args, "max", DefaultMax)),
                Frame = Time.frameCount,
                Cam = cam,
            };
            pending = p;
            Camera.onPreRender += OnPreRender;
            try
            {
                instance.StartCoroutine(instance.Finish(p));
            }
            catch (Exception)
            {
                Camera.onPreRender -= OnPreRender;
                pending = null;
                throw;
            }
        }

        /// <summary>The render-time half: the main camera's pose here is the one STATE "cam" V/P were captured with
        /// (RenderCapture runs in the same callback, registered earlier).</summary>
        private static void OnPreRender(Camera cam)
        {
            var p = pending;
            if (p == null || p.Rendered || cam != p.Cam || Time.frameCount != p.Frame) return;
            var t0 = Stopwatch.GetTimestamp();
            try
            {
                p.CamInfo = CamInfo(cam, true);
                Collect(p, cam);
                foreach (var c in p.Cols) c.S = ToScreen(cam, c.W);
                p.Rendered = true;
            }
            catch (Exception e)
            {
                // Finish collects again at end of frame without the render-time points.
                p.Cols.Clear();
                p.Candidates = 0;
                p.Truncated = false;
                Core.Plugin.Log.LogWarning("projection.sample (render): " + e.Message);
            }
            p.RenderTicks = Stopwatch.GetTimestamp() - t0;
        }

        private IEnumerator Finish(Pending p)
        {
            yield return Eof;
            Camera.onPreRender -= OnPreRender;
            pending = null;
            var t0 = Stopwatch.GetTimestamp();
            Dictionary<string, object> result;
            try
            {
                result = Build(p);
            }
            catch (Exception e)
            {
                p.Reply.Fail("projection.sample: " + e.GetType().Name + ": " + e.Message);
                yield break;
            }
            result["us"] = new Dictionary<string, object>
            {
                ["render"] = Us(p.RenderTicks),
                ["eof"] = Us(Stopwatch.GetTimestamp() - t0),
            };
            p.Reply.Ok(result);
        }

        private static Dictionary<string, object> Build(Pending p)
        {
            if (p.Cam == null) throw new InvalidOperationException("the main camera was destroyed");
            var dmCam = Camera.main;
            if (dmCam == null) dmCam = p.Cam;
            if (!p.Rendered)
            {
                p.CamInfo = CamInfo(p.Cam, false);
                Collect(p, p.Cam);
            }

            var cols = new List<object>(p.Cols.Count);
            foreach (var col in p.Cols)
            {
                var c = col.C;
                if (c == null) continue;  // destroyed since the render callback
                // DebugMod's draw filter at OnGUI time (ShouldCullCollider with Camera.main); physics: still in view.
                if (!c.isActiveAndEnabled || !Overlaps(dmCam, c, 0f)) continue;
                if (p.DebugMod && c.gameObject.layer == IgnoreRaycastLayer) continue;
                float[] w;
                try
                {
                    w = Outline(c, col.Path, col.Kind);
                }
                catch (ArgumentException)
                {
                    continue;  // a polygon path removed since the render callback
                }
                var moved = 0f;
                for (var i = 0; i < w.Length && i < col.W.Length; i++) moved = Math.Max(moved, Math.Abs(w[i] - col.W[i]));
                if (w.Length != col.W.Length) moved = float.PositiveInfinity;
                var d = new Dictionary<string, object>
                {
                    ["id"] = col.Id,
                    ["path"] = col.Path,
                    ["go"] = c.name,
                    ["type"] = col.Type,
                    ["color"] = col.Type != null ? new[] { col.Color.r, col.Color.g, col.Color.b } : null,
                    ["kind"] = Geometry.KindNames[col.Kind],
                    ["closed"] = col.Kind != Geometry.Edge,
                    ["layer"] = c.gameObject.layer,
                    ["trigger"] = c.isTrigger,
                    ["er"] = col.EdgeRadius,
                    ["r"] = col.Radius,
                    ["w"] = col.W,
                    ["o"] = col.O,
                    ["s"] = col.S,
                    ["e"] = ToScreen(dmCam, w),
                    ["moved"] = moved,
                };
                if (moved > 0f) d["we"] = w;
                cols.Add(d);
            }

            var result = new Dictionary<string, object>
            {
                ["frame"] = p.Frame,
                ["q"] = Core.Qpc.Now(),
                ["source"] = p.DebugMod ? "debugmod" : "physics",
                ["cam"] = p.CamInfo,
                ["dm_cam"] = CamInfo(dmCam, false),
                ["cols"] = cols,
                ["n"] = new Dictionary<string, object>
                {
                    ["candidates"] = p.Candidates,
                    ["cols"] = cols.Count,
                    ["truncated"] = p.Truncated,
                },
            };
            if (Time.frameCount != p.Frame) result["eof_frame"] = Time.frameCount;  // never expected: EOF of the request frame
            result["dm"] = DebugModBridge.ResolveHitboxes()
                ? new Dictionary<string, object>
                {
                    ["show"] = DebugModBridge.ShowHitboxes,
                    ["state"] = DebugModBridge.HitboxViewerState,
                    ["line_width"] = DebugModBridge.HitboxLineWidth,
                    ["version"] = DebugModBridge.Version,
                }
                : null;
            return result;
        }

        // ---- colliders ---------------------------------------------------------------------------------------------

        /// <summary>The candidates for this frame with their outlines, from <paramref name="view"/>'s current pose (render
        /// time when called from the render callback).</summary>
        private static void Collect(Pending p, Camera view)
        {
            p.Cols.Clear();
            p.Candidates = 0;
            p.Truncated = false;
            if (p.DebugMod)
            {
                var renderer = DebugModBridge.HitboxRenderer;
                if (renderer == null) throw new InvalidOperationException("DebugMod's hitbox display stopped");
                Entries.Clear();
                DebugModBridge.HitboxColliders(renderer, Entries);
                foreach (var e in Entries)
                {
                    var c = e.Col;
                    if (c == null || c.gameObject.layer == IgnoreRaycastLayer || !c.isActiveAndEnabled) continue;
                    if (!Overlaps(view, c, CandidateMargin)) continue;
                    p.Candidates++;
                    Add(p, c, e.Type, e.Color);
                }
                Entries.Clear();
            }
            else
            {
                // The z = 0 plane the camera sees (EntityExporter's view test), widened by the candidate margin.
                var dist = -view.transform.position.z;
                if (!(dist > 0.01f)) dist = 10f;
                var a = view.ViewportToWorldPoint(new Vector3(-CandidateMargin, -CandidateMargin, dist));
                var b = view.ViewportToWorldPoint(new Vector3(1f + CandidateMargin, 1f + CandidateMargin, dist));
                foreach (var c in Physics2D.OverlapAreaAll(new Vector2(Mathf.Min(a.x, b.x), Mathf.Min(a.y, b.y)),
                             new Vector2(Mathf.Max(a.x, b.x), Mathf.Max(a.y, b.y))))
                {
                    if (c == null || !c.isActiveAndEnabled) continue;
                    p.Candidates++;
                    Add(p, c, null, default);
                }
            }
        }

        private static void Add(Pending p, Collider2D c, string type, Color color)
        {
            var kind = Geometry.ShapeOf(c);
            var paths = c is PolygonCollider2D poly ? poly.pathCount : 1;
            for (var path = 0; path < paths; path++)
            {
                if (p.Cols.Count >= p.Max)
                {
                    p.Truncated = true;
                    return;
                }
                var w = Outline(c, path, kind);
                if (w.Length == 0) continue;  // an empty polygon path draws nothing
                var o = OracleOutline(c, path, kind, out var radius);
                p.Cols.Add(new Col
                {
                    C = c,
                    Id = c.GetInstanceID(),
                    Path = path,
                    Type = type,
                    Color = color,
                    Kind = kind,
                    Radius = radius,
                    EdgeRadius = c is BoxCollider2D box ? box.edgeRadius : c is EdgeCollider2D edge ? edge.edgeRadius : 0f,
                    W = w,
                    O = o,
                });
            }
        }

        /// <summary>The outline DebugMod draws (HitboxRender.DrawHitbox: transform.TransformPoint(point + offset), cast to
        /// Vector2), world x, y pairs. Box corners TL, TR, BR, BL without edgeRadius; circles as centre and centre + radius
        /// along local x (DebugMod's radius is that distance on screen). Shapes DebugMod does not draw get the ents
        /// outline.</summary>
        private static float[] Outline(Collider2D c, int path, byte kind)
        {
            var m = c.transform.localToWorldMatrix;
            var off = c.offset;
            Points.Clear();
            switch (c)
            {
                case BoxCollider2D box:
                {
                    var h = box.size * 0.5f;
                    Points.Add(new Vector2(-h.x, h.y));
                    Points.Add(h);
                    Points.Add(new Vector2(h.x, -h.y));
                    Points.Add(-h);
                    break;
                }
                case PolygonCollider2D poly:
                    poly.GetPath(path, Points);
                    break;
                case EdgeCollider2D edge:
                    edge.GetPoints(Points);
                    break;
                case CircleCollider2D circle:
                    Points.Add(Vector2.zero);
                    Points.Add(Vector2.right * circle.radius);
                    break;
                default:
                    return OracleOutline(c, path, kind, out _);
            }
            var w = new float[Points.Count * 2];
            for (var i = 0; i < Points.Count; i++)
            {
                var q = m.MultiplyPoint3x4(new Vector3(Points[i].x + off.x, Points[i].y + off.y, 0f));
                w[2 * i] = q.x;
                w[2 * i + 1] = q.y;
            }
            return w;
        }

        /// <summary>The outline exactly as STATE "ents" exports it (EntityExporter.GatherCollider).</summary>
        private static float[] OracleOutline(Collider2D c, int path, byte kind, out float radius)
        {
            radius = 0f;
            var m = c.transform.localToWorldMatrix;
            Scratch.Clear();
            switch (kind)
            {
                case Geometry.Box:
                    Geometry.AppendBox(Scratch, ref m, (BoxCollider2D)c);
                    break;
                case Geometry.Circle:
                    radius = Geometry.AppendCircle(Scratch, ref m, (CircleCollider2D)c);
                    break;
                case Geometry.Capsule:
                    Geometry.AppendCapsule(Scratch, ref m, (CapsuleCollider2D)c);
                    break;
                case Geometry.Edge:
                {
                    var edge = (EdgeCollider2D)c;
                    Points.Clear();
                    edge.GetPoints(Points);
                    Geometry.AppendPoints(Scratch, ref m, edge.offset, Points);
                    break;
                }
                case Geometry.Poly:
                {
                    var poly = (PolygonCollider2D)c;
                    Points.Clear();
                    poly.GetPath(path, Points);
                    Geometry.AppendPoints(Scratch, ref m, poly.offset, Points);
                    break;
                }
                default:
                    Geometry.AppendBounds(Scratch, c);
                    break;
            }
            return Scratch.ToArray();
        }

        /// <summary>DebugMod's HitboxRender.ShouldCullCollider negated: the collider's bounds overlap the viewport (grown by
        /// <paramref name="margin"/>, in viewport units).</summary>
        private static bool Overlaps(Camera cam, Collider2D c, float margin)
        {
            var b = c.bounds;
            var min = cam.WorldToViewportPoint(b.min);
            var max = cam.WorldToViewportPoint(b.max);
            return min.x < 1f + margin && max.x > -margin && min.y < 1f + margin && max.y > -margin;
        }

        private static float[] ToScreen(Camera cam, float[] w)
        {
            var s = new float[w.Length];
            for (var i = 0; i + 1 < w.Length; i += 2)
            {
                var q = cam.WorldToScreenPoint(new Vector3(w[i], w[i + 1], 0f));
                s[i] = q.x;
                s[i + 1] = q.y;
            }
            return s;
        }

        /// <summary>What turns WorldToScreenPoint into image pixels: the pixel rect in the camera's target (a render
        /// texture when rt, e.g. CameraRenderScaled) and the normalized rect that target is shown in on the screen.</summary>
        private static Dictionary<string, object> CamInfo(Camera cam, bool renderTime)
        {
            var rt = cam.targetTexture;
            var pr = cam.pixelRect;
            var r = cam.rect;
            var v = cam.worldToCameraMatrix;
            var proj = cam.projectionMatrix;
            return new Dictionary<string, object>
            {
                ["id"] = cam.GetInstanceID(),
                ["name"] = cam.name,
                ["is_main"] = cam == Camera.main,
                ["render"] = renderTime,
                ["pixel_rect"] = new[] { pr.x, pr.y, pr.width, pr.height },
                ["rect"] = new[] { r.x, r.y, r.width, r.height },
                ["target"] = rt != null ? new[] { (float)rt.width, (float)rt.height } : new[] { (float)Screen.width, (float)Screen.height },
                ["rt"] = rt != null,
                ["screen"] = new[] { (float)Screen.width, (float)Screen.height },
                ["pos"] = cam.transform.position,
                ["V"] = ColumnMajor(v),
                ["P"] = ColumnMajor(proj),
            };
        }

        /// <summary>Same layout as STATE "cam" V/P (CamView.WriteMatrix).</summary>
        private static float[] ColumnMajor(Matrix4x4 m) => new[]
        {
            m.m00, m.m10, m.m20, m.m30, m.m01, m.m11, m.m21, m.m31,
            m.m02, m.m12, m.m22, m.m32, m.m03, m.m13, m.m23, m.m33,
        };

        private static float Us(long ticks) => (float)(ticks * 1_000_000.0 / Stopwatch.Frequency);
    }
}
