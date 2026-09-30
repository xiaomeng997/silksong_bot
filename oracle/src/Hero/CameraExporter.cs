using System;
using System.Diagnostics;
using HarmonyLib;
using SsOracle.Export;
using SsOracle.Ipc;
using UnityEngine;

namespace SsOracle.Hero
{
    /// <summary>
    /// Camera matrices captured at the moment each game camera renders (Camera.onPreRender, built-in pipeline).
    /// STATE is sampled at WaitForEndOfFrame, after rendering, and by then CameraShakeManager has already removed
    /// the shake offset it added in OnPreCull (it restores localPosition in OnPostRender), so the end-of-frame
    /// worldToCameraMatrix is not the one that produced the image. The render-time V/P are what the projector
    /// (DESIGN §3.1.3) and the HUD rectangles need. Only GameCameras.mainCamera and .hudCamera are captured.
    ///
    /// The callback runs for every camera render, outside FrameExporter's measured window, so it returns at once
    /// while no brain is connected (STATE is not built then either) and sums its own per-frame cost, which
    /// CameraExporter reports as cam["cb_us"] (C14 accounting).
    /// </summary>
    internal static class RenderCapture
    {
        internal struct Snap
        {
            public long Frame;
            public int CamId;
            public Matrix4x4 V, P;
            public Vector3 Pos;
        }

        public static Snap Main, Hud;
        private static bool installed;
        private static int errors;

        /// <summary>Stopwatch ticks spent in OnPreRender during frame CostFrame (all cameras).</summary>
        private static long costTicks, costFrame = -1;

        public static void Install()
        {
            if (installed) return;
            Camera.onPreRender += OnPreRender;
            installed = true;
        }

        /// <summary>Main-thread microseconds spent in the capture callbacks of frame `frame` (0 if none ran).</summary>
        public static float CostUs(long frame) =>
            costFrame == frame ? (float)(costTicks * 1_000_000.0 / Stopwatch.Frequency) : 0f;

        private static void OnPreRender(Camera cam)
        {
            var server = Ipc.FramedServer.Instance;
            if (server == null || !server.Connected) return;
            var t0 = Stopwatch.GetTimestamp();
            try
            {
                var gm = GameManager._instance;
                if (gm == null) return;
                var gc = gm.gameCams;
                if (gc == null) return;
                if (cam == gc.mainCamera) Take(cam, ref Main);
                else if (cam == gc.hudCamera) Take(cam, ref Hud);
            }
            catch (Exception e)
            {
                if (errors++ < 5) Core.Plugin.Log.LogWarning("render capture: " + e.Message);
            }
            finally
            {
                long frame = Time.frameCount;
                if (costFrame != frame)
                {
                    costFrame = frame;
                    costTicks = 0;
                }
                costTicks += Stopwatch.GetTimestamp() - t0;
            }
        }

        private static void Take(Camera cam, ref Snap s)
        {
            s.Frame = Time.frameCount;
            s.CamId = cam.GetInstanceID();
            s.V = cam.worldToCameraMatrix;
            s.P = cam.projectionMatrix;
            s.Pos = cam.transform.position;
        }
    }

    /// <summary>
    /// A camera's projection for this frame: world point -> image pixel with the origin at the TOP-LEFT of the
    /// game window's client area (the capture convention). Pixels are computed from the normalized viewport
    /// rect times the screen size rather than from pixelRect, because the main camera may render into a
    /// scaled RenderTexture (CameraRenderScaled) that is then blitted over the whole screen.
    /// </summary>
    internal struct CamView
    {
        public bool Valid;
        public bool FromRender;
        public Matrix4x4 V, P, VP;
        public Vector3 Pos;
        public Rect Rect;
        public float ScreenW, ScreenH;

