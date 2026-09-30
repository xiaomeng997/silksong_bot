using System;
using System.Globalization;
using System.Reflection;

namespace SsOracle.Train
{
    /// <summary>
    /// Training-only: read or set a primitive PlayerData field by name (e.g. to give rosaries while preparing
    /// a probe save). Main thread only. Never used in evaluation runs.
    /// </summary>
    internal static class PlayerDataEdit
    {
        public static string Get(string name)
        {
            var (pd, field, error) = Resolve(name);
            if (error != null) return error;
            return Convert.ToString(field.GetValue(pd), CultureInfo.InvariantCulture);
        }

        public static string Set(string name, string value)
        {
            var (pd, field, error) = Resolve(name);
            if (error != null) return error;
            object parsed;
            try
            {
                parsed = field.FieldType.IsEnum
                    ? Enum.Parse(field.FieldType, value)
                    : Convert.ChangeType(value, field.FieldType, CultureInfo.InvariantCulture);
            }
            catch (Exception e)
            {
                return $"err cannot parse '{value}' as {field.FieldType.Name}: {e.Message}";
            }
            var old = field.GetValue(pd);
            field.SetValue(pd, parsed);
            Core.Plugin.Log.LogWarning($"PlayerData.{name}: {old} -> {parsed} (training edit)");
            return "ok";
        }

        private static (PlayerData, FieldInfo, string) Resolve(string name)
        {
            var gm = GameManager._instance;
            var pd = gm != null ? gm.playerData : null;
            if (pd == null) return (null, null, "err no PlayerData (not in a game)");
            var field = typeof(PlayerData).GetField(name, BindingFlags.Instance | BindingFlags.Public);
            if (field == null) return (null, null, $"err PlayerData has no public field '{name}'");
            var t = field.FieldType;
            if (!(t.IsPrimitive || t.IsEnum || t == typeof(string)))
                return (null, null, $"err '{name}' is {t.Name}, not a primitive");
            return (pd, field, null);
        }
    }
}
