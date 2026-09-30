using GlobalEnums;
using UnityEngine;

namespace SsOracle.Train
{
    /// <summary>
    /// Where the randomized start may move the hero sideways. A candidate offset is accepted when (1) sweeping the hero
    /// box (lifted off the floor so the floor and gentle slopes do not count) meets no TERRAIN collider, (2) for a
    /// grounded hero, a downward ray at the new spot finds non-steep ground within half a unit of the current floor
    /// (no pits, no ledges; same ground layers and steep-slope rule as the game's TouchGroundResult), and (3) the hero
    /// box fits there. The requested offset is tried first, then 3/4, 1/2 and 1/4 of it, then none.
    /// Trigger colliders are ignored throughout. Main thread only.
    /// </summary>
    internal static class StartPlacement
    {
        private const int TerrainMask = 1 << (int)PhysLayers.TERRAIN;
        /// <summary>TouchGroundResult's mask (8448 = TERRAIN | layer 13).</summary>
        private const int GroundMask = 8448;
        private const float FloorLift = 0.2f;
        private const float MaxStep = 0.5f;

        private static readonly float[] Fractions = { 1f, 0.75f, 0.5f, 0.25f };
        private static readonly RaycastHit2D[] Hits = new RaycastHit2D[16];
        private static readonly Collider2D[] Overlaps = new Collider2D[8];

        /// <summary>The accepted x offset (0 when none fits); dy is the floor height change to apply with it.</summary>
        public static float FindOffset(HeroController hero, float want, out float dy, out int tries, out string note)
        {
            dy = 0f;
            tries = 0;
            note = null;
            if (Mathf.Abs(want) < 0.01f) return 0f;

            var b = hero.Bounds;
            var grounded = hero.cState.onGround;
            var solid = Filter(TerrainMask);
            var ground = Filter(GroundMask);
            var sweep = new Vector2(b.size.x * 0.9f, Mathf.Max(0.1f, b.size.y - 2f * FloorLift));
            var fit = new Vector2(b.size.x * 0.95f, b.size.y * 0.95f);
            var dir = new Vector2(Mathf.Sign(want), 0f);

            foreach (var fraction in Fractions)
            {
                var dx = want * fraction;
                if (Mathf.Abs(dx) < 0.05f) break;
                tries++;
                if (Physics2D.BoxCast(new Vector2(b.center.x, b.center.y + FloorLift), sweep, 0f, dir, solid, Hits, Mathf.Abs(dx)) > 0)
                {
                    note = "wall";
                    continue;
                }
                var step = 0f;
                if (grounded)
                {
                    if (!GroundBelow(new Vector2(b.center.x + dx, b.center.y), b.extents.y + 1f, ground, out var floorY))
                    {
                        note = "no ground";
                        continue;
                    }
                    step = floorY - b.min.y;
                    if (Mathf.Abs(step) > MaxStep)
                    {
                        note = "ledge";
                        continue;
                    }
                    if (Mathf.Abs(step) < 0.05f) step = 0f;
                }
                if (Physics2D.OverlapBox(new Vector2(b.center.x + dx, b.center.y + step + 0.05f), fit, 0f, solid, Overlaps) > 0)
                {
                    note = "no room";
                    continue;
                }
                dy = step;
                note = fraction < 1f ? $"shortened ({note})" : null;
                return dx;
            }
            return 0f;
        }

        private static bool GroundBelow(Vector2 origin, float distance, ContactFilter2D filter, out float y)
        {
            y = 0f;
            var n = Physics2D.Raycast(origin, Vector2.down, filter, Hits, distance);
            var best = float.MaxValue;
            for (var i = 0; i < n; i++)
            {
                var h = Hits[i];
                if (h.collider == null || h.distance >= best || SteepSlope.IsSteepSlope(h.collider)) continue;
                best = h.distance;
                y = h.point.y;
            }
            return best < float.MaxValue;
        }

        private static ContactFilter2D Filter(int mask)
        {
            var f = new ContactFilter2D { useTriggers = false };
            f.SetLayerMask(mask);
            return f;
        }
    }
}
