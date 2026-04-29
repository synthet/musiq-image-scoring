using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;

namespace WebUILauncher;

internal static class Program
{
    private enum LaunchMode
    {
        Wsl,
        WslLocal,
        WindowsNative,
        Docker,
        DockerRebuild,
        DockerRefresh,
    }

    /// <summary>How to open the WebUI after the server is reachable (launch.py / docker batch).</summary>
    private enum OpenUiKind
    {
        Browser,
        Electron,
        None,
    }

    private static int Main(string[] args)
    {
        var baseDir = NormalizeDir(AppContext.BaseDirectory);
        if (string.IsNullOrEmpty(baseDir) || !Directory.Exists(baseDir))
        {
            Console.Error.WriteLine("Error: could not resolve launcher directory.");
            return 1;
        }

        if (!TryParseArgs(args, out var mode, out var forward, out var openUi, out var error, out var helpRequested))
        {
            if (helpRequested)
            {
                PrintHelp();
                return 0;
            }

            if (!string.IsNullOrEmpty(error))
                Console.Error.WriteLine(error);
            PrintHelp();
            return 1;
        }

        var batchRelative = mode switch
        {
            LaunchMode.Wsl => "run_webui.bat",
            LaunchMode.WslLocal => "run_webui_local.bat",
            LaunchMode.WindowsNative => "run_webui_windows.bat",
            LaunchMode.Docker => "run_webui_docker.bat",
            LaunchMode.DockerRebuild => "docker_rebuild.bat",
            LaunchMode.DockerRefresh => "docker_refresh_webui.bat",
            _ => throw new InvalidOperationException(),
        };

        var batchPath = Path.Combine(baseDir, batchRelative);
        if (!File.Exists(batchPath))
        {
            Console.Error.WriteLine("Error: expected file next to RunWebUI.exe:");
            Console.Error.WriteLine("  " + batchPath);
            return 1;
        }

        InjectWebUiOpenArg(forward, mode, openUi);
        return RunCmdBatch(batchPath, forward, baseDir, mode, openUi);
    }

    private static void InjectWebUiOpenArg(List<string> forward, LaunchMode mode, OpenUiKind openUi)
    {
        if (mode is LaunchMode.Docker or LaunchMode.DockerRebuild or LaunchMode.DockerRefresh)
            return;

        var value = openUi switch
        {
            OpenUiKind.Browser => "browser",
            OpenUiKind.Electron => "electron",
            OpenUiKind.None => "none",
            _ => "browser",
        };
        forward.Insert(0, "--webui-open=" + value);
    }

    private static bool TryParseArgs(
        string[] args,
        out LaunchMode mode,
        out List<string> forward,
        out OpenUiKind openUi,
        out string error,
        out bool helpRequested)
    {
        mode = LaunchMode.Wsl;
        forward = new List<string>();
        openUi = OpenUiKind.Browser;
        error = "";
        helpRequested = false;

        var i = 0;
        LaunchMode? explicitMode = null;
        OpenUiKind? explicitOpen = null;

        while (i < args.Length)
        {
            var a = args[i];
            if (a == "--help" || a == "-h" || a == "/?" || string.Equals(a, "help", StringComparison.OrdinalIgnoreCase))
            {
                helpRequested = true;
                return false;
            }

            if (a == "--")
            {
                i++;
                while (i < args.Length)
                {
                    forward.Add(args[i]);
                    i++;
                }

                break;
            }

            if (a.StartsWith("--", StringComparison.Ordinal))
            {
                switch (a)
                {
                    case "--browser":
                        if (explicitOpen != null && explicitOpen != OpenUiKind.Browser)
                        {
                            error = "Conflicting UI flags: use only one of --browser, --electron, --no-open.";
                            return false;
                        }

                        explicitOpen = OpenUiKind.Browser;
                        i++;
                        continue;
                    case "--electron":
                        if (explicitOpen != null && explicitOpen != OpenUiKind.Electron)
                        {
                            error = "Conflicting UI flags: use only one of --browser, --electron, --no-open.";
                            return false;
                        }

                        explicitOpen = OpenUiKind.Electron;
                        i++;
                        continue;
                    case "--no-open":
                        if (explicitOpen != null && explicitOpen != OpenUiKind.None)
                        {
                            error = "Conflicting UI flags: use only one of --browser, --electron, --no-open.";
                            return false;
                        }

                        explicitOpen = OpenUiKind.None;
                        i++;
                        continue;
                }

                var nextMode = a switch
                {
                    "--wsl" => LaunchMode.Wsl,
                    "--local" => LaunchMode.WslLocal,
                    "--wsl-local" => LaunchMode.WslLocal,
                    "--windows" => LaunchMode.WindowsNative,
                    "--docker" => LaunchMode.Docker,
                    "--docker-rebuild" => LaunchMode.DockerRebuild,
                    "--docker-refresh" => LaunchMode.DockerRefresh,
                    _ => (LaunchMode?)null,
                };

                if (nextMode == null)
                {
                    error = "Unknown option: " + a + " (use -- before arguments for launch.py)";
                    return false;
                }

                if (explicitMode != null && explicitMode != nextMode)
                {
                    error = "Conflicting mode flags (use only one of --wsl, --local, --windows, --docker, --docker-rebuild, --docker-refresh).";
                    return false;
                }

                explicitMode = nextMode;
                i++;
                continue;
            }

            forward.Add(a);
            i++;
        }

        mode = explicitMode ?? LaunchMode.Wsl;
        openUi = explicitOpen ?? OpenUiKind.Browser;
        if (mode == LaunchMode.DockerRebuild)
            openUi = OpenUiKind.None;
        return true;
    }