        public static CamView Of(Camera cam, ref RenderCapture.Snap snap, long frame)
        {
            var v = new CamView { Valid = cam != null };
            if (!v.Valid) return v;
            v.FromRender = snap.Frame == frame && snap.CamId == cam.GetInstanceID();
            if (v.FromRender)
            {
                v.V = snap.V;
                v.P = snap.P;
                v.Pos = snap.Pos;
            }
            else
            {
                v.V = cam.worldToCameraMatrix;
                v.P = cam.projectionMatrix;
                v.Pos = cam.transform.position;
            }
            v.VP = v.P * v.V;
            v.Rect = cam.rect;
            v.ScreenW = Screen.width;
            v.ScreenH = Screen.height;
            return v;
        }

        /// <summary>False when the point is behind a perspective camera.</summary>
        public bool ToImage(Vector3 world, out float x, out float y)
        {
            var c = VP * new Vector4(world.x, world.y, world.z, 1f);
            if (c.w <= 1e-6f) { x = y = 0f; return false; }
            var u = (c.x / c.w + 1f) * 0.5f;
            var t = (c.y / c.w + 1f) * 0.5f;
            x = (Rect.x + u * Rect.width) * ScreenW;
            y = ScreenH - (Rect.y + t * Rect.height) * ScreenH;
            return true;
        }

        /// <summary>Image-space bounding rectangle [x0, y0, x1, y1] (top-left origin) of a world AABB.</summary>
        public bool RectOf(Bounds b, out float x0, out float y0, out float x1, out float y1)
        {
            x0 = y0 = float.MaxValue;
            x1 = y1 = float.MinValue;
            var min = b.min;
            var max = b.max;
            for (var i = 0; i < 8; i++)
            {
                var p = new Vector3((i & 1) == 0 ? min.x : max.x, (i & 2) == 0 ? min.y : max.y, (i & 4) == 0 ? min.z : max.z);
                if (!ToImage(p, out var x, out var y)) return false;
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
                if (y < y0) y0 = y;
                if (y > y1) y1 = y;
            }
            return true;
        }

        public void WriteRect(MsgPackWriter w, Bounds b)
        {
            if (!RectOf(b, out var x0, out var y0, out var x1, out var y1)) { w.Nil(); return; }
            w.ArrayHeader(4); w.Float(x0); w.Float(y0); w.Float(x1); w.Float(y1);
        }

        public void WritePoint(MsgPackWriter w, Vector3 world)
        {
            if (!ToImage(world, out var x, out var y)) { w.Nil(); return; }
            w.Vec2(x, y);
        }

        /// <summary>Unity Matrix4x4 as 16 floats in COLUMN-MAJOR order (m00, m10, m20, m30, m01, ...),
        /// i.e. numpy.array(a).reshape(4, 4).T is the matrix.</summary>
        public static void WriteMatrix(MsgPackWriter w, in Matrix4x4 m)
        {
            w.ArrayHeader(16);
            w.Float(m.m00); w.Float(m.m10); w.Float(m.m20); w.Float(m.m30);
            w.Float(m.m01); w.Float(m.m11); w.Float(m.m21); w.Float(m.m31);
            w.Float(m.m02); w.Float(m.m12); w.Float(m.m22); w.Float(m.m32);
            w.Float(m.m03); w.Float(m.m13); w.Float(m.m23); w.Float(m.m33);
        }

        public static void WriteRectXywh(MsgPackWriter w, Rect r)
        {
            w.ArrayHeader(4); w.Float(r.x); w.Float(r.y); w.Float(r.width); w.Float(r.height);
        }
    }

    /// <summary>
    /// STATE "cam" (DESIGN §3.1.2 camera; m0 §3.1 camera and §2.7 camera rows). The camera is
    /// GameManager._instance.gameCams.mainCamera (Camera.main as fallback). "V"/"P" are the render-time matrices
    /// when "src" == 1 (see RenderCapture), otherwise the end-of-frame ones. "cb_us" is this frame's main-thread
    /// cost of the RenderCapture callbacks (all cameras), which cost_us/cost_ex do not include. Projection of a world point:
    /// clip = P*V*[x, y, z, 1]; ndc = clip.xyz / clip.w; image_x = (rect.x + (ndc.x+1)/2*rect.w)*screen.w;
    /// image_y = screen.h - (rect.y + (ndc.y+1)/2*rect.h)*screen.h (top-left origin).
    /// </summary>
    internal sealed class CameraExporter : IExporter
    {
        public string Key => "cam";

