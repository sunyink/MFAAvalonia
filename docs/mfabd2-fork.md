# MFABD2 fork maintenance

This fork uses `mfabd2` as its default integration and release branch. `master`
remains the upstream synchronization branch. Merge upstream changes into
`mfabd2` deliberately; keep the fork release policy when resolving CI conflicts.
Branches submitted as upstream UI pull requests do not carry this release setup.

## Build a package

1. Merge the desired source changes into `mfabd2` and push it.
2. Open **Actions → Build MFABD2 prerelease → Run workflow**.
3. Leave **Use workflow from** set to **mfabd2**, then run it.
4. Wait for all six desktop builds and the publication check to finish.
5. Copy the six-character commit selector from the run summary or release notes.

There is no arbitrary source branch or stable-release input. Each run builds the
exact commit selected when it was dispatched, even if the branch advances later.

Packages use names such as `v2.16.3-mfbd2.g4e22d1`. The numeric prefix comes from
the nearest upstream version tag (fetched from MaaXYZ into a separate local tag
namespace, so stale fork tags do not select an old version); the suffix is exactly six hexadecimal commit
characters. Ambiguous short commits fail instead of silently lengthening the ID.
Releases always have `prerelease: true` and `make_latest: false`. Existing releases
are never replaced. A failed run removes only the draft it created, retaining
any already-created tag as an immutable source pointer.

The workflow publishes Windows, Linux, and macOS packages for x64 and arm64. It
does not build the MFAA Android shell; MFABD2's Android application has its own
UI/build pipeline. Every desktop package contains `mfaa-build.json`. The release
also includes `fork-release.json` with the complete source commit and package
sizes/SHA-256 checksums. All six packages are uploaded as a draft, verified, then
made public together as a prerelease.

The inherited `Release.yml` and `Test.yml` remain for upstream comparisons but
are disabled in this fork's Actions settings, and guarded in `mfabd2` against
running outside the upstream repository. Keep those guards when merging upstream
changes. The custom workflow never uploads to the upstream release or mirrors.

The MFABD2 resource repository chooses an already-built package using the
six-character selector. Its ordinary `requirements.txt` version remains the
default when the optional override is empty. Client-side update behavior remains
the upstream behavior.
