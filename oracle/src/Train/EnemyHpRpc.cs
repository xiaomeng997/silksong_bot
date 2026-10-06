using System;
using System.Collections.Generic;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// RPC "enemy.hp" {type_key, hp | frac} (Task route bosses, 2026-10-06): sets the HP of every enemy whose entity
    /// type key (EntityRegistry.TypeKey of its GameObject name) is type_key, for training-only starts in a boss's
    /// late phases (Last Judge's flame and rage phases, Trobbio's second phase, Lace 1's cross slash all branch on the
    /// boss HP: CompareHP in their Control FSMs). hp sets it outright; frac multiplies the current hp (rounded, at
    /// least 1). Writes HealthManager.hp directly, as the game's own SetHP / SubtractHP actions do: no hit, no "hit"
    /// event, no stun count; ents[].hp shows the new value from the next STATE. Dead enemies (isDead) are left alone.
    /// Only where the profile allows cheats (training copy); never in the formal run.
    /// Returns {set: [{iid, name, hp_before, hp_after}]}; an error when nothing matched.
    /// </summary>
    internal static class EnemyHpRpc
    {
        public static void Register() => Ipc.Rpc.Register("enemy.hp", Set);

        private static void Set(Dictionary<string, object> args, Ipc.Rpc.Reply reply)
        {
            if (!Core.Profile.Rules.CheatsAllowed)
            {
                reply.Fail($"enemy.hp is disabled in profile {Core.Profile.Current}");
                return;
            }
            var key = Ipc.Rpc.Str(args, "type_key");
            if (string.IsNullOrEmpty(key))
            {
                reply.Fail("enemy.hp needs type_key");
                return;
            }
            var hasHp = args.ContainsKey("hp");
            var hasFrac = args.ContainsKey("frac");
            if (hasHp == hasFrac)
            {
                reply.Fail("enemy.hp takes exactly one of hp, frac");
                return;
            }
            var hp = hasHp ? (int)Ipc.Rpc.Long(args, "hp") : 0;
            var frac = hasFrac ? Ipc.Rpc.Double(args, "frac", 1.0) : 1.0;
            if ((hasHp && hp < 1) || (hasFrac && !(frac > 0.0 && frac <= 1.0)))
            {
                reply.Fail("hp must be >= 1, frac in (0, 1]");
                return;
            }
            var set = new List<object>();
            try
            {
                foreach (var hm in UnityEngine.Object.FindObjectsByType<HealthManager>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                {
                    if (hm == null || hm.isDead) continue;
                    var go = hm.gameObject;
                    if (Entities.EntityRegistry.TypeKey(go.name) != key) continue;
                    var before = hm.hp;
                    var after = hasHp ? hp : Math.Max(1, (int)Math.Round(before * frac));
                    hm.hp = after;
                    set.Add(new Dictionary<string, object>
                    {
                        ["iid"] = (long)go.GetInstanceID(),
                        ["name"] = go.name,
                        ["hp_before"] = (long)before,
                        ["hp_after"] = (long)after,
                    });
                }
            }
            catch (Exception e)
            {
                reply.Fail(e.GetType().Name + ": " + e.Message);
                return;
            }
            if (set.Count == 0)
            {
                reply.Fail($"no live enemy with type key {key}");
                return;
            }
            Core.Plugin.Log.LogInfo($"enemy.hp {key}: {set.Count} set");
            reply.Ok(new Dictionary<string, object> { ["set"] = set });
        }
    }
}
