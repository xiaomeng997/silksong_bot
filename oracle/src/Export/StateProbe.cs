using System.Globalization;
using System.IO;
using System.Text;
using UnityEngine;

namespace SsOracle.Export
{
    /// <summary>
    /// M0 hello-world probe: once per second, append the core game state to a JSONL file.
    /// Replaced by the full per-frame exporter in M1.
    /// </summary>
    internal sealed class StateProbe : MonoBehaviour
    {
        private const float IntervalSeconds = 1f;
        private static readonly string OutPath = @"C:\ssbot\sandbox\oracle_probe.jsonl";

        private float nextWrite;
        private StreamWriter writer;

        private void Start()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(OutPath));
            writer = new StreamWriter(OutPath, append: true, Encoding.UTF8) { AutoFlush = true };
        }

        private void Update()
        {
            if (Time.unscaledTime < nextWrite) return;
            nextWrite = Time.unscaledTime + IntervalSeconds;
            writer.WriteLine(Snapshot());
        }

        private void OnDestroy() => writer?.Dispose();

        private static string Snapshot()
        {
            var inv = CultureInfo.InvariantCulture;
            var sb = new StringBuilder(256);
            sb.Append("{\"t\":").Append(Time.unscaledTime.ToString("F3", inv));
            sb.Append(",\"frame\":").Append(Time.frameCount);
            sb.Append(",\"timeScale\":").Append(Time.timeScale.ToString("F3", inv));
            sb.Append(",\"focused\":").Append(Application.isFocused ? "true" : "false");

            // _instance, not the instance getter: the getter logs an error every call while no GameManager exists.
            var gm = GameManager._instance;
            if (gm == null)
            {
                sb.Append(",\"gm\":null}");
                return sb.ToString();
            }

            sb.Append(",\"state\":\"").Append(gm.GameState).Append('"');
            sb.Append(",\"scene\":\"").Append(gm.sceneName).Append('"');
            sb.Append(",\"playTime\":").Append(gm.PlayTime.ToString("F3", inv));

            var pd = gm.playerData;
            if (pd != null)
            {
                sb.Append(",\"hp\":").Append(pd.health).Append(",\"hpMax\":").Append(pd.maxHealth);
                sb.Append(",\"hpBlue\":").Append(pd.healthBlue);
                sb.Append(",\"silk\":").Append(pd.silk).Append(",\"silkMax\":").Append(pd.silkMax);
                sb.Append(",\"geo\":").Append(pd.geo);
                sb.Append(",\"permadeath\":\"").Append(pd.permadeathMode).Append('"');
                sb.Append(",\"savedPlayTime\":").Append(pd.playTime.ToString("F3", inv));
                sb.Append(",\"disablePause\":").Append(pd.disablePause ? "true" : "false");
                sb.Append(",\"disableSaveQuit\":").Append(pd.disableSaveQuit ? "true" : "false");
            }

            var hero = HeroController.SilentInstance;
            if (hero != null)
            {
                var p = hero.transform.position;
                sb.Append(",\"hero\":[").Append(p.x.ToString("F3", inv)).Append(',').Append(p.y.ToString("F3", inv)).Append(']');
                sb.Append(",\"onGround\":").Append(hero.cState.onGround ? "true" : "false");
                sb.Append(",\"invuln\":").Append(hero.cState.Invulnerable ? "true" : "false");
            }

            sb.Append('}');
            return sb.ToString();
        }
    }
}
