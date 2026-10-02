using System;
using System.Collections.Generic;
using GlobalEnums;
using SsOracle.Entities;
using UnityEngine;

/// <summary>
/// Offline checks of the Entities module's pure helpers: type_key suffix stripping, the effective-damage rule
/// (HeroController.TakeDamage hazard overrides), the parryable rule and the collider outline math. Everything that needs the engine
/// (collider getters, transforms) is left to the in-game probe brain/ssbot/probes/m1_entities.py.
/// </summary>
internal static class Program
{
    private static int fails;

    private static void Check(bool ok, string what)
    {
        if (!ok) fails++;
        Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    }

    private static void Eq<T>(T got, T want, string what) => Check(Equals(got, want), $"{what}: got {got} want {want}");

    private static void Near(float got, float want, string what) =>
        Check(Math.Abs(got - want) < 1e-4f, $"{what}: got {got:R} want {want:R}");

    private static int Main()
    {
        TypeKeys();
        EffectiveDamage();
        Parry();
        Geometry();
        M2Exports();
        Console.WriteLine(fails == 0 ? "ALL OK" : $"{fails} FAILED");
        return fails == 0 ? 0 : 1;
    }

    private static void TypeKeys()
    {
        foreach (var (name, want) in new[]
                 {
                     ("Bone Hunter (3)(Clone)", "Bone Hunter"), ("Spike Collider (12)", "Spike Collider"), ("(1)", "(1)"),
                     ("Foo(Clone)(Clone)", "Foo"), ("Foo (bar)", "Foo (bar)"), ("Foo  (2) ", "Foo"), ("", ""),
                     ("A(Clone) (4)", "A"), ("Mossbone Crawler", "Mossbone Crawler"), ("x()", "x()"),
                 })
            Eq(EntityRegistry.TypeKey(name), want, $"TypeKey('{name}')");
    }

    private static void EffectiveDamage()
    {
        int E(int dealt, HazardType h, DamagePropertyFlags f = 0) => EntityExporter.Effective(dealt, (int)h, (int)f);
        Eq(E(1, HazardType.SPIKES), 1, "SPIKES 1");
        Eq(E(3, HazardType.SPIKES, DamagePropertyFlags.Flame), 1, "SPIKES+Flame stays 1 (flags only in default branch)");
        Eq(E(3, HazardType.LAVA), 2, "LAVA 2");
        Eq(E(0, HazardType.LAVA), 0, "overrides need damageDealt > 0");
        Eq(E(1, HazardType.ENEMY, DamagePropertyFlags.Flame), 2, "ENEMY+Flame 2");
        Eq(E(3, HazardType.ENEMY, DamagePropertyFlags.Void), 2, "ENEMY+Void 3 -> 2");
        Eq(E(2, HazardType.ENEMY), 2, "ENEMY uses dealt");
        Eq(E(1, HazardType.RESPAWN_PIT), 0, "RESPAWN_PIT 0");
        Eq(E(1, HazardType.STEAM), 2, "STEAM 2");
        Eq(E(5, HazardType.PIT), 5, "PIT uses dealt");
        Eq(E(1, HazardType.COAL_SPIKES), 1, "COAL_SPIKES 1");
        Eq(E(4, HazardType.ZAP), 1, "ZAP 1");
    }

    private static void Parry()
    {
        // parryable follows forceParry / canClashTink; the Cross Stitch counter (hazard ENEMY) is only a bit.
        Eq(EntityExporter.Parryable(EntityExporter.ParryClash), true, "CLASH is parryable");
        Eq(EntityExporter.Parryable(EntityExporter.ParryForce), true, "FORCE is parryable");
        Eq(EntityExporter.Parryable(EntityExporter.ParryCounter), false, "COUNTER alone is not parryable");
        Eq(EntityExporter.Parryable(0), false, "no bits, not parryable");
        Eq(EntityExporter.Parryable(EntityExporter.ParryClash | EntityExporter.ParryCounter), true, "CLASH + COUNTER");
    }

