using System;
using System.Collections.Generic;
using UnityEngine;

namespace SsOracle.SceneDump
{
    /// <summary>One piece of collider outline in world units.</summary>
    internal struct Shape
    {
        public string Kind;    // "box", "poly" (closed), "edge" (open chain), "circle" (1 vertex = centre), "capsule"
        public float[] Verts;  // x0, y0, x1, y1, ... (world space)
        public float Radius;   // circle / capsule radius, or the edge radius of boxes and edge chains
    }

    /// <summary>
    /// Collider2D -> world-space outlines. Authored shapes (box, polygon paths, edge chains, circles) are
    /// transformed with the collider's localToWorldMatrix after applying its offset, which is how 2D physics
    /// places them (DebugMod HitboxRender draws them the same way). Any other collider type (composite,
    /// tilemap, custom) falls back to the physics engine's own shapes (Collider2D.GetShapes).
    /// </summary>
    internal static class ColliderGeometry
    {
        private static readonly List<Vector2> Points = new List<Vector2>(256);
        private static readonly PhysicsShapeGroup2D Group = new PhysicsShapeGroup2D();

        /// <summary>Appends the shapes of <paramref name="col"/> to <paramref name="into"/>; returns the vertex count added.</summary>
        public static int Extract(Collider2D col, List<Shape> into)
        {
            var m = col.transform.localToWorldMatrix;
            var off = col.offset;
            switch (col)
            {
                case BoxCollider2D b:
                {
                    var h = b.size * 0.5f;
                    Points.Clear();
                    Points.Add(new Vector2(-h.x, -h.y));
                    Points.Add(new Vector2(h.x, -h.y));
                    Points.Add(new Vector2(h.x, h.y));
                    Points.Add(new Vector2(-h.x, h.y));
                    return Add(into, "box", m, off, b.edgeRadius);
                }
                case PolygonCollider2D p:
                {
                    var n = 0;
                    for (var i = 0; i < p.pathCount; i++)
                    {
                        Points.Clear();
                        p.GetPath(i, Points);
                        if (Points.Count >= 2) n += Add(into, "poly", m, off, 0f);
                    }
                    return n;
                }
                case EdgeCollider2D e:
                    Points.Clear();
                    e.GetPoints(Points);
                    return Points.Count >= 2 ? Add(into, "edge", m, off, e.edgeRadius) : 0;
                case CircleCollider2D c:
                {
                    var s = col.transform.lossyScale;
                    Points.Clear();
                    Points.Add(Vector2.zero);
                    return Add(into, "circle", m, off, c.radius * Mathf.Max(Mathf.Abs(s.x), Mathf.Abs(s.y)));
                }
                case CapsuleCollider2D cap:
                {
                    // Outline as its bounding box; the brain gets the kind and can round the ends.
                    var h = cap.size * 0.5f;
                    Points.Clear();
                    Points.Add(new Vector2(-h.x, -h.y));
                    Points.Add(new Vector2(h.x, -h.y));
                    Points.Add(new Vector2(h.x, h.y));
                    Points.Add(new Vector2(-h.x, h.y));
                    return Add(into, "capsule", m, off, 0f);
                }
                default:
                    return FromPhysics(col, into);
            }
        }

        private static int Add(List<Shape> into, string kind, Matrix4x4 m, Vector2 off, float radius)
        {
            var n = Points.Count;
            var v = new float[n * 2];
            for (var i = 0; i < n; i++)
            {
                var p = Points[i] + off;
                var w = m.MultiplyPoint3x4(new Vector3(p.x, p.y, 0f));
                v[2 * i] = w.x;
                v[2 * i + 1] = w.y;
            }
            into.Add(new Shape { Kind = kind, Verts = v, Radius = radius });
            return n;
        }

        private static int FromPhysics(Collider2D col, List<Shape> into)
        {
            int count;
            try
            {
                count = col.GetShapes(Group);
            }
            catch (Exception)
            {
                return 0;
            }
            var m = Group.localToWorldMatrix;
            var total = 0;
            for (var i = 0; i < count; i++)
            {
                var s = Group.GetShape(i);
                Points.Clear();
                Group.GetShapeVertices(i, Points);
                if (Points.Count == 0) continue;
                string kind;
                switch (s.shapeType)
                {
                    case PhysicsShapeType2D.Circle: kind = "circle"; break;
                    case PhysicsShapeType2D.Capsule: kind = "capsule"; break;
                    case PhysicsShapeType2D.Edges: kind = "edge"; break;
                    default: kind = "poly"; break;
                }
                total += Add(into, kind, m, Vector2.zero, s.radius);
            }
            return total;
        }

        /// <summary>Axis-aligned bounds [minx, miny, maxx, maxy] of shapes, or null when there are none.</summary>
        public static float[] Bounds(List<Shape> shapes, int from, int to)
        {
            float x0 = float.MaxValue, y0 = float.MaxValue, x1 = float.MinValue, y1 = float.MinValue;
            for (var s = from; s < to; s++)
            {
                var v = shapes[s].Verts;
                var r = shapes[s].Radius;
                for (var i = 0; i + 1 < v.Length; i += 2)
                {
                    x0 = Math.Min(x0, v[i] - r); x1 = Math.Max(x1, v[i] + r);
                    y0 = Math.Min(y0, v[i + 1] - r); y1 = Math.Max(y1, v[i + 1] + r);
                }
            }
            return x0 > x1 ? null : new[] { x0, y0, x1, y1 };
        }
    }
}
