using System;
using System.Collections.Generic;
using System.Reflection;
using HarmonyLib;
using HutongGames.PlayMaker;
using SsOracle.Export;
using SsOracle.Ipc;
using UnityEngine;

namespace SsOracle.Hero
{
    /// <summary>
    /// STATE "hud" (DESIGN §3.1.2 hud[], §3.3.2 HUD reading; m0 §2.7 HUD row, §3.2 HudProbe): where the HUD
    /// elements are on screen, projected with the HUD camera's render-time matrices, plus the visibility flags.
    /// All rectangles are image pixels [x0, y0, x1, y1] with the origin at the top-left of the client area.
    ///
    /// The HUD is not uGUI: masks are tk2d sprites driven by one "health_display" FSM each (FsmInt "Health
    /// Number"), found under GameCameras.hudCanvasSlideOut (the "Hud Canvas"); the silk spool is SilkSpool.Instance
    /// whose chunks sit at chunkParent-local x = firstChunk_x + i*chunkDistance_x. Object lookups are cached and
    /// rebuilt only when the HUD root changes, the scene changes, maxHealth/healthBlue change (each followed by one
    /// delayed re-check) or a cached object dies, so the per-frame cost is a few native reads per element.
    /// </summary>
    internal sealed class HudProbe : IExporter
    {
        public string Key => "hud";

        private const int MaxSlots = 40;
        private const int RetryFrames = 120;
        private const int MinRebuildFrames = 10;
        private const int FollowUpFrames = 45;

        private static readonly AccessTools.FieldRef<SilkSpool, List<SilkChunk>> SilkChunks =
            Refs.Field<SilkSpool, List<SilkChunk>>("silkChunks");
        private static readonly AccessTools.FieldRef<SilkSpool, Transform> ChunkParent =
            Refs.Field<SilkSpool, Transform>("chunkParent");
        private static readonly AccessTools.FieldRef<SilkSpool, GameObject> SpoolParent =
            Refs.Field<SilkSpool, GameObject>("spoolParent");
        private static readonly AccessTools.FieldRef<SilkSpool, GameObject> ActiveParent =
            Refs.Field<SilkSpool, GameObject>("activeParent");
        private static readonly AccessTools.FieldRef<SilkSpool, GameObject> BrokenParent =
            Refs.Field<SilkSpool, GameObject>("brokenParent");
        private static readonly AccessTools.FieldRef<SilkSpool, GameObject> CursedParent =
            Refs.Field<SilkSpool, GameObject>("cursedParent");
        private static readonly AccessTools.FieldRef<SilkSpool, GameObject> BindNotch =
            Refs.Field<SilkSpool, GameObject>("bindNotch");
        private static readonly AccessTools.FieldRef<RadialHudIcon, SpriteRenderer> IconRenderer =
            Refs.Field<RadialHudIcon, SpriteRenderer>("icon");
        private static readonly AccessTools.FieldRef<ToolHudIcon, AttackToolBinding> IconBinding =
            Refs.Field<ToolHudIcon, AttackToolBinding>("binding");
        private static readonly AccessTools.FieldRef<BlueHealth, bool> BlueIsActive =
            Refs.Field<BlueHealth, bool>("isActive");
        private static readonly FieldInfo HudCanvasInstance = AccessTools.Field(typeof(HudCanvas), "instance");

        private sealed class MaskSlot
        {
            public PlayMakerFSM Fsm;
            public GameObject Go;
            public Renderer R;
            public bool ChildR;
            public FsmInt Number;
        }

        private sealed class ToolSlot
        {
            public ToolHudIcon Icon;
            public GameObject Go;
            public SpriteRenderer R;
            public int Binding;
            public ToolItem LastTool;
            public string LastToolName;
        }

        private sealed class BlueSlot
        {
            public BlueHealth B;
            public GameObject Go;
            public Renderer R;
            public bool ChildR;
        }

        private readonly List<MaskSlot> masks = new List<MaskSlot>();
        private readonly List<ToolSlot> tools = new List<ToolSlot>();
        private readonly List<BlueSlot> blues = new List<BlueSlot>();
        private readonly List<Renderer> bindOrbRenderers = new List<Renderer>();
        private GameObject bindOrb;

        private PlayMakerFSM rootFsm;
        private Transform root;
        private string builtScene;
        private int builtMaxHealth = int.MinValue, builtBlue = int.MinValue;
        private bool invalid = true;
        private long nextRetry, lastRebuild = long.MinValue / 2;

        private SilkChunk sizedChunk;
        private Renderer sizedChunkRenderer;
        private int errorsLogged;

