using System.Collections.Generic;
using UnityEngine;

namespace SsOracle.Export
{
    /// <summary>
    /// One section of the per-frame STATE message (DESIGN §3.1.2 FrameLabel). FrameExporter calls every
    /// registered exporter once per frame at end-of-frame, in registration order. Each exporter writes exactly one
    /// value (usually a map, or nil when not applicable) under its Key. Never cache Unity object references across
    /// frames: GameManager, the hero and PlayerData are rebuilt on Save & Quit (m0:N42); use FrameContext.
    /// </summary>
    internal interface IExporter
    {
        /// <summary>Short, stable key in the STATE map (e.g. "hero", "ents", "cam").</summary>
        string Key { get; }

        /// <summary>Write exactly one msgpack value. Must not throw for missing objects: write nil instead.</summary>
        void Write(Ipc.MsgPackWriter w, FrameContext ctx);
    }

    /// <summary>References resolved once per frame for all exporters (may be null in menus and during loads).</summary>
    internal sealed class FrameContext
    {
        public long Frame;
        public long QpcEndOfFrame;
        public GameManager Gm;
        public PlayerData Pd;
        public HeroController Hero;
        public Camera MainCamera;

        /// <summary>Events recorded by hooks since the previous STATE (EventTap appends, FrameExporter drains).</summary>
        public readonly List<FrameEvent> Events = new List<FrameEvent>();
    }

    /// <summary>A discrete event captured by a Harmony hook during the frame (DESIGN §3.1.1 EventTap).</summary>
    internal struct FrameEvent
    {
        public string Kind;            // e.g. "damage", "hp_change", "state", "freeze", "scene", "save", "die"
        public long Frame;
        public long Qpc;
        public Dictionary<string, object> Data;
    }
}
