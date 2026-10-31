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
                || schema.ValueKind != JsonValueKind.Number || !schema.TryGetInt32(out var schemaVersion) || schemaVersion is not (1 or 2))
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
                // Ignore a stale fork manifest after the client has been replaced by an official build.
                || informationalVersion == null || !informationalVersion.EndsWith($"+{commit}", StringComparison.OrdinalIgnoreCase))
                return null;
            int? sequence = root.TryGetProperty("fork_sequence", out var number)
                && number.ValueKind == JsonValueKind.Number && number.TryGetInt32(out var parsed) && parsed > 0
                    ? parsed : null;
            if (schemaVersion == 2)
            {
                var upstream = ReadString(root, "upstream_version");
                if (!repository.Equals("sunyink/MFAAvalonia", StringComparison.OrdinalIgnoreCase)
                    || upstream == null || !Regex.IsMatch(upstream,
                        "\\Av[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?\\z")
                    || sequence == null || tag != $"{upstream}-MFABD2.beta.{sequence}")
                    return null;
                return $"{tag} · {shortCommit}";
            }
            if (!tag.EndsWith($".g{shortCommit}", StringComparison.Ordinal))
                return null;
            return FormatPackageLabel(repository, ReadString(root, "upstream_tag"), tag, shortCommit!, sequence);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string FormatPackageLabel(string repository, string? upstreamVersion, string tag, string shortCommit, int? sequence)
    {
        if (!repository.Equals("sunyink/MFAAvalonia", StringComparison.OrdinalIgnoreCase) || upstreamVersion == null)
            return tag;
        var version = Regex.Match(upstreamVersion,
            "\\Av(?<base>[0-9]+\\.[0-9]+\\.[0-9]+)(?:-(?<pre>[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?\\z");
        if (!version.Success || tag != $"v{version.Groups["base"].Value}-mfbd2.g{shortCommit}" || sequence == null)
            return tag;
        // Historical schema-1 packages used only the numeric baseline. The beta counter is
        // reserved by our own Git tag and shared with the release/package metadata.
        // This label never enters the updater or PI_CLIENT_VERSION.
        return $"v{version.Groups["base"].Value}-MFABD2.beta.{sequence} · {shortCommit}";
    }

    private static string? ReadString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}