        public void Write(MsgPackWriter w, FrameContext ctx)
        {
            var gm = ctx.Gm;
            var gc = gm != null ? gm.gameCams : null;
            if (gc == null) { w.Nil(); return; }
            var pd = ctx.Pd;
            // Everything that can throw runs before the first byte is written: a half-written value would make
            // FrameExporter disable this section for good.
            try
            {
                EnsureCache(gm, gc, pd, ctx.Frame);
            }
            catch (Exception e)
            {
                LogOnce(e);
                ClearCache();
                nextRetry = ctx.Frame + RetryFrames;
            }

            var hudCam = gc.hudCamera;
            var view = hudCam != null ? CamView.Of(hudCam, ref RenderCapture.Hud, ctx.Frame) : default;
            var canvasVisible = HudCanvas.IsVisible;
            bool camsVisible;
            try { camsVisible = gc.IsHudVisible; }
            catch (Exception e) { LogOnce(e); camsVisible = false; }

            w.MapHeader(8);
            w.Key("hidden"); w.Bool(!canvasVisible || !camsVisible || HudGlobalHide.IsHidden);
            w.Key("vis");
            w.MapHeader(4);
            w.Key("canvas"); w.Bool(canvasVisible);
            w.Key("cams"); w.Bool(camsVisible);
            w.Key("global_hide"); w.Bool(HudGlobalHide.IsHidden);
            w.Key("reduced"); w.Bool(HudGlobalHide.IsReduced);
            w.Key("cam"); WriteCam(w, hudCam, view);
            w.Key("masks"); WriteMasks(w, view);
            w.Key("blue"); WriteBlue(w, view);
            w.Key("spool"); WriteSpool(w, gc, pd, ctx.Hero, view);
            w.Key("bind_orb"); WriteBindOrb(w, view);
            w.Key("tools"); WriteTools(w, view);
        }

        private static void WriteCam(MsgPackWriter w, Camera cam, CamView view)
        {
            if (!view.Valid) { w.Nil(); return; }
            w.MapHeader(5);
            w.Key("src"); w.Int(view.FromRender ? 1 : 0);
            w.Key("V"); CamView.WriteMatrix(w, view.V);
            w.Key("P"); CamView.WriteMatrix(w, view.P);
            w.Key("rect"); CamView.WriteRectXywh(w, view.Rect);
            w.Key("ortho_size"); w.Float(cam.orthographicSize);
        }

        /// <summary>Per mask: [health_number, active, fsm_state, rect|nil], in Health Number order at cache time.</summary>
        private void WriteMasks(MsgPackWriter w, CamView view)
        {
            w.ArrayHeader(masks.Count);
            foreach (var m in masks)
            {
                if (m.Go == null || m.Fsm == null) { invalid = true; w.Nil(); continue; }
                bool active;
                int number;
                string state;
                try
                {
                    active = m.Go.activeInHierarchy;
                    number = m.Number != null ? m.Number.Value : -1;
                    state = m.Fsm.ActiveStateName;
                }
                catch (Exception e) { LogOnce(e); invalid = true; w.Nil(); continue; }
                w.ArrayHeader(4);
                w.Int(number);
                w.Bool(active);
                w.Str(state);
                WriteRenderer(w, view, active && ChildShown(m.ChildR, m.R), m.R);
            }
        }

        /// <summary>
        /// Lifeblood masks (BlueHealth components under the HUD): [shown, live|nil, rect|nil]. "shown" is
        /// activeInHierarchy; "live" is BlueHealth.isActive, the flag the game counts in BlueHealth.ActiveCount
        /// (MarkActive/MarkInactive), which can differ from "shown" while the FSM animates a mask in or out.
        /// </summary>
        private void WriteBlue(MsgPackWriter w, CamView view)
        {
            w.ArrayHeader(blues.Count);
            foreach (var b in blues)
            {
                if (b.Go == null || b.B == null) { invalid = true; w.Nil(); continue; }
                var active = b.Go.activeInHierarchy;
                w.ArrayHeader(3);
                w.Bool(active);
                if (BlueIsActive != null) w.Bool(BlueIsActive(b.B)); else w.Nil();
                WriteRenderer(w, view, active && ChildShown(b.ChildR, b.R), b.R);
            }
        }

        /// <summary>A renderer found below the element (ElementSprite fallback) must itself be active to have bounds.</summary>
        private static bool ChildShown(bool child, Renderer r) => !child || r == null || r.gameObject.activeInHierarchy;