        private static readonly AccessTools.FieldRef<ForceCameraAspect, float> FovOffset =
            Refs.Field<ForceCameraAspect, float>("fovOffset");
        private static readonly AccessTools.FieldRef<ForceCameraAspect, float> ExtraFovOffset =
            Refs.Field<ForceCameraAspect, float>("extraFovOffset");

        public void Write(MsgPackWriter w, FrameContext ctx)
        {
            var gm = ctx.Gm;
            var gc = gm != null ? gm.gameCams : null;
            var cam = gc != null ? gc.mainCamera : null;
            if (cam == null) cam = ctx.MainCamera;
            if (cam == null) { w.Nil(); return; }

            var view = CamView.Of(cam, ref RenderCapture.Main, ctx.Frame);
            var eofPos = cam.transform.position;
            var ctrl = gm != null ? gm.cameraCtrl : null;
            if (ctrl == null && gc != null) ctrl = gc.cameraController;
            var fca = gc != null ? gc.forceCameraAspect : null;
            var rt = cam.targetTexture;

            var at = w.BeginMap16();
            var n = 0;
            K(w, "src", ref n); w.Int(view.FromRender ? 1 : 0);
            K(w, "cb_us", ref n); w.Float(RenderCapture.CostUs(ctx.Frame));
            K(w, "V", ref n); CamView.WriteMatrix(w, view.V);
            K(w, "P", ref n); CamView.WriteMatrix(w, view.P);
            K(w, "pos", ref n); w.Vec3(view.Pos.x, view.Pos.y, view.Pos.z);
            K(w, "pos_eof", ref n); w.Vec3(eofPos.x, eofPos.y, eofPos.z);
            K(w, "shake", ref n); w.Vec2(view.Pos.x - eofPos.x, view.Pos.y - eofPos.y);
            K(w, "rect", ref n); CamView.WriteRectXywh(w, view.Rect);
            K(w, "pixel_rect", ref n); CamView.WriteRectXywh(w, cam.pixelRect);
            K(w, "rt", ref n); if (rt != null) w.Vec2(rt.width, rt.height); else w.Nil();
            K(w, "screen", ref n); w.Vec2(view.ScreenW, view.ScreenH);
            K(w, "fov", ref n); w.Float(cam.fieldOfView);
            K(w, "ortho", ref n); w.Bool(cam.orthographic);
            K(w, "ortho_size", ref n); w.Float(cam.orthographicSize);
            K(w, "is_camera_main", ref n); w.Bool(ctx.MainCamera != null && ctx.MainCamera == cam);
            if (ctrl != null)
            {
                K(w, "mode", ref n); w.Int((int)ctrl.mode);
                K(w, "look_offset", ref n); w.Float(ctrl.lookOffset);
                K(w, "at_bounds", ref n); w.Bool(ctrl.atSceneBounds);
                K(w, "limits", ref n); w.Vec2(ctrl.xLimit, ctrl.yLimit);
                K(w, "scene_size", ref n); w.Vec2(ctrl.sceneWidth, ctrl.sceneHeight);
                K(w, "lock", ref n);
                w.ArrayHeader(4); w.Float(ctrl.xLockMin); w.Float(ctrl.xLockMax); w.Float(ctrl.yLockMin); w.Float(ctrl.yLockMax);
            }
            K(w, "aspect", ref n); w.Float(ForceCameraAspect.CurrentViewportAspect);
            K(w, "fca_fov", ref n); w.Float(ForceCameraAspect.CurrentMainCamFov);
            K(w, "height_mult", ref n); w.Float(ForceCameraAspect.CurrentMainCamHeightMult);
            if (fca != null && FovOffset != null && ExtraFovOffset != null)
            {
                K(w, "fov_offset", ref n); w.Vec2(FovOffset(fca), ExtraFovOffset(fca));
            }
            w.EndMap16(at, n);
        }

        private static void K(MsgPackWriter w, string key, ref int n)
        {
            w.Key(key);
            n++;
        }
    }
}