    private static float[] Aabb(List<float> v)
    {
        float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
        for (var i = 0; i < v.Count; i += 2)
        {
            x0 = Math.Min(x0, v[i]); x1 = Math.Max(x1, v[i]);
            y0 = Math.Min(y0, v[i + 1]); y1 = Math.Max(y1, v[i + 1]);
        }
        return new[] { x0, y0, x1, y1 };
    }

    private static double SignedArea(List<float> v)
    {
        double a = 0;
        for (var i = 0; i < v.Count; i += 2)
        {
            var j = (i + 2) % v.Count;
            a += v[i] * v[j + 1] - v[j] * v[i + 1];
        }
        return a / 2;
    }

    private static void Geometry()
    {
        // x' = -2x + 10, y' = y + 5: scaled and mirrored, like an enemy facing the other way.
        var m = new Matrix4x4(new Vector4(-2, 0, 0, 0), new Vector4(0, 1, 0, 0), new Vector4(0, 0, 1, 0), new Vector4(10, 5, 0, 1));
        var v = new List<float>();
        ColliderGeometry.AppendBox(v, ref m, new Vector2(0.5f, 0), new Vector2(2, 4), 0f);
        var box = new[] { 11f, 3f, 7f, 3f, 7f, 7f, 11f, 7f };
        for (var i = 0; i < 8; i++) Near(v[i], box[i], $"box v[{i}]");

        v.Clear();
        ColliderGeometry.AppendBox(v, ref m, Vector2.zero, new Vector2(2, 2), 0.5f);
        var a = Aabb(v);
        Near(a[0], 7f, "box edgeRadius grows it (minx)");
        Near(a[3], 6.5f, "box edgeRadius grows it (maxy)");

        v.Clear();
        var r = ColliderGeometry.AppendCircle(v, ref m, new Vector2(1, 0), 1f);
        Near(r, 2f, "circle world radius uses the larger axis scale");
        Eq(v.Count, 16, "circle is an octagon");
        a = Aabb(v);
        Near(a[0], 6f, "octagon AABB = circle AABB (minx)");
        Near(a[2], 10f, "octagon AABB = circle AABB (maxx)");
        Near(a[1], 3f, "octagon AABB = circle AABB (miny)");
        Near(a[3], 7f, "octagon AABB = circle AABB (maxy)");
        for (var i = 0; i < 16; i += 2)
        {
            var d = (float)Math.Sqrt((v[i] - 8) * (v[i] - 8) + (v[i + 1] - 5) * (v[i + 1] - 5));
            Near(d, 2f * 1.0823922f, $"octagon vertex {i / 2} circumscribes");
        }

        var id = Matrix4x4.identity;
        v.Clear();
        ColliderGeometry.AppendCapsule(v, ref id, Vector2.zero, new Vector2(1, 3), true);
        Eq(v.Count, 20, "capsule has 10 points");
        a = Aabb(v);
        Near(a[0], -0.5f, "vertical capsule minx");
        Near(a[2], 0.5f, "vertical capsule maxx");
        Near(a[1], -1.5f, "vertical capsule miny");
        Near(a[3], 1.5f, "vertical capsule maxy");
        Check(SignedArea(v) > 0, "vertical capsule is counter-clockwise");

        v.Clear();
        ColliderGeometry.AppendCapsule(v, ref id, new Vector2(1, 1), new Vector2(3, 1), false);
        a = Aabb(v);
        Near(a[0], -0.5f, "horizontal capsule minx");
        Near(a[2], 2.5f, "horizontal capsule maxx");
        Near(a[1], 0.5f, "horizontal capsule miny");
        Near(a[3], 1.5f, "horizontal capsule maxy");
        Check(SignedArea(v) > 0, "horizontal capsule is counter-clockwise");

        v.Clear();
        ColliderGeometry.AppendPoints(v, ref m, new Vector2(1, 1), new List<Vector2> { new Vector2(0, 0), new Vector2(1, 2) });
        Near(v[0], 8f, "points: offset then transform (x0)");
        Near(v[1], 6f, "points: offset then transform (y0)");
        Near(v[2], 6f, "points: offset then transform (x1)");
        Near(v[3], 8f, "points: offset then transform (y1)");
    }

