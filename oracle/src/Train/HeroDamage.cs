using System;
using GlobalEnums;

namespace SsOracle.Train
{
    /// <summary>
    /// Training-only probe tool: hurt Hornet through the game's own HeroController.TakeDamage path, so the
    /// real hit-freeze, recoil, i-frames, pause blocking and (on a sandbox Steel Soul save) death sequence all
    /// run. Used by P7/P15. Never used in evaluation runs.
    /// </summary>
    internal static class HeroDamage
    {
        public static string Hurt(string args)
        {
            var parts = args.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length < 2)
                return "err hurt takes <amount> <HazardType> [CollisionSide]";
            if (!int.TryParse(parts[0], out var amount))
                return $"err bad amount '{parts[0]}'";
            HazardType hazard;
            CollisionSide side = CollisionSide.left;
            try
            {
                hazard = (HazardType)Enum.Parse(typeof(HazardType), parts[1], ignoreCase: true);
                if (parts.Length > 2)
                    side = (CollisionSide)Enum.Parse(typeof(CollisionSide), parts[2], ignoreCase: true);
            }
            catch (ArgumentException e)
            {
                return "err " + e.Message;
            }

            var hero = HeroController.UnsafeInstance;
            if (hero == null) return "err no hero";
            var frame = UnityEngine.Time.frameCount;
            Core.Plugin.Log.LogWarning($"hurt {amount} {hazard} from {side} at frame {frame} (training probe)");
            hero.TakeDamage(hero.gameObject, side, amount, hazard);
            return "ok " + frame;
        }
    }
}