        private static void WriteRenderer(MsgPackWriter w, CamView view, bool active, Renderer r)
        {
            if (!active || !view.Valid || r == null || !r.enabled) { w.Nil(); return; }
            view.WriteRect(w, r.bounds);
        }

        /// <summary>
        /// Silk spool: "parts" bits (1 spool shown, 2 normal, 4 broken, 8 cursed parent active), "slots" = image
        /// centres of chunk positions 0..CurrentSilkMax-1, "pitch" = px between slots, "chunks" = centres of the
        /// chunks currently shown (one per silk, regen chunks included), "chunk_rect" = rect of the first chunk,
        /// "notch" = the bind-cost notch centre. Without a hero (menus, loads, Save &amp; Quit) the slot count is
        /// CurrentSilkMaxBasic, because CurrentSilkMax would search for the tool manager and the hero (SafeReads).
        /// </summary>
        private void WriteSpool(MsgPackWriter w, GameCameras gc, PlayerData pd, HeroController hero, CamView view)
        {
            var sp = SilkSpool.Instance;
            if (sp == null) sp = gc.silkSpool;
            if (sp == null || !view.Valid) { w.Nil(); return; }

            uint parts = 0;
            if (Active(Get(SpoolParent, sp))) parts |= 1;
            if (Active(Get(ActiveParent, sp))) parts |= 2;
            if (Active(Get(BrokenParent, sp))) parts |= 4;
            if (Active(Get(CursedParent, sp))) parts |= 8;

            var slotCount = 9;
            if (pd != null)
            {
                try
                {
                    if (!SafeReads.TrySilkMax(pd, hero, out slotCount)) slotCount = pd.CurrentSilkMaxBasic;
                    slotCount = Mathf.Clamp(slotCount, 0, MaxSlots);
                }
                catch (Exception e) { LogOnce(e); slotCount = 9; }
            }

            w.MapHeader(6);
            w.Key("parts"); w.UInt(parts);
            var cp = ChunkParent != null ? ChunkParent(sp) : null;
            w.Key("slots");
            if (cp != null)
            {
                var m = cp.localToWorldMatrix;
                w.ArrayHeader(slotCount);
                for (var i = 0; i < slotCount; i++)
                    view.WritePoint(w, m.MultiplyPoint3x4(new Vector3(sp.firstChunk_x + sp.chunkDistance_x * i, 0f, 0f)));
                w.Key("pitch");
                var a = m.MultiplyPoint3x4(new Vector3(sp.firstChunk_x, 0f, 0f));
                var b = m.MultiplyPoint3x4(new Vector3(sp.firstChunk_x + sp.chunkDistance_x, 0f, 0f));
                if (view.ToImage(a, out var ax, out var ay) && view.ToImage(b, out var bx, out var by))
                    w.Float(Mathf.Sqrt((bx - ax) * (bx - ax) + (by - ay) * (by - ay)));
                else w.Nil();
            }
            else
            {
                w.Nil();
                w.Key("pitch"); w.Nil();
            }

            var chunks = SilkChunks != null ? SilkChunks(sp) : null;
            var shown = chunks != null ? Mathf.Min(chunks.Count, MaxSlots) : 0;
            w.Key("chunks");
            w.ArrayHeader(shown);
            SilkChunk first = null;
            for (var i = 0; i < shown; i++)
            {
                var c = chunks[i];
                if (c == null) { w.Nil(); continue; }
                if (first == null) first = c;
                view.WritePoint(w, c.transform.position);
            }
            w.Key("chunk_rect");
            if (first != null)
            {
                if (!ReferenceEquals(first, sizedChunk))
                {
                    sizedChunk = first;
                    sizedChunkRenderer = FirstSprite(first);
                }
                WriteRenderer(w, view, first.gameObject.activeInHierarchy, sizedChunkRenderer);
            }
            else w.Nil();
            w.Key("notch");
            var notch = Get(BindNotch, sp);
            if (Active(notch)) view.WritePoint(w, notch.transform.position);
            else w.Nil();
        }

        private static bool Active(GameObject go) => go != null && go.activeInHierarchy;

        private static GameObject Get(AccessTools.FieldRef<SilkSpool, GameObject> field, SilkSpool sp) =>
            field != null ? field(sp) : null;

        /// <summary>Union of the enabled renderers of the crest/bind orb frame (BindOrbHudFrame).</summary>
        private void WriteBindOrb(MsgPackWriter w, CamView view)
        {
            if (bindOrb == null || !view.Valid || !bindOrb.activeInHierarchy) { w.Nil(); return; }
            var any = false;
            var u = default(Bounds);
            foreach (var r in bindOrbRenderers)
            {
                if (r == null || !r.enabled || !r.gameObject.activeInHierarchy) continue;
                if (!any) { u = r.bounds; any = true; }
                else u.Encapsulate(r.bounds);
            }
            if (any) view.WriteRect(w, u);
            else w.Nil();
        }