    /// <summary>The pure parts of the M2 STATE additions (docs/facts/1.0.30000/state_fields_m2.md); the engine-side parts
    /// are checked in game by brain/ssbot/probes/m2_exports.py.</summary>
    private static void M2Exports()
    {
        // menu.sel roles
        Eq(SsOracle.Export.MenuExporter.PauseRole(UnityEngine.UI.PauseMenuButton.PauseButtonType.Continue), "continue", "sel Continue");
        Eq(SsOracle.Export.MenuExporter.PauseRole(UnityEngine.UI.PauseMenuButton.PauseButtonType.Options), "options", "sel Options");
        Eq(SsOracle.Export.MenuExporter.PauseRole(UnityEngine.UI.PauseMenuButton.PauseButtonType.Quit), "quit", "sel Quit");
        Eq(SsOracle.Export.MenuExporter.MethodRole("UIReturnToMainMenu"), "yes", "prompt Yes calls UIReturnToMainMenu");
        Eq(SsOracle.Export.MenuExporter.MethodRole("UILeaveExitToMenuPrompt"), "no", "prompt No calls UILeaveExitToMenuPrompt");
        Eq(SsOracle.Export.MenuExporter.MethodRole("UIGoBack"), "back", "a back button calls UIGoBack");
        Eq(SsOracle.Export.MenuExporter.MethodRole("UIGoToOptionsMenu"), null, "anything else has no role");
        // Every listener name the mapping uses is a real UIManager method (a rename would silently drop yes/no).
        foreach (var name in new[] { "UIReturnToMainMenu", "UILeaveExitToMenuPrompt", "UIGoBack" })
            Check(typeof(UIManager).GetMethod(name) != null, $"UIManager.{name} exists");

        // room.gates selection: battle gates, solids off in the dump, and solids seen changed since.
        Eq(SsOracle.SceneDump.GateWatch.IsWatched(false, true, true), false, "a solid on at the dump and on now is not listed");
        Eq(SsOracle.SceneDump.GateWatch.IsWatched(false, false, false), true, "Bone_05 'Threaded Bell Gate' (off at entry) is listed");
        Eq(SsOracle.SceneDump.GateWatch.IsWatched(false, true, false), true, "Bone_05 'Wall' (on at entry, gone later) is listed once seen off");
        Eq(SsOracle.SceneDump.GateWatch.IsWatched(true, true, true), true, "a BattleScene gate is always listed");

        // hero.tags dmg_left
        Eq(SsOracle.Hero.HeroExporter.TagDmgLeft(false, 3, 2, 1), 2, "limited tag: hits left x amount");
        Eq(SsOracle.Hero.HeroExporter.TagDmgLeft(false, 0, 0, 1), -1, "unlimited tag (frost water while swimming): -1");
        Eq(SsOracle.Hero.HeroExporter.TagDmgLeft(true, 0, 0, 2), 2, "RemoveAfterNextHit: one more hit");
        Eq(SsOracle.Hero.HeroExporter.TagDmgLeft(false, 5, 0, 1), 0, "limited tag with no hits left: 0");

        // act.hf age cap must not hide a difference the filter acts on
        Check(SsOracle.Export.FrameExporter.HfAgeCap >= SsOracle.Input.HoldFilter.DefaultMinPressFrames &&
              SsOracle.Export.FrameExporter.HfAgeCap >= SsOracle.Input.HoldFilter.DefaultMinReleaseFrames,
              "act.hf age cap is above the minimum press / release frames");
    }
}
