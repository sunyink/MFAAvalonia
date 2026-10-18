using System.Text.Json;
using MFAAvalonia.Helper;
using Xunit;

namespace MFAAvalonia.Background.Tests;

public class BuildVersionDisplayTests
{
    private const string Commit = "fb5b805df7c3e152bdacf7727a38356481bd7a45";

    private static string Manifest(string repository = "sunyink/MFAAvalonia", string commit = Commit, string? upstream = "v2.16.3-beta.1") =>
        JsonSerializer.Serialize(new { schema = 1, repository, commit, short_commit = commit[..6], upstream_tag = upstream, tag = $"v2.16.3-mfbd2.g{commit[..6]}" });

    [Fact]
    public void StagedBuildLabelTakesPrecedenceOverAnOlderPackageManifest()
    {
        Assert.Equal("PR260-controls-4e22d1-staged", BuildVersionDisplay.ResolveLabel(
            "PR260-controls-4e22d1-staged", "2.14.0+different-source", Manifest()));
    }

    [Fact]
    public void MatchingForkManifestIdentifiesTheActualClientBuild()
    {
        Assert.Equal("v2.16.3-MFABD2.beta.1 · fb5b80", BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", Manifest()));
    }

    [Theory]
    [InlineData("v2.16.3", "v2.16.3-MFABD2 · fb5b80")]
    [InlineData("v2.16.3-beta.5", "v2.16.3-MFABD2.beta.5 · fb5b80")]
    [InlineData("v2.16.3-rc.2+build.7", "v2.16.3-MFABD2.rc.2 · fb5b80")]
    [InlineData(null, "v2.16.3-mfbd2.gfb5b80")]
    [InlineData("bad version", "v2.16.3-mfbd2.gfb5b80")]
    [InlineData("v2.17.0-beta.1", "v2.16.3-mfbd2.gfb5b80")]
    public void ForkLabelKeepsTheUpstreamBaselineAndSixCharacterSource(string? upstream, string expected)
    {
        Assert.Equal(expected, BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", Manifest(upstream: upstream)));
    }

    [Fact]
    public void StaleForkManifestDoesNotMislabelAReplacementClient()
    {
        Assert.Null(BuildVersionDisplay.ResolveLabel(null, "2.14.0+aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Manifest()));
        Assert.Null(BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", Manifest("MaaXYZ/MFAAvalonia")));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("{\"schema\":\"1\"}")]
    [InlineData("{\"schema\":1,\"commit\":1}")]
    public void MissingOrInvalidBuildMetadataLeavesTheCompatibilityVersionAlone(string? manifest)
    {
        Assert.Null(BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", manifest));
    }
}
