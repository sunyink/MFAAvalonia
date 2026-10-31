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

Release tags use the complete upstream tag plus an independent fork counter,
for example `v2.16.5-beta.1-MFABD2.beta.1`. The upstream tag is selected from the
dispatched commit's ancestors, using tags fetched directly from MaaXYZ into a
separate local tag namespace. Prerelease and build suffixes are preserved;
unmerged upstream tags cannot change the baseline. Each complete upstream tag
has its own counter: moving from `v2.16.5-beta.1` to `v2.16.5-beta.2` starts a new
sequence. Retrying a source keeps its reserved tag; another source cannot reuse it.
The six-character commit selector remains separate from the tag. Ambiguous short
commits fail instead of silently lengthening the ID.
Releases always have `prerelease: true` and `make_latest: false`. Existing releases
are never replaced. A failed run removes only the draft it created, retaining
any already-created tag as an immutable source pointer.

The workflow publishes Windows, Linux, and macOS packages for x64 and arm64. It
does not build the MFAA Android shell; MFABD2's Android application has its own
UI/build pipeline. Every desktop package contains `mfaa-build.json`. The release
also includes `fork-release.json` with the complete upstream tag in
`upstream_version`, the fork counter, the complete source commit, and package
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

## Displayed version and upstream updates

Version settings, the default window title, and release titles show, for example,
`v2.16.5-beta.1-MFABD2.beta.1 · abcdef`. The first `beta.1` belongs to upstream;
the final `MFABD2.beta.1` is the independently reserved fork counter. A stable
upstream baseline uses `v2.16.5-MFABD2.beta.1 · abcdef` and remains a prerelease.

The same tag is used in the release, package names and schema-2 manifests.
Historical numeric-only numbered tags and schema-1 hash-tag packages remain
readable with their original identities. The resource-side package selector must
support complete upstream versions before selecting a new-format release.
The UI reads the package manifest only if its full commit matches the running
assembly. A stale manifest is ignored after an official client replacement.
Local test builds may supply `-p:MfaBuildLabel=...`; those show an explicit
localized self-built/dev label instead of claiming a packaged release identity.

The displayed label is separate from `RootViewModel.Version`. Upstream update
checks, minimum-version checks and `PI_CLIENT_VERSION` continue to use the
upstream compatibility version. Never insert the fork name or a fork beta counter
into that field. A newer official version therefore compares independently of
how many fork builds were made.
An official release equal to the compatibility version is not a new version;
reinstalling that same version remains a manual action.
