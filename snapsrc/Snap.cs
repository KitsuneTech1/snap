// Snap.cs - native fast screenshot for agents. Compiles to snap.exe with .NET Framework csc.
// No PowerShell start-up, no per-run JIT: about 60-90 ms vs ~490 ms for the .ps1.
// Read-only: never clicks, types, moves, restores or focuses a window.
// Build: build.cmd (csc /target:exe /out:..\snap.exe ...). OCR stays in ocr.ps1 (WinRT).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

static class Snap {
  [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);
  [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int v, int size);
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }

  class Win { public IntPtr h; public string title; public string proc; public int x, y, w, hgt; public bool min; }

  static readonly string[] Terminals = {
    "WindowsTerminal","OpenConsole","conhost","pwsh","powershell","cmd","mintty","Code","Cursor","wezterm-gui","alacritty" };

  static string Esc(string s) {
    if (s == null) return "";
    StringBuilder b = new StringBuilder();
    foreach (char c in s) {
      if (c == '"' || c == '\\') { b.Append('\\'); b.Append(c); }
      else if (c == '\n') b.Append("\\n");
      else if (c == '\r') b.Append("\\r");
      else if (c == '\t') b.Append("\\t");
      else if (c < 32) b.Append("\\u").Append(((int)c).ToString("x4"));
      else b.Append(c);
    }
    return b.ToString();
  }

  static Win Info(IntPtr h) {
    StringBuilder sb = new StringBuilder(512);
    GetWindowText(h, sb, 512);
    uint pid; GetWindowThreadProcessId(h, out pid);
    string name = "";
    try { name = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName; } catch { }
    RECT r;
    if (DwmGetWindowAttribute(h, 9, out r, 16) != 0) GetWindowRect(h, out r); // extended frame bounds
    return new Win { h = h, title = sb.ToString(), proc = name, x = r.Left, y = r.Top,
      w = r.Right - r.Left, hgt = r.Bottom - r.Top, min = IsIconic(h) };
  }

  static List<Win> TopWindows() {
    List<Win> outp = new List<Win>();
    EnumWindows(delegate (IntPtr h, IntPtr l) {
      if (!IsWindowVisible(h)) return true;
      int cloaked = 0; DwmGetWindowAttribute(h, 14, out cloaked, 4); // on another virtual desktop
      if (cloaked != 0) return true;
      Win w = Info(h);
      if (string.IsNullOrEmpty(w.title)) return true;
      if (!w.min && (w.w <= 80 || w.hgt <= 60)) return true;
      if (w.proc == "TextInputHost" || w.proc == "ShellExperienceHost" || w.proc == "SearchHost" || w.proc == "StartMenuExperienceHost") return true;
      outp.Add(w);
      return true;
    }, IntPtr.Zero);
    return outp;
  }

  static string MonitorsJson() {
    StringBuilder b = new StringBuilder("[");
    bool first = true;
    foreach (Screen s in Screen.AllScreens) {
      if (!first) b.Append(",");
      first = false;
      b.Append("\"").Append(s.Primary ? "primary" : "screen").Append(" ")
       .Append(s.Bounds.Width).Append("x").Append(s.Bounds.Height).Append("@")
       .Append(s.Bounds.X).Append(",").Append(s.Bounds.Y).Append("\"");
    }
    b.Append("]");
    return b.ToString();
  }

  [STAThread]
  static int Main(string[] args) {
    long t0 = DateTime.UtcNow.Ticks;
    if (!SetProcessDpiAwarenessContext((IntPtr)(-4))) SetProcessDPIAware();

    string mode = "auto", app = null, region = null, outPath = null;
    bool list = false; int maxWidth = 1600;
    for (int i = 0; i < args.Length; i++) {
      string a = args[i].ToLowerInvariant();
      if (a == "-list") list = true;
      else if (a == "-app" && i + 1 < args.Length) app = args[++i];
      else if (a == "-region" && i + 1 < args.Length) region = args[++i];
      else if (a == "-mode" && i + 1 < args.Length) mode = args[++i].ToLowerInvariant();
      else if (a == "-maxwidth" && i + 1 < args.Length) int.TryParse(args[++i], out maxWidth);
      else if (a == "-out" && i + 1 < args.Length) outPath = args[++i];
    }

    if (list) {
      StringBuilder b = new StringBuilder("[");
      bool first = true;
      foreach (Win w in TopWindows()) {
        Rectangle mb = Screen.FromHandle(w.h).Bounds;
        if (!first) b.Append(",");
        first = false;
        b.Append("{\"title\":\"").Append(Esc(w.title)).Append("\",\"process\":\"").Append(Esc(w.proc))
         .Append("\",\"x\":").Append(w.x).Append(",\"y\":").Append(w.y).Append(",\"width\":").Append(w.w)
         .Append(",\"height\":").Append(w.hgt).Append(",\"minimized\":").Append(w.min ? "true" : "false")
         .Append(",\"monitor\":\"").Append(mb.Width).Append("x").Append(mb.Height).Append("@").Append(mb.X).Append(",").Append(mb.Y).Append("\"}");
      }
      b.Append("]");
      Console.WriteLine(b.ToString());
      return 0;
    }

    Win fg = Info(GetForegroundWindow());
    Win target = fg;
    string used = mode;
    int x = 0, y = 0, w2 = 0, h2 = 0;
    Bitmap bmp = null;

    if (app != null) {
      string needle = app.ToLowerInvariant();
      Win hit = null; long best = -1; Win minHit = null;
      foreach (Win win in TopWindows()) {
        bool match = win.title.ToLowerInvariant().Contains(needle) || win.proc.ToLowerInvariant().Contains(needle);
        if (!match) continue;
        if (win.min) { if (minHit == null) minHit = win; continue; }
        long area = (long)win.w * win.hgt;
        if (area > best) { best = area; hit = win; }
      }
      if (hit == null) {
        string why = minHit != null
          ? "window '" + Esc(app) + "' is minimized; snap never restores windows"
          : "no visible window matches '" + Esc(app) + "'; run -List";
        Console.WriteLine("{\"error\":\"" + why + "\",\"monitors\":" + MonitorsJson() + "}");
        return 2;
      }
      target = hit; x = hit.x; y = hit.y; w2 = hit.w; h2 = hit.hgt; used = "app";
      Bitmap full = new Bitmap(w2, h2);
      using (Graphics g = Graphics.FromImage(full)) {
        IntPtr hdc = g.GetHdc();
        bool ok = PrintWindow(hit.h, hdc, 2); // PW_RENDERFULLCONTENT: draw even when covered
        g.ReleaseHdc(hdc);
        if (ok) bmp = full; else { full.Dispose(); used = "app-screen"; }
      }
    } else if (region != null) {
      string[] p = region.Split(',');
      x = int.Parse(p[0].Trim()); y = int.Parse(p[1].Trim());
      w2 = int.Parse(p[2].Trim()); h2 = int.Parse(p[3].Trim());
      used = "region";
    } else {
      if (mode == "auto") { used = "monitor"; foreach (string t in Terminals) if (t == fg.proc) { used = "all"; break; } }
      if (used == "window") { x = fg.x; y = fg.y; w2 = fg.w; h2 = fg.hgt; }
      else if (used == "all") { Rectangle v = SystemInformation.VirtualScreen; x = v.X; y = v.Y; w2 = v.Width; h2 = v.Height; }
      else { Rectangle b = Screen.FromHandle(fg.h).Bounds; x = b.X; y = b.Y; w2 = b.Width; h2 = b.Height; }
    }

    if (w2 <= 0 || h2 <= 0) {
      Rectangle b = Screen.PrimaryScreen.Bounds;
      x = b.X; y = b.Y; w2 = b.Width; h2 = b.Height; used += "-fallback";
    }
    if (bmp == null) {
      bmp = new Bitmap(w2, h2);
      using (Graphics g = Graphics.FromImage(bmp)) g.CopyFromScreen(x, y, 0, 0, bmp.Size);
    }
    if (maxWidth > 0 && bmp.Width > maxWidth) {
      int nw = maxWidth, nh = (int)Math.Round(bmp.Height * (double)maxWidth / bmp.Width);
      Bitmap small = new Bitmap(nw, nh);
      using (Graphics g = Graphics.FromImage(small)) { g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.DrawImage(bmp, 0, 0, nw, nh); }
      bmp.Dispose(); bmp = small;
    }

    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"Temp\claude-snaps");
    if (outPath == null) {
      Directory.CreateDirectory(dir);
      outPath = Path.Combine(dir, "snap-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + ".png");
    }
    bmp.Save(outPath, ImageFormat.Png);
    int sw = bmp.Width, sh = bmp.Height;
    bmp.Dispose();

    try {
      if (Directory.Exists(dir)) {
        List<FileInfo> snaps = new List<FileInfo>(new DirectoryInfo(dir).GetFiles("snap-*.png"));
        snaps.Sort(delegate (FileInfo a, FileInfo b) { return b.LastWriteTimeUtc.CompareTo(a.LastWriteTimeUtc); });
        for (int i = 30; i < snaps.Count; i++) {
          try { snaps[i].Delete(); } catch { }
          try { File.Delete(snaps[i].FullName + ".ocr.json"); } catch { }
        }
      }
    } catch { }

    long ms = (DateTime.UtcNow.Ticks - t0) / 10000;
    StringBuilder o = new StringBuilder();
    o.Append("{\"path\":\"").Append(Esc(outPath)).Append("\",\"mode\":\"").Append(used)
     .Append("\",\"x\":").Append(x).Append(",\"y\":").Append(y).Append(",\"width\":").Append(w2).Append(",\"height\":").Append(h2)
     .Append(",\"saved_width\":").Append(sw).Append(",\"saved_height\":").Append(sh)
     .Append(",\"title\":\"").Append(Esc(target.title)).Append("\",\"process\":\"").Append(Esc(target.proc))
     .Append("\",\"front\":\"").Append(Esc(fg.title)).Append("\",\"monitors\":").Append(MonitorsJson())
     .Append(",\"ms\":").Append(ms.ToString(CultureInfo.InvariantCulture)).Append("}");
    Console.WriteLine(o.ToString());
    return 0;
  }
}
