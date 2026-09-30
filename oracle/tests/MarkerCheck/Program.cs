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
        // Placement: 12 px cells at 720p (3 px of a 320 px thumbnail), 13 at 768 (12.8 rounds up), 18 at 1080p.
        MarkerCode.Place(1280, 720, 1, MarkerCode.DefaultCell(720), out var x, out var y);
        Check(MarkerCode.DefaultCell(720) == 12 && x == 1100 && y == 12, $"1280x720 tr: cell 12 at ({x}, {y})");
        MarkerCode.Place(1920, 1080, 2, MarkerCode.DefaultCell(1080), out x, out y);
        Check(MarkerCode.DefaultCell(1080) == 18 && x == 18 && y == 990, $"1920x1080 bl: cell 18 at ({x}, {y})");
        MarkerCode.Place(1366, 768, 1, MarkerCode.DefaultCell(768), out x, out y);
        Check(MarkerCode.DefaultCell(768) == 13 && x == 1171 && y == 13, $"1366x768 tr: cell 13 at ({x}, {y})");
        MarkerCode.Place(1600, 900, 3, MarkerCode.DefaultCell(900), out x, out y);
        Check(MarkerCode.DefaultCell(900) == 15 && x == 1375 && y == 825, $"1600x900 br: cell 15 at ({x}, {y})");
        Console.WriteLine(fails == 0 ? "ALL OK" : $"{fails} FAILED");
        return fails == 0 ? 0 : 1;
    }
}
