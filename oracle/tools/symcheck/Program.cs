using System.Collections;
using System.Reflection;
using System.Runtime.Loader;

// Offline SymbolCheck (no game launch): loads the pinned game DLLs (+ DebugMod) and a built SsOracle.dll under .NET 8,
// then runs SsOracle.Core.SymbolCheck.Evaluate() (the exact table the plugin checks at startup), replays
// LethalBlock.Simulate on the documented Fractured Mask / blue health cases, and checks that every guard patch binds
// to its target (PatchCheck.cs). Harmony itself cannot initialize outside Unity, which is why SymbolCheck uses plain
// reflection.
//
//   cd oracle && dotnet build -c Release -p:Deploy=false
//   dotnet run --project tools/symcheck -c Release -- bin/Release/net472/SsOracle.dll [C:\ssbot\game\train] [--no-debugmod]
//
// Exit code 0 = every hard symbol resolved and every patch signature matches.
var game = args.Length > 1 && !args[1].StartsWith("--") ? args[1] : @"C:\ssbot\game\train";
var managed = Path.Combine(game, @"Hollow Knight Silksong_Data\Managed");
var core = Path.Combine(game, @"BepInEx\core");
var dm = Path.Combine(game, @"BepInEx\plugins\DebugMod");
var oracle = Path.GetFullPath(args[0]);
string[] dirs = { managed, core, dm, Path.GetDirectoryName(oracle) };
AssemblyLoadContext.Default.Resolving += (ctx, name) =>
{
    foreach (var d in dirs)
    {
        var p = Path.Combine(d, name.Name + ".dll");
        if (File.Exists(p)) return ctx.LoadFromAssemblyPath(p);
    }
    return null;
};
foreach (var n in new[] { "Assembly-CSharp", "PlayMaker", "TeamCherry.TK2D", "TeamCherry.SharedUtils", "Assembly-CSharp-firstpass", "UnityEngine.CoreModule", "UnityEngine.Physics2DModule", "Unity.InputSystem" })
    AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(managed, n + ".dll"));
if (!args.Contains("--no-debugmod")) AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(dm, "DebugMod.dll"));
var asm = AssemblyLoadContext.Default.LoadFromAssemblyPath(oracle);

var t = asm.GetType("SsOracle.Core.SymbolCheck", true);
var r = t.GetMethod("Evaluate", BindingFlags.Public | BindingFlags.Static).Invoke(null, null);
object F(string n) => r.GetType().GetField(n).GetValue(r);
Console.WriteLine($"symbols: ok={F("Ok")} resolved={F("Resolved")}/{F("Total")} in {F("Micros")} us");
foreach (var m in (IEnumerable)F("Missing")) Console.WriteLine("  MISSING " + m);
foreach (var m in (IEnumerable)F("SoftMissing")) Console.WriteLine("  soft    " + m);

// PlayerData.TakeHealth replay: (hp, maxHealth, CurrentMaxHealth, blue, mask equipped, AmountLeft, amount, allowBreak, PreventDeath).
var lb = asm.GetType("SsOracle.Guards.LethalBlock", true);
var sim = lb.GetMethod("Simulate", BindingFlags.Public | BindingFlags.Static);
string S(int hp, int max, int cur, int blue, bool eq, int left, int amt, bool allow, bool prevent)
{
    var o = sim.Invoke(null, new object[] { hp, max, cur, blue, eq, left, amt, allow, prevent });
    object G(string n) => o.GetType().GetField(n).GetValue(o);
    return $"hp={G("Health")} blue={G("Blue")} mask={G("MaskLeft")} zero={G("ReachesZero")} saved={G("MaskSaved")} consumed={G("MaskConsumed")}";
}
// Expected values worked out by hand from PlayerData.cs:3605-3655 (1.0.30000); a mismatch fails the run.
var replayBad = 0;
void R(string what, string got, string want)
{
    var ok = got == want;
    if (!ok) replayBad++;
    Console.WriteLine($"  {(ok ? "ok  " : "BAD ")} {what,-34} {got}{(ok ? "" : "   expected " + want)}");
}
Console.WriteLine("TakeHealth replay:");
R("hp1 dmg1, no mask", S(1, 5, 5, 0, false, 0, 1, true, false), "hp=0 blue=0 mask=0 zero=True saved=False consumed=False");
R("hp1 dmg1, mask, may break", S(1, 5, 5, 0, true, 1, 1, true, false), "hp=1 blue=0 mask=0 zero=False saved=True consumed=True");
R("hp1 dmg1, mask, MidChain", S(1, 5, 5, 0, true, 1, 1, false, false), "hp=1 blue=0 mask=1 zero=False saved=True consumed=False");
R("hp1 dmg1, mask spent", S(1, 5, 5, 0, true, 0, 1, true, false), "hp=0 blue=0 mask=0 zero=True saved=False consumed=False");
R("hp3 dmg5, mask (saves at 1 HP)", S(3, 5, 5, 0, true, 1, 5, true, false), "hp=1 blue=0 mask=0 zero=False saved=True consumed=True");
R("hp2 blue1 dmg2", S(2, 5, 5, 1, false, 0, 2, true, false), "hp=1 blue=0 mask=0 zero=False saved=False consumed=False");
R("hp1 blue1 dmg2", S(1, 5, 5, 1, false, 0, 2, true, false), "hp=0 blue=0 mask=0 zero=True saved=False consumed=False");
R("hp1 blue3 dmg2", S(1, 5, 5, 3, false, 0, 2, true, false), "hp=1 blue=1 mask=0 zero=False saved=False consumed=False");
R("hp1 blue1 dmg2, mask", S(1, 5, 5, 1, true, 1, 2, true, false), "hp=1 blue=0 mask=0 zero=False saved=True consumed=True");
R("hp0 dmg0", S(0, 5, 5, 0, false, 0, 0, true, false), "hp=0 blue=0 mask=0 zero=True saved=False consumed=False");
R("hp0 dmg1, mask (heals to 1)", S(0, 5, 5, 0, true, 1, 1, false, false), "hp=1 blue=0 mask=1 zero=False saved=True consumed=False");
R("hp1 dmg0 (critical at 1 HP)", S(1, 5, 5, 0, false, 0, 0, true, false), "hp=1 blue=0 mask=0 zero=False saved=False consumed=False");
R("hp0 dmg-1 (critical at 0 HP)", S(0, 5, 5, 0, false, 0, -1, true, false), "hp=1 blue=0 mask=0 zero=False saved=False consumed=False");
R("hp5=max, BoundShell max 3, dmg1", S(5, 5, 3, 0, false, 0, 1, true, false), "hp=2 blue=0 mask=0 zero=False saved=False consumed=False");
R("hp1 dmg1, PreventDeath cheat", S(1, 5, 5, 0, false, 0, 1, true, true), "hp=1 blue=0 mask=0 zero=True saved=False consumed=False");
Console.WriteLine($"TakeHealth replay: {replayBad} mismatches");

var patchProblems = PatchCheck.Run();
return (bool)F("Ok") && patchProblems == 0 && replayBad == 0 ? 0 : 1;