    private static void PrintHelp()
    {
        var sb = new StringBuilder();
        sb.AppendLine("RunWebUI - start the Vexlum WebUI");
        sb.AppendLine();
        sb.AppendLine("Usage: RunWebUI.exe [options] [--] [extra args for launch.py ...]");
        sb.AppendLine("       Use -- before launch.py flags that start with \"--\".");
        sb.AppendLine();
        sb.AppendLine("Modes (default: --wsl):");
        sb.AppendLine("  --wsl              WSL + ~/.venvs/tf + launch.py (same as run_webui.bat)");
        sb.AppendLine("  --local            WSL + local Firebird file access (run_webui_local.bat)");
        sb.AppendLine("  --windows          Native Windows .venv + launch.py (run_webui_windows.bat)");
        sb.AppendLine("  --docker           docker compose up -d, wait for :7860, tail logs");
        sb.AppendLine("  --docker-rebuild   docker compose down, build --no-cache, docker compose up");
        sb.AppendLine("  --docker-refresh   npm build frontend, rebuild webui image, up -d webui (keeps Postgres data)");
        sb.AppendLine();
        sb.AppendLine("After start (default: open in browser):");
        sb.AppendLine("  --browser          Open http://127.0.0.1:<port>/ui/ in the default browser (default)");
        sb.AppendLine("  --electron         Open the WebUI in an Electron window (sibling image-scoring-gallery)");
        sb.AppendLine("  --no-open          Do not open a window automatically");
        sb.AppendLine();
        sb.AppendLine("  -h, --help         Show this help");
        sb.AppendLine();
        sb.AppendLine("Place RunWebUI.exe in the repository root (next to the .bat launchers).");
        Console.WriteLine(sb.ToString());
    }

    private static int RunCmdBatch(
        string batchPath,
        List<string> forwardArgs,
        string workingDirectory,
        LaunchMode mode,
        OpenUiKind openUi)
    {
        var argLine = BuildCmdArgumentLine(forwardArgs);
        var inner = "\"" + batchPath + "\"" + (argLine.Length > 0 ? " " + argLine : "");

        var psi = new ProcessStartInfo
        {
            FileName = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe",
            Arguments = "/c " + inner,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
        };

        if (mode is LaunchMode.Docker or LaunchMode.DockerRefresh)
        {
            psi.EnvironmentVariables["WEBUI_OPEN_UI"] = openUi switch
            {
                OpenUiKind.Electron => "electron",
                OpenUiKind.None => "none",
                _ => "browser",
            };
        }

        try
        {
            using var p = Process.Start(psi);
            if (p == null)
            {
                Console.Error.WriteLine("Error: failed to start cmd.exe");
                return 1;
            }

            p.WaitForExit();
            return p.ExitCode;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Error launching: " + ex.Message);
            return 1;
        }
    }

    /// <summary>
    /// Build a single string of arguments safe for <c>cmd.exe /c "batch.cmd" a1 a2</c>.
    /// </summary>
    private static string BuildCmdArgumentLine(IEnumerable<string> args)
    {
        return string.Join(" ", args.Select(CmdEscapeArg));
    }

    private static string CmdEscapeArg(string s)
    {
        if (string.IsNullOrEmpty(s))
            return "\"\"";

        var needsQuotes = s.Any(c => char.IsWhiteSpace(c) || c == '&' || c == '|' || c == '<' || c == '>' || c == '^');
        if (!needsQuotes && s.IndexOf('"') < 0)
            return s;

        return "\"" + s.Replace("\"", "\"\"") + "\"";
    }

    private static string NormalizeDir(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
            return "";
        var p = path!.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        try
        {
            return Path.GetFullPath(p);
        }
        catch
        {
            return p;
        }
    }
}
