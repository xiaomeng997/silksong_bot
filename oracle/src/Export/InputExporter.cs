namespace SsOracle.Export
{
    /// <summary>
    /// "input": what the game's action layer saw this frame (DESIGN §3.1.2 input), whoever pressed it: the
    /// oracle's injected keys, or a person on keyboard or gamepad in human mode (D12). Buttons use the ACTION
    /// bit order (KeyboardInjector.ButtonNames); the analog move vector and the input source are kept so
    /// gamepad play can be mapped onto the bot's digital buttons.
    /// </summary>
    internal sealed class InputExporter : IExporter
    {
        public string Key => "input";

        public void Write(Ipc.MsgPackWriter w, FrameContext ctx)
        {
            var ih = ctx.Gm != null ? ctx.Gm.inputHandler : null;
            var a = ih != null ? ih.inputActions : null;
            if (a == null) { w.Nil(); return; }

            uint mask = 0;
            // Order must match KeyboardInjector.ButtonNames.
            if (a.Jump.IsPressed) mask |= 1u << 0;
            if (a.Attack.IsPressed) mask |= 1u << 1;
            if (a.Dash.IsPressed) mask |= 1u << 2;
            if (a.Cast.IsPressed) mask |= 1u << 3;          // bind
            if (a.SuperDash.IsPressed) mask |= 1u << 4;     // clawline / silk soar
            if (a.DreamNail.IsPressed) mask |= 1u << 5;     // needolin
            if (a.QuickCast.IsPressed) mask |= 1u << 6;
            if (a.Taunt.IsPressed) mask |= 1u << 7;
            if (a.OpenInventory.IsPressed) mask |= 1u << 8;
            if (a.OpenInventoryMap.IsPressed) mask |= 1u << 9;
            if (a.OpenInventoryTools.IsPressed) mask |= 1u << 10;
            if (a.OpenInventoryJournal.IsPressed) mask |= 1u << 11;
            if (a.OpenInventoryQuests.IsPressed) mask |= 1u << 12;
            if (a.QuickMap.IsPressed) mask |= 1u << 13;
            if (a.Pause.IsPressed) mask |= 1u << 14;
            if (a.MenuSubmit.IsPressed) mask |= 1u << 15;   // enter
            if (a.PaneLeft.IsPressed) mask |= 1u << 16;
            if (a.PaneRight.IsPressed) mask |= 1u << 17;
            if (a.Up.IsPressed) mask |= 1u << 18;
            if (a.Down.IsPressed) mask |= 1u << 19;
            if (a.Left.IsPressed) mask |= 1u << 20;
            if (a.Right.IsPressed) mask |= 1u << 21;

            var move = a.MoveVector.Value;
            w.MapHeader(5);
            w.Key("mask"); w.UInt(mask);
            w.Key("move"); w.Vec2(move.x, move.y);
            w.Key("cancel"); w.Bool(a.MenuCancel.IsPressed);
            w.Key("src"); w.Str(ih.lastActiveController.ToString());
            w.Key("style"); w.Str(a.LastDeviceStyle.ToString());
        }
    }
}
