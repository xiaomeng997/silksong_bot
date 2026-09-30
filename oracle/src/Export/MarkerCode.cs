using System;

namespace SsOracle.Export
{
    /// <summary>
    /// The frame marker's code and placement (DESIGN §3.1.4 C4), without Unity: FrameMarker draws it,
    /// brain/ssbot/record/marker.py decodes it, and oracle/tests/MarkerCheck and brain/tests/test_marker.py pin both
    /// to the same vectors. A (Rows + 2) x (Cols + 2) grid of square cells with a one-cell black border; grid row gr
    /// (top to bottom), column gc (left to right), true = white:
    /// <list type="bullet">
    /// <item>border (gr 0 or Rows + 1, gc 0 or Cols + 1): black</item>
    /// <item>gc 1: gr 1 white, gr 2 black; gc Cols: gr 1 black, gr 2 white (sync)</item>
    /// <item>gc 2 .. Cols - 1: bit j = (gc - 2) + (gr - 1) * (Cols - 2); j 0 .. 15 = the frame number's bits (LSB
    /// first, the frame modulo 65536), j 16 .. 19 = Crc4 of those 16 bits</item>
    /// </list>
    /// </summary>
    internal static class MarkerCode
    {
        public const int Rows = 2, Cols = 12, DataBits = 16, CheckBits = 4;
        public const int GridW = Cols + 2, GridH = Rows + 2;

        /// <summary>CRC-4 (x^4 + x + 1, init 0, no reflection) of the DataBits low bits, MSB first.</summary>
        public static int Crc4(int value)
        {
            var crc = 0;
            for (var i = DataBits - 1; i >= 0; i--)
            {
                var fb = ((crc >> 3) & 1) ^ ((value >> i) & 1);
                crc = (crc << 1) & 0xF;
                if (fb != 0) crc ^= 0x3;
            }
            return crc;
        }

        /// <summary>white[gr * GridW + gc] for the pattern of `frame` (the array is reused: no allocation).</summary>
        public static void Fill(long frame, bool[] white)
        {
            Array.Clear(white, 0, white.Length);
            white[1 * GridW + 1] = true;
            white[2 * GridW + Cols] = true;
            var v = (int)(frame & ((1 << DataBits) - 1));
            var crc = Crc4(v);
            for (var j = 0; j < DataBits + CheckBits; j++)
            {
                var bit = j < DataBits ? (v >> j) & 1 : (crc >> (j - DataBits)) & 1;
                white[(1 + j / (Cols - 2)) * GridW + 2 + j % (Cols - 2)] = bit != 0;
            }
        }

        /// <summary>Default cell size: 3 px of a 320 px wide thumbnail of a 16:9 client (12 px at 720p, 18 at
        /// 1080p). Math.Round rounds half to even, as Python's round does.</summary>
        public static int DefaultCell(int screenHeight) => Math.Max(4, (int)Math.Round(screenHeight / 60.0));

        /// <summary>Top-left corner (client px, top-left origin) of the grid in corner 0 tl, 1 tr, 2 bl, 3 br,
        /// `cell` px in from both edges.</summary>
        public static void Place(int screenW, int screenH, int corner, int cell, out int x0, out int y0)
        {
            x0 = (corner & 1) == 0 ? cell : screenW - cell - GridW * cell;
            y0 = (corner & 2) == 0 ? cell : screenH - cell - GridH * cell;
        }
    }
}
