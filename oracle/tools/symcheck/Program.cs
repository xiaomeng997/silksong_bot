using System.Collections;
using System.Reflection;
using System.Runtime.Loader;

// Offline SymbolCheck (no game launch): loads the pinned game DLLs (+ DebugMod) and a built SsOracle.dll under .NET 8,
// then runs SsOracle.Core.SymbolCheck.Evaluate() (the exact table the plugin checks at startup), replays
// LethalBlock.Simulate on the documented Fractured Mask / blue health cases and AbilityGrant.ChooseSlot on synthetic
// crests, and checks that every guard patch binds to its target (PatchCheck.cs). Harmony itself cannot initialize
// outside Unity, which is why SymbolCheck uses plain reflection.
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
foreach (var n in new[] { "Assembly-CSharp", "PlayMaker", "TeamCherry.TK2D", "TeamCherry.SharedUtils", "Assembly-CSharp-firstpass", "UnityEngine.CoreModule", "UnityEngine.Physics2DModule", "Unity.InputSystem", "UnityEngine.UI", "UnityEngine.UIModule" })
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

// abilities.grant slot choice (AbilityGrant.ChooseSlot) on synthetic crests; expected values from its rules: never Up
// if avoidable, no binding another attack tool already uses, unlocked before locked, Neutral before Down, free first.
var gameAsm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "Assembly-CSharp");
var slotT = gameAsm.GetType("ToolCrest+SlotInfo", true);
var typeT = gameAsm.GetType("ToolItemType", true);
var bindT = gameAsm.GetType("AttackToolBinding", true);
var choose = asm.GetType("SsOracle.Train.AbilityGrant", true).GetMethod("ChooseSlot", BindingFlags.NonPublic | BindingFlags.Static);
Array Crest(params string[] slots)  // "Red/Up", "Skill/Neutral", ...
{
    var arr = Array.CreateInstance(slotT, slots.Length);
    for (var i = 0; i < slots.Length; i++)
    {
        var o = Activator.CreateInstance(slotT);
        var parts = slots[i].Split('/');
        slotT.GetField("Type").SetValue(o, Enum.Parse(typeT, parts[0]));
        slotT.GetField("AttackBinding").SetValue(o, Enum.Parse(bindT, parts[1]));
        arr.SetValue(o, i);
    }
    return arr;
}
var slotBad = 0;
void C(string what, string type, Array crest, string[] names, bool[] usable, string[] keep, bool unlock, int want)
{
    Func<string, bool> isAttack = n => n.StartsWith("attack:");
    var got = (int)choose.Invoke(null, new object[] { Enum.Parse(typeT, type), crest, names.ToList(), usable, keep.ToList(), unlock, isAttack });
    var ok = got == want;
    if (!ok) slotBad++;
    Console.WriteLine($"  {(ok ? "ok  " : "BAD ")} {what,-56} slot {got}{(ok ? "" : "   expected " + want)}");
}
Console.WriteLine("abilities.grant slot choice:");
var hunter = Crest("Red/Up", "Blue/Neutral", "Red/Down", "Skill/Neutral", "Yellow/Neutral", "Blue/Neutral", "Yellow/Neutral");
var hunterUsable = new[] { true, true, false, true, true, false, false };
var empty7 = new[] { "", "", "", "", "", "", "" };
C("skill -> the Neutral skill slot", "Skill", hunter, empty7, hunterUsable, new string[0], false, 3);
C("red, locked slots off -> the only unlocked one (Up)", "Red", hunter, empty7, hunterUsable, new string[0], false, 0);
C("red, unlock_slots -> locked Down beats unlocked Up", "Red", hunter, empty7, hunterUsable, new string[0], true, 2);
C("blue, unlock_slots -> unlocked before locked", "Blue", hunter, empty7, hunterUsable, new string[0], true, 1);
var shared = Crest("Red/Neutral", "Red/Down", "Skill/Neutral");
C("red, Neutral taken by the skill -> locked Down", "Red", shared, new[] { "", "", "attack:Skill" }, new[] { true, false, true }, new string[0], true, 1);
C("red, Neutral taken, locked slots off -> Neutral anyway", "Red", shared, new[] { "", "", "attack:Skill" }, new[] { true, false, true }, new string[0], false, 0);
C("red, all free and usable -> Neutral before Down", "Red", shared, new[] { "", "", "" }, new[] { true, true, true }, new string[0], false, 0);
C("red, only slot holds a requested tool -> none", "Red", shared, new[] { "attack:Kept", "", "" }, new[] { true, false, true }, new[] { "attack:Kept", "attack:New" }, false, -1);
C("red, only slot holds another tool -> replace it", "Red", shared, new[] { "attack:Old", "", "" }, new[] { true, false, true }, new[] { "attack:New" }, false, 0);
C("skill on a crest without a skill slot -> none", "Skill", Crest("Red/Neutral"), new[] { "" }, new[] { true }, new string[0], true, -1);
Console.WriteLine($"abilities.grant slot choice: {slotBad} mismatches");

var patchProblems = PatchCheck.Run();
return (bool)F("Ok") && patchProblems == 0 && replayBad == 0 && slotBad == 0 ? 0 : 1;