        /// <summary>Per ToolHudIcon: [binding (0 Neutral, 1 Up, 2 Down), tool name|nil, active, icon rect|nil].</summary>
        private void WriteTools(MsgPackWriter w, CamView view)
        {
            w.ArrayHeader(tools.Count);
            foreach (var t in tools)
            {
                if (t.Icon == null || t.Go == null) { invalid = true; w.Nil(); continue; }
                var tool = t.Icon.CurrentTool;
                if (!ReferenceEquals(tool, t.LastTool))
                {
                    t.LastTool = tool;
                    t.LastToolName = tool != null ? tool.name : null;
                }
                var active = t.Go.activeInHierarchy;
                w.ArrayHeader(4);
                w.Int(t.Binding);
                w.Str(tool != null ? t.LastToolName : null);
                w.Bool(active);
                WriteRenderer(w, view, active, t.R);
            }
        }

        /// <summary>
        /// Rebuild on a new HUD root or scene, on maxHealth changes and on healthBlue rising above what was seen
        /// (masks may be spawned), at most every MinRebuildFrames when a cached object died (Save &amp; Quit
        /// teardown), and every RetryFrames while the HUD has no masks yet (menus, loads). A structural trigger
        /// fires in the frame PlayerData changes, but the HUD FSMs may spawn or reparent the new mask or lifeblood
        /// object a few frames later while the old objects stay alive (nothing would mark the cache invalid), so
        /// every structural rebuild schedules one more, FollowUpFrames later.
        /// </summary>
        private void EnsureCache(GameManager gm, GameCameras gc, PlayerData pd, long frame)
        {
            var structural = !ReferenceEquals(gc.hudCanvasSlideOut, rootFsm)
                             || !ReferenceEquals(gm.sceneName, builtScene)
                             || (pd != null && (pd.maxHealth != builtMaxHealth || pd.healthBlue > builtBlue));
            var due = (invalid && frame >= lastRebuild + MinRebuildFrames) || frame >= nextRetry;
            if (!structural && !due) return;
            Rebuild(gm, gc, pd, frame, structural);
        }

        private void ClearCache()
        {
            masks.Clear();
            tools.Clear();
            blues.Clear();
            bindOrbRenderers.Clear();
            bindOrb = null;
            sizedChunk = null;
            sizedChunkRenderer = null;
        }

        private void LogOnce(Exception e)
        {
            if (errorsLogged++ < 5) Core.Plugin.Log.LogWarning("hud probe: " + e.GetType().Name + ": " + e.Message);
        }

        private void Rebuild(GameManager gm, GameCameras gc, PlayerData pd, long frame, bool structural)
        {
            ClearCache();
            invalid = false;
            lastRebuild = frame;
            rootFsm = gc.hudCanvasSlideOut;
            builtScene = gm.sceneName;
            builtMaxHealth = pd != null ? pd.maxHealth : int.MinValue;
            builtBlue = pd != null ? Math.Max(pd.healthBlue, 0) : int.MinValue;
            root = FindRoot(gc);
            if (root == null) { nextRetry = frame + RetryFrames; return; }

            foreach (var f in root.GetComponentsInChildren<PlayMakerFSM>(true))
            {
                if (f.FsmName != "health_display") continue;
                masks.Add(new MaskSlot
                {
                    Fsm = f,
                    Go = f.gameObject,
                    R = ElementSprite(f, out var child),
                    ChildR = child,
                    Number = f.FsmVariables.FindFsmInt("Health Number"),
                });
            }
            masks.Sort((a, b) => (a.Number != null ? a.Number.Value : int.MaxValue).CompareTo(b.Number != null ? b.Number.Value : int.MaxValue));

            foreach (var icon in root.GetComponentsInChildren<ToolHudIcon>(true))
                tools.Add(new ToolSlot
                {
                    Icon = icon,
                    Go = icon.gameObject,
                    R = IconRenderer != null ? IconRenderer(icon) : null,
                    Binding = IconBinding != null ? (int)IconBinding(icon) : -1,
                });

            foreach (var b in root.GetComponentsInChildren<BlueHealth>(true))
                blues.Add(new BlueSlot { B = b, Go = b.gameObject, R = ElementSprite(b, out var child), ChildR = child });

            var orb = root.GetComponentInChildren<BindOrbHudFrame>(true);
            if (orb != null)
            {
                bindOrb = orb.gameObject;
                foreach (var r in orb.GetComponentsInChildren<Renderer>(true))
                    if (IsSprite(r) && bindOrbRenderers.Count < 32) bindOrbRenderers.Add(r);
            }

            // Menus have a HUD root but may have no masks yet: retry periodically, not every frame. After a
            // structural trigger, look once more when late-spawned HUD objects have appeared (see EnsureCache).
            nextRetry = masks.Count == 0 ? frame + RetryFrames
                      : structural ? frame + FollowUpFrames
                      : long.MaxValue;
        }

