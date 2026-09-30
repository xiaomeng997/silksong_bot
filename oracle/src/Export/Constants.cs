using System;
using System.Globalization;
using System.Reflection;
using System.Text;
using UnityEngine;

namespace SsOracle.Export
{
    /// <summary>
    /// P11: dump serialized tuning values that are not visible in the decompiled code (prefab values),
    /// plus engine timing settings. Main thread only.
    /// </summary>
    internal static class ConstantsDump
    {
        public static string Build()
        {
            var inv = CultureInfo.InvariantCulture;
            var sb = new StringBuilder(8192);
            sb.Append("{\"engine\":{");
            sb.Append("\"fixedDeltaTime\":").Append(Time.fixedDeltaTime.ToString("R", inv));
            sb.Append(",\"maximumDeltaTime\":").Append(Time.maximumDeltaTime.ToString("R", inv));
            sb.Append(",\"targetFrameRate\":").Append(Application.targetFrameRate);
            sb.Append(",\"vSyncCount\":").Append(QualitySettings.vSyncCount);
            sb.Append(",\"refreshRate\":").Append(Screen.currentResolution.refreshRateRatio.value.ToString("R", inv));
            sb.Append(",\"screen\":\"").Append(Screen.width).Append('x').Append(Screen.height).Append(' ').Append(Screen.fullScreenMode).Append('"');
            sb.Append(",\"inputUpdateMode\":\"").Append(UnityEngine.InputSystem.InputSystem.settings.updateMode).Append('"');
            sb.Append(",\"defaultButtonPressPoint\":").Append(UnityEngine.InputSystem.InputSystem.settings.defaultButtonPressPoint.ToString("R", inv));
            var icm = UnityEngine.Object.FindAnyObjectByType<InControl.InControlManager>();
            if (icm != null)
                sb.Append(",\"inControlUpdateMode\":\"").Append(icm.updateMode).Append('"');
            sb.Append('}');

            var hero = HeroController.SilentInstance;
            if (hero != null)
            {
                sb.Append(",\"hero\":");
                AppendPrimitiveFields(sb, hero, typeof(HeroController));
            }
            sb.Append('}');
            return sb.ToString();
        }

        // Every instance field of a primitive/enum/string type, public or private, declared on the type.
        private static void AppendPrimitiveFields(StringBuilder sb, object obj, Type type)
        {
            var inv = CultureInfo.InvariantCulture;
            sb.Append('{');
            var first = true;
            foreach (var f in type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly))
            {
                var t = f.FieldType;
                if (!(t.IsPrimitive || t.IsEnum || t == typeof(string))) continue;
                var v = f.GetValue(obj);
                if (!first) sb.Append(',');
                first = false;
                sb.Append('"').Append(f.Name).Append("\":");
                switch (v)
                {
                    case null: sb.Append("null"); break;
                    case bool b: sb.Append(b ? "true" : "false"); break;
                    case float x: sb.Append(float.IsNaN(x) || float.IsInfinity(x) ? "null" : x.ToString("R", inv)); break;
                    case double d: sb.Append(double.IsNaN(d) || double.IsInfinity(d) ? "null" : d.ToString("R", inv)); break;
                    case string s: sb.Append('"').Append(s.Replace("\\", "\\\\").Replace("\"", "\\\"")).Append('"'); break;
                    default:
                        if (t.IsEnum) sb.Append('"').Append(v).Append('"');
                        else sb.Append(Convert.ToString(v, inv));
                        break;
                }
            }
            sb.Append('}');
        }
    }
}
