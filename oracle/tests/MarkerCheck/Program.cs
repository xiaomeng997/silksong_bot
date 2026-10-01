using System;
using System.Text;
using SsOracle.Export;

/// <summary>
/// The frame marker's code (MarkerCode) against the vectors that brain/tests/test_marker.py also pins
/// brain/ssbot/record/marker.py to: the patterns of some frame numbers (rows top to bottom, 1 = white, border
/// included), CRC-4 values, and the placement in two corners. The in-game counterpart is the M1 alignment probe
/// (brain/ssbot/probes/m1_align.py), which decodes the marker from the captured images.
/// </summary>
internal static class Program
{
    private static int fails;

    private static void Check(bool ok, string what)
    {
        if (!ok) fails++;
        Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    }

    // Same table as brain/tests/test_marker.py::VECTORS.
    private static readonly (long Frame, string Rows)[] Vectors =
    {
        (0, "00000000000000|01000000000000|00000000000010|00000000000000"),
        (1, "00000000000000|01100000000000|00000000110010|00000000000000"),
        (12345, "00000000000000|01100111000000|00001100100010|00000000000000"),
        (65535, "00000000000000|01111111111100|00111111110010|00000000000000"),
        (70000, "00000000000000|01000011101000|00001000101010|00000000000000"),
        (2600000, "00000000000000|01000000100000|00110101000110|00000000000000"),
    };

    private static string Pattern(long frame)
    {
        var white = new bool[MarkerCode.GridW * MarkerCode.GridH];
        MarkerCode.Fill(frame, white);
        var sb = new StringBuilder();
        for (var gr = 0; gr < MarkerCode.GridH; gr++)
        {
            if (gr > 0) sb.Append('|');
            for (var gc = 0; gc < MarkerCode.GridW; gc++) sb.Append(white[gr * MarkerCode.GridW + gc] ? '1' : '0');
        }
        return sb.ToString();
    }

    private static int Main()
    {
        foreach (var (frame, rows) in Vectors)
        {
            var got = Pattern(frame);
            Check(got == rows, $"pattern of frame {frame}: {got}");
        }
        int[] values = { 0, 1, 2, 0x8000, 0xFFFF, 12345, 4464 };
        int[] crcs = { 0, 3, 6, 3, 3, 1, 5 };
        for (var i = 0; i < values.Length; i++)
            Check(MarkerCode.Crc4(values[i]) == crcs[i], $"crc4({values[i]}) = {MarkerCode.Crc4(values[i])}");
        // Placement (brain/ssbot/vision/mask.py; the same table in brain/tests/test_marker.py): max(3, round(h / 270))
        // px cells, 3 at 720p, 768 (2.84 rounds up) and 900, 4 at 1080p, 5 at 1440p, 8 at 2160p, 3 at least.
        MarkerCode.Place(1280, 720, 1, MarkerCode.DefaultCell(720), out var x, out var y);
        Check(MarkerCode.DefaultCell(720) == 3 && x == 1235 && y == 3, $"1280x720 tr: cell 3 at ({x}, {y})");
        MarkerCode.Place(1920, 1080, 2, MarkerCode.DefaultCell(1080), out x, out y);
        Check(MarkerCode.DefaultCell(1080) == 4 && x == 4 && y == 1060, $"1920x1080 bl: cell 4 at ({x}, {y})");
        MarkerCode.Place(1366, 768, 1, MarkerCode.DefaultCell(768), out x, out y);
        Check(MarkerCode.DefaultCell(768) == 3 && x == 1321 && y == 3, $"1366x768 tr: cell 3 at ({x}, {y})");
        MarkerCode.Place(1600, 900, 3, MarkerCode.DefaultCell(900), out x, out y);
        Check(MarkerCode.DefaultCell(900) == 3 && x == 1555 && y == 885, $"1600x900 br: cell 3 at ({x}, {y})");
        MarkerCode.Place(2560, 1440, 1, MarkerCode.DefaultCell(1440), out x, out y);
        Check(MarkerCode.DefaultCell(1440) == 5 && x == 2485 && y == 5, $"2560x1440 tr: cell 5 at ({x}, {y})");
        MarkerCode.Place(3840, 2160, 1, MarkerCode.DefaultCell(2160), out x, out y);
        Check(MarkerCode.DefaultCell(2160) == 8 && x == 3720 && y == 8, $"3840x2160 tr: cell 8 at ({x}, {y})");
        Check(MarkerCode.DefaultCell(360) == 3, $"640x360: cell {MarkerCode.DefaultCell(360)} (the minimum)");
        Console.WriteLine(fails == 0 ? "ALL OK" : $"{fails} FAILED");
        return fails == 0 ? 0 : 1;
    }
}