        /// <summary>Sprites only: particle/trail renderers have bounds unrelated to the drawn HUD element.</summary>
        private static bool IsSprite(Renderer r) => r is MeshRenderer || r is SpriteRenderer;

        private static Renderer OwnSprite(Component c)
        {
            Renderer r = c.GetComponent<MeshRenderer>();
            if (r == null) r = c.GetComponent<SpriteRenderer>();
            return r;
        }

        /// <summary>
        /// The sprite that draws a mask or lifeblood element: its own MeshRenderer/SpriteRenderer, else the first one
        /// below it (inactive children included, since the element may be hidden at rebuild time). Skips the
        /// HealthSpecialHealIndicator overlays that sit under each mask with their renderer disabled by default.
        /// </summary>
        private static Renderer ElementSprite(Component c, out bool child)
        {
            child = false;
            var own = OwnSprite(c);
            if (own != null) return own;
            foreach (var r in c.GetComponentsInChildren<Renderer>(true))
                if (IsSprite(r) && r.GetComponent<HealthSpecialHealIndicator>() == null)
                {
                    child = true;
                    return r;
                }
            return null;
        }

        private static Renderer FirstSprite(Component c)
        {
            foreach (var r in c.GetComponentsInChildren<Renderer>())
                if (IsSprite(r)) return r;
            return null;
        }

        private static Transform FindRoot(GameCameras gc)
        {
            if (gc.hudCanvasSlideOut != null) return gc.hudCanvasSlideOut.transform;
            var hc = HudCanvasInstance?.GetValue(null) as HudCanvas;
            return hc != null ? hc.transform : null;
        }

        /// <summary>
        /// RPC "hud.dump" {depth=4, max=400}: the HUD hierarchy with components and image rects, so the element
        /// list can be checked in game (M1 integration) without a debugger. Allocates; never per frame.
        /// </summary>
        public static object Dump(Dictionary<string, object> args)
        {
            var depth = (int)Rpc.Long(args, "depth", 4);
            var max = (int)Rpc.Long(args, "max", 400);
            var gm = GameManager._instance;
            var gc = gm != null ? gm.gameCams : null;
            if (gc == null) throw new InvalidOperationException("no GameManager/GameCameras");
            var root = FindRoot(gc);
            if (root == null) throw new InvalidOperationException("no HUD root");
            var view = gc.hudCamera != null ? CamView.Of(gc.hudCamera, ref RenderCapture.Hud, Time.frameCount) : default;
            var nodes = new List<object>();
            Walk(root, root.name, 0, depth, max, view, nodes);
            return new Dictionary<string, object>
            {
                ["root"] = root.name,
                ["screen"] = new[] { Screen.width, Screen.height },
                ["truncated"] = nodes.Count >= max,
                ["nodes"] = nodes,
            };
        }

        private static void Walk(Transform t, string path, int level, int depth, int max, CamView view, List<object> nodes)
        {
            if (nodes.Count >= max) return;
            var comps = new List<string>();
            foreach (var c in t.GetComponents<Component>())
            {
                if (c == null || c is Transform) continue;
                comps.Add(c is PlayMakerFSM f ? "PlayMakerFSM:" + f.FsmName + "@" + f.ActiveStateName : c.GetType().Name);
            }
            var node = new Dictionary<string, object>
            {
                ["path"] = path,
                ["active"] = t.gameObject.activeInHierarchy,
                ["comps"] = comps,
            };
            var r = t.GetComponent<Renderer>();
            if (r != null && view.Valid && view.RectOf(r.bounds, out var x0, out var y0, out var x1, out var y1))
            {
                node["rect"] = new[] { x0, y0, x1, y1 };
                node["enabled"] = r.enabled;
            }
            nodes.Add(node);
            if (level >= depth) return;
            for (var i = 0; i < t.childCount; i++)
            {
                var ch = t.GetChild(i);
                Walk(ch, path + "/" + ch.name, level + 1, depth, max, view, nodes);
            }
        }
    }
}
