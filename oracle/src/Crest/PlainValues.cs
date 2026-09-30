using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace SsOracle.Crest
{
    /// <summary>
    /// Reflection dump of a game object's plain fields for the crest RPCs (never per frame): every instance field of the
    /// object's type and its bases below the Unity base classes, public or not, serialized or runtime, whose value is
    /// plain data. Plain = bool, numbers, strings, enums (by name), Vector2/3/4, Color, UnityEngine.Object references (by
    /// name, null when missing or destroyed), arrays and lists of those, and [Serializable] structs made of them (two
    /// levels deep). Delegates, dictionaries and other classes are left out. An auto-property's backing field appears
    /// under the property name; a private field hidden by a same-named one further down gets "Type." in front.
    /// Values are whatever FramedServer.WriteObject can serialize.
    /// </summary>
    internal static class PlainValues
    {
        private const BindingFlags Declared = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
        private const int MaxItems = 256;

        private static readonly object Skip = new object();

        public static Dictionary<string, object> Fields(object o) => Fields(o, 0);

        private static Dictionary<string, object> Fields(object o, int depth)
        {
            var d = new Dictionary<string, object>();
            if (o == null) return d;
            for (var t = o.GetType(); t != null && !IsUnityBase(t); t = t.BaseType)
            {
                foreach (var f in t.GetFields(Declared))
                {
                    object v;
                    try { v = Plain(f.GetValue(o), depth); }
                    catch (Exception) { continue; }
                    if (ReferenceEquals(v, Skip)) continue;
                    var name = FieldName(f);
                    if (d.ContainsKey(name)) name = t.Name + "." + name;
                    d[name] = v;
                }
            }
            return d;
        }

        private static bool IsUnityBase(Type t) =>
            t == typeof(object) || t == typeof(ValueType) || t == typeof(MonoBehaviour) || t == typeof(Behaviour) ||
            t == typeof(Component) || t == typeof(ScriptableObject) || t == typeof(UnityEngine.Object);

        private static string FieldName(FieldInfo f)
        {
            var n = f.Name;
            // "<Name>k__BackingField" -> "Name"
            if (n.Length > 2 && n[0] == '<')
            {
                var close = n.IndexOf('>');
                if (close > 1) return n.Substring(1, close - 1);
            }
            return n;
        }

        /// <summary>The value as plain data, or <see cref="Skip"/>.</summary>
        private static object Plain(object v, int depth)
        {
            switch (v)
            {
                case null: return null;
                case UnityEngine.Object uo: return uo != null ? uo.name : null;
                case string _:
                case bool _:
                case int _:
                case long _:
                case float _:
                case double _:
                case uint _:
                case ulong _:
                    return v;
                case byte b: return (int)b;
                case sbyte sb: return (int)sb;
                case short sh: return (int)sh;
                case ushort us: return (int)us;
                case char c: return c.ToString();
                case Vector2 _:
                case Vector3 _:
                    return v;
                case Vector4 v4: return new[] { v4.x, v4.y, v4.z, v4.w };
                case Color col: return new[] { col.r, col.g, col.b, col.a };
                case Delegate _: return Skip;
            }
            var t = v.GetType();
            if (t.IsEnum) return v.ToString();
            if (v is IList list && !(v is IDictionary))
            {
                var items = new List<object>(Math.Min(list.Count, MaxItems));
                foreach (var x in list)
                {
                    if (items.Count >= MaxItems) break;
                    var p = Plain(x, depth + 1);
                    if (ReferenceEquals(p, Skip)) return Skip;
                    items.Add(p);
                }
                return items;
            }
            if (t.IsValueType && depth < 2 && t.IsSerializable) return Fields(v, depth + 1);
            return Skip;
        }
    }
}
