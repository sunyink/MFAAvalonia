using System.Text.Json;
using MFAAvalonia.Helper;
using Xunit;

namespace MFAAvalonia.Background.Tests;

public class BuildVersionDisplayTests
{
    private const string Commit = "fb5b805df7c3e152bdacf7727a38356481bd7a45";

    private static string Manifest(string repository = "sunyink/MFAAvalonia", string commit = Commit,
        string? upstream = "v2.16.3-beta.1", object? sequence = null) =>
        JsonSerializer.Serialize(new { schema = 1, repository, commit, short_commit = commit[..6],
            upstream_tag = upstream, fork_sequence = sequence, tag = $"v2.16.3-mfbd2.g{commit[..6]}" });

    [Fact]
    public void StagedBuildLabelTakesPrecedenceOverAnOlderPackageManifest()
    {
        Assert.Equal("PR260-controls-4e22d1-staged", BuildVersionDisplay.ResolveLabel(
            "PR260-controls-4e22d1-staged", "2.14.0+different-source", Manifest()));
    }

    [Fact]
    public void MatchingForkManifestIdentifiesTheActualClientBuild()
    {
        Assert.Equal("v2.16.3-MFABD2.beta.5 · fb5b80", BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", Manifest(sequence: 5)));
    }

    [Theory]
    [InlineData("v2.16.3", "v2.16.3-MFABD2.beta.7 · fb5b80")]
    [InlineData("v2.16.3-beta.1", "v2.16.3-MFABD2.beta.7 · fb5b80")]
    [InlineData("v2.16.3-beta.5", "v2.16.3-MFABD2.beta.7 · fb5b80")]
    [InlineData("v2.16.3-rc.2+build.7", "v2.16.3-MFABD2.beta.7 · fb5b80")]
    [InlineData(null, "v2.16.3-mfbd2.gfb5b80")]
    [InlineData("bad version", "v2.16.3-mfbd2.gfb5b80")]
    [InlineData("v2.17.0-beta.1", "v2.16.3-mfbd2.gfb5b80")]
    public void ForkLabelUsesOnlyUpstreamNumericVersionAndOurOwnSequence(string? upstream, string expected)
    {
        Assert.Equal(expected, BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", Manifest(upstream: upstream, sequence: 7)));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData("5")]
    [InlineData(true)]
    [InlineData(1.5)]
    [InlineData(2147483648L)]
    public void MissingOrInvalidSequenceDoesNotBorrowTheUpstreamBetaNumber(object? sequence)
    {
        Assert.Equal("v2.16.3-mfbd2.gfb5b80", BuildVersionDisplay.ResolveLabel(
            null, $"2.14.0+{Commit}", Manifest(sequence: sequence)));
    }

    [Fact]
    public void LegacyManifestKeepsItsImmutablePackageTag()
    {
        var manifest = JsonSerializer.Serialize(new { schema = 1, repository = "sunyink/MFAAvalonia",
            commit = Commit, short_commit = Commit[..6], upstream_tag = "v2.16.3-beta.1", tag = "v2.16.3-mfbd2.gfb5b80" });
        Assert.Equal("v2.16.3-mfbd2.gfb5b80", BuildVersionDisplay.ResolveLabel(null, $"2.14.0+{Commit}", manifest));
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
