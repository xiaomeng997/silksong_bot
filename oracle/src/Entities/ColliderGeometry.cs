using System.Collections.Generic;
using UnityEngine;

namespace SsOracle.Entities
{
    /// <summary>
    /// World-space outlines of 2D colliders for the "ents" export (DESIGN §3.1.2 colliders[].verts_world; the
    /// projector turns them into screen polygons, §3.1.3). Points are appended to a flat float list as x0, y0,
    /// x1, y1, ... in the collider's z = 0 local plane. Only managed math plus the shape getters; no allocation.
    /// </summary>
    internal static class ColliderGeometry
    {
        public const byte Box = 0, Circle = 1, Poly = 2, Capsule = 3, Edge = 4, Aabb = 5;

        /// <summary>Wire names of the shape kinds, indexed by the constants above.</summary>
        public static readonly string[] KindNames = { "box", "circle", "poly", "capsule", "edge", "aabb" };

        /// <summary>1 / cos(22.5 deg): the octagon standing in for a circle circumscribes it, so the polygon never
        /// under-reports a threat and its axis-aligned extent equals the circle's.</summary>
        private const float OctagonCircumscribe = 1.0823922f;

        private static readonly float[] OctCos = new float[8];
        private static readonly float[] OctSin = new float[8];
        private static readonly float[] ArcCos = new float[5];
        private static readonly float[] ArcSin = new float[5];

        static ColliderGeometry()
        {
            // Vertices at 22.5 + k*45 deg: flat top, bottom and sides.
            for (var k = 0; k < 8; k++)
            {
                var a = Mathf.Deg2Rad * (22.5f + 45f * k);
                OctCos[k] = Mathf.Cos(a) * OctagonCircumscribe;
                OctSin[k] = Mathf.Sin(a) * OctagonCircumscribe;
            }
            for (var k = 0; k < 5; k++)
            {
                var a = Mathf.Deg2Rad * (45f * k);
                ArcCos[k] = Mathf.Cos(a);
                ArcSin[k] = Mathf.Sin(a);
            }
        }

        public static byte ShapeOf(Collider2D c)
        {
            switch (c)
            {
                case BoxCollider2D _: return Box;
                case CircleCollider2D _: return Circle;
                case PolygonCollider2D _: return Poly;
                case CapsuleCollider2D _: return Capsule;
                case EdgeCollider2D _: return Edge;
                default: return Aabb;
            }
        }

        private static void Add(List<float> dst, ref Matrix4x4 m, float x, float y)
        {
            dst.Add(m.m00 * x + m.m01 * y + m.m03);
            dst.Add(m.m10 * x + m.m11 * y + m.m13);
        }

        public static void AppendBox(List<float> dst, ref Matrix4x4 m, BoxCollider2D box) =>
            AppendBox(dst, ref m, box.offset, box.size, box.edgeRadius);

        public static float AppendCircle(List<float> dst, ref Matrix4x4 m, CircleCollider2D circle) =>
            AppendCircle(dst, ref m, circle.offset, circle.radius);

        public static void AppendCapsule(List<float> dst, ref Matrix4x4 m, CapsuleCollider2D cap) =>
            AppendCapsule(dst, ref m, cap.offset, cap.size, cap.direction == CapsuleDirection2D.Vertical);

        // The shape math below takes plain values so it can be checked outside Unity.

        /// <summary>From the local bottom-left corner, counter-clockwise in local space (a flipped transform
        /// mirrors the winding). Rounded corners (edgeRadius) grow the box; the square hull over-reports by less
        /// than r(1 - pi/4).</summary>
        public static void AppendBox(List<float> dst, ref Matrix4x4 m, Vector2 off, Vector2 size, float edgeRadius)
        {
            var hx = size.x * 0.5f + edgeRadius;
            var hy = size.y * 0.5f + edgeRadius;
            Add(dst, ref m, off.x - hx, off.y - hy);
            Add(dst, ref m, off.x + hx, off.y - hy);
            Add(dst, ref m, off.x + hx, off.y + hy);
            Add(dst, ref m, off.x - hx, off.y + hy);
        }

        /// <summary>Returns the world radius. Box2D scales circles by the larger axis scale.</summary>
        public static float AppendCircle(List<float> dst, ref Matrix4x4 m, Vector2 off, float radius)
        {
            var cx = m.m00 * off.x + m.m01 * off.y + m.m03;
            var cy = m.m10 * off.x + m.m11 * off.y + m.m13;
            var sx = Mathf.Sqrt(m.m00 * m.m00 + m.m10 * m.m10);
            var sy = Mathf.Sqrt(m.m01 * m.m01 + m.m11 * m.m11);
            var r = radius * Mathf.Max(sx, sy);
            for (var k = 0; k < 8; k++)
            {
                dst.Add(cx + r * OctCos[k]);
                dst.Add(cy + r * OctSin[k]);
            }
            return r;
        }

        /// <summary>Two half-circles of 5 points each joined by straight sides (10 points, counter-clockwise in
        /// local space).</summary>
        public static void AppendCapsule(List<float> dst, ref Matrix4x4 m, Vector2 off, Vector2 size, bool vertical)
        {
            var r = 0.5f * (vertical ? size.x : size.y);
            var half = Mathf.Max(0f, 0.5f * (vertical ? size.y : size.x) - r);
            for (var end = 0; end < 2; end++)
            {
                var sign = end == 0 ? 1f : -1f;
                for (var k = 0; k < 5; k++)
                {
                    // Vertical: top arc from +x over +y to -x, then the bottom arc mirrored. Horizontal: rotated 90 deg.
                    float ax = ArcCos[k] * r * sign, ay = ArcSin[k] * r * sign;
                    if (vertical) Add(dst, ref m, off.x + ax, off.y + ay + sign * half);
                    else Add(dst, ref m, off.x + ay + sign * half, off.y - ax);
                }
            }
        }

        /// <summary>Local points (collider offset not yet applied) to world.</summary>
        public static void AppendPoints(List<float> dst, ref Matrix4x4 m, Vector2 offset, List<Vector2> local)
        {
            for (var i = 0; i < local.Count; i++)
            {
                var p = local[i];
                Add(dst, ref m, p.x + offset.x, p.y + offset.y);
            }
        }

        /// <summary>Fallback for composite/tilemap/custom colliders: the world AABB as a quad.</summary>
        public static void AppendBounds(List<float> dst, Collider2D c)
        {
            var b = c.bounds;
            var min = b.min;
            var max = b.max;
            dst.Add(min.x); dst.Add(min.y);
            dst.Add(max.x); dst.Add(min.y);
            dst.Add(max.x); dst.Add(max.y);
            dst.Add(min.x); dst.Add(max.y);
        }
    }
}
