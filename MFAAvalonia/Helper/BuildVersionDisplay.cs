using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace MFAAvalonia.Helper;

/// <summary>Human-readable build identity, separate from update/protocol version numbers.</summary>
public static class BuildVersionDisplay
{
    public static string GetDisplayVersion(string compatibilityVersion, string selfBuildFormat)
    {
        var assembly = typeof(BuildVersionDisplay).Assembly;
        var label = assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(attribute => attribute.Key == "MfaBuildLabel")?.Value;
        var explicitLabel = !string.IsNullOrWhiteSpace(label);
        string? manifest = null;
        if (string.IsNullOrWhiteSpace(label))
        {
            try
            {
                var path = Path.Combine(AppContext.BaseDirectory, "mfaa-build.json");
                if (File.Exists(path) && new FileInfo(path).Length <= 65536)
                    manifest = File.ReadAllText(path);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        var information = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
        label = ResolveLabel(label, information, manifest);
        return label == null ? compatibilityVersion : explicitLabel
            ? string.Format(CultureInfo.CurrentCulture, selfBuildFormat, label) : label;
    }

    internal static string? ResolveLabel(string? explicitLabel, string? informationalVersion, string? manifest)
    {
        if (!string.IsNullOrWhiteSpace(explicitLabel))
            return explicitLabel.Trim();
        if (string.IsNullOrWhiteSpace(manifest))
            return null;
        try
        {
            using var document = JsonDocument.Parse(manifest);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("schema", out var schema)
                || schema.ValueKind != JsonValueKind.Number || !schema.TryGetInt32(out var schemaVersion) || schemaVersion != 1)
                return null;
            var repository = ReadString(root, "repository");
            var commit = ReadString(root, "commit");
            var shortCommit = ReadString(root, "short_commit");
            var tag = ReadString(root, "tag");
            if (string.IsNullOrWhiteSpace(repository)
                || repository.Equals("MaaXYZ/MFAAvalonia", StringComparison.OrdinalIgnoreCase)
                || commit == null || !Regex.IsMatch(commit, "\\A[0-9a-f]{40}\\z")
                || shortCommit != commit[..6] || tag == null || tag.Length > 128
                || !Regex.IsMatch(tag, "\\Av[0-9A-Za-z.+-]+\\z")
                || !tag.EndsWith($".g{shortCommit}", StringComparison.Ordinal)
                // Ignore a stale fork manifest after the client has been replaced by an official build.
                || informationalVersion == null || !informationalVersion.EndsWith($"+{commit}", StringComparison.OrdinalIgnoreCase))
                return null;
            return FormatPackageLabel(repository, ReadString(root, "upstream_tag"), tag, shortCommit!);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string FormatPackageLabel(string repository, string? upstreamVersion, string tag, string shortCommit)
    {
        if (!repository.Equals("sunyink/MFAAvalonia", StringComparison.OrdinalIgnoreCase) || upstreamVersion == null)
            return tag;
        var version = Regex.Match(upstreamVersion,
            "\\Av(?<base>[0-9]+\\.[0-9]+\\.[0-9]+)(?:-(?<pre>[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?\\z");
        if (!version.Success || tag != $"v{version.Groups["base"].Value}-mfbd2.g{shortCommit}")
            return tag;
        var prerelease = version.Groups["pre"].Value;
        var suffix = string.IsNullOrEmpty(prerelease) ? "" : $".{prerelease}";
        // The upstream prerelease identifies the source baseline, not a fork counter.
        // This label never enters the updater or PI_CLIENT_VERSION.
        return $"v{version.Groups["base"].Value}-MFABD2{suffix} · {shortCommit}";
    }

    private static string? ReadString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}
