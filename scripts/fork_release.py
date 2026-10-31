"""Build and publish immutable desktop prereleases from the mfabd2 branch."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
from urllib.parse import quote
import zipfile

REPOSITORY = "sunyink/MFAAvalonia"
BRANCH = "mfabd2"
RIDS = ("win-x64", "win-arm64", "linux-x64", "linux-arm64", "osx-x64", "osx-arm64")
STAMP = "mfaa-build.json"
MANIFEST = "fork-release.json"
STATE = Path("fork-release-state.json")
UPSTREAM_VERSION = re.compile(
    r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
NUMBERED_TAG = re.compile(rf"(?P<upstream>{UPSTREAM_VERSION.pattern})-MFABD2\.beta\.(?P<number>[1-9]\d*)")
LEGACY_TAG = re.compile(r"v\d+\.\d+\.\d+-mfbd2\.g[0-9a-f]{6}")


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def api(path, method="GET", payload=None, missing_ok=False):
    args = ["gh", "api", "--method", method, path]
    if payload is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True)
    if missing_ok and result.returncode and "HTTP 404" in result.stderr:
        return None
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def validate_info(info):
    if info.get("schema") != 2 or info.get("repository") != REPOSITORY or info.get("branch") != BRANCH:
        raise ValueError("Not an mfabd2 fork build")
    sha = info.get("commit", "")
    short = info.get("short_commit", "")
    upstream = info.get("upstream_version", "")
    base = UPSTREAM_VERSION.fullmatch(upstream)
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or short != sha[:6] or not base:
        raise ValueError("Invalid commit or upstream version")
    sequence = info.get("fork_sequence")
    if type(sequence) is not int or not 1 <= sequence <= 2147483647:
        raise ValueError("Fork beta sequence must be a positive 32-bit integer")
    if info.get("tag") != f"{upstream}-MFABD2.beta.{sequence}":
        raise ValueError("The release, packages and client must use the same numbered fork tag")
    return info


def build_info(sha, upstream, sequence):
    if not UPSTREAM_VERSION.fullmatch(upstream):
        raise ValueError("No recognizable upstream version tag")
    return validate_info(dict(schema=2, repository=REPOSITORY, branch=BRANCH,
                              commit=sha, short_commit=sha[:6], upstream_version=upstream,
                              fork_sequence=sequence,
                              tag=f"{upstream}-MFABD2.beta.{sequence}"))


def read_info():
    return validate_info(json.loads(os.environ["MFAA_BUILD_INFO"]))


def version_tag(info):
    validate_info(info)
    return info["tag"]


def display_version(info):
    return f"{version_tag(info)} · {info['short_commit']}"


def release_notes(info, run_id):
    validate_info(info)
    return (f"MFABD2 自家客户端预发布。上游基础版本：`{info['upstream_version']}`。\n\n"
            "请按系统和处理器选择下方安装包；普通 64 位 Windows 电脑使用 `win-x64.zip`。"
            "GitHub 自动附带的 `Source code` 是源码。\n\n"
            f"MFABD2 单次打包选用本版时，填写 **`{info['short_commit']}`**。\n\n"
            f"[本次源码](https://github.com/{REPOSITORY}/commit/{info['commit']}) · "
            f"[六平台构建](https://github.com/{REPOSITORY}/actions/runs/{run_id})")


def upstream_tag_at(sha):
    # Tags fetched from upstream may be ahead of this branch. Only ancestry of
    # the packaged commit determines its baseline; never read upstream releases.
    return command("git", "describe", "--tags", "--match", "upstream/v[0-9]*",
                   "--exclude", "upstream/*-mfbd2.*", "--abbrev=0", sha).removeprefix("upstream/")


def fork_tags():
    result = {}
    for ref in command("git", "for-each-ref", "--format=%(refname)", "refs/tags/fork/").splitlines():
        name = ref.removeprefix("refs/tags/fork/")
        if NUMBERED_TAG.fullmatch(name) or LEGACY_TAG.fullmatch(name):
            result[name] = command("git", "rev-parse", f"{ref}^{{commit}}")
    return result


def fork_sequence(sha, upstream, tags):
    if not UPSTREAM_VERSION.fullmatch(upstream):
        raise ValueError("No recognizable upstream version tag")
    reserved = []
    maximum = 0
    package_count = 0
    for tag, commit in tags.items():
        number = NUMBERED_TAG.fullmatch(tag)
        if number:
            if commit == sha:
                if number["upstream"] != upstream:
                    raise ValueError("This source already has a reserved fork version under another baseline")
                reserved.append(int(number["number"]))
            if number["upstream"] == upstream:
                maximum = max(maximum, int(number["number"]))
        elif re.fullmatch(rf"{re.escape(upstream)}-mfbd2\.g[0-9a-f]{{6}}", tag):
            # The package count supplies a floor for pre-numbering builds.
            # Keep their tags, including after a release is removed.
            if not tag.endswith(f".g{commit[:6]}"):
                raise ValueError("Fork package tag points to a different source")
            package_count += 1
    if len(reserved) > 1:
        raise ValueError("This source has more than one reserved fork version")
    return reserved[0] if reserved else max(maximum, package_count) + 1


def reserve_version(info):
    tag = version_tag(info)
    path = f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}"
    if api(path, missing_ok=True) is None:
        # Atomic ref creation rejects competing reservations. Never move or
        # remove this tag: failed builds reuse it; other sources advance past it.
        api(f"repos/{REPOSITORY}/git/refs", "POST", dict(ref=f"refs/tags/{tag}", sha=info["commit"]))
    verify_version(info)


def verify_version(info):
    if api(f"repos/{REPOSITORY}/commits/{quote(version_tag(info), safe='')}")["sha"] != info["commit"]:
        raise ValueError("Fork beta number is reserved for another source")


def check_context(info=None):
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_REF") != f"refs/heads/{BRANCH}"
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        raise ValueError("Fork releases may only run manually from sunyink/MFAAvalonia:mfabd2")
    if info is not None and info["commit"] != os.environ.get("GITHUB_SHA"):
        raise ValueError("Build commit differs from the dispatched commit")


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset_name(info, rid):
    if rid not in RIDS:
        raise ValueError(f"Unsupported runtime: {rid}")
    return f'MFAAvalonia-{info["tag"]}-{rid}' + (".zip" if rid.startswith("win-") else ".tar.gz")


def metadata():
    check_context()
    sha = command("git", "rev-parse", "HEAD")
    # A fork's copied tags can lag behind its merged source. Keep upstream tag
    # names separate from local/fork tags; describe only ancestors of this SHA.
    command("git", "fetch", "--no-tags", "https://github.com/MaaXYZ/MFAAvalonia.git",
            "refs/tags/v*:refs/tags/upstream/v*")
    command("git", "fetch", "--no-tags", f"https://github.com/{REPOSITORY}.git",
            "refs/tags/v*:refs/tags/fork/v*")
    upstream = upstream_tag_at(sha)
    tags = fork_tags()
    info = build_info(sha, upstream, fork_sequence(sha, upstream, tags))
    check_context(info)
    # Resolve the requested six characters remotely as well, so ambiguous prefixes fail.
    resolved = api(f"repos/{REPOSITORY}/commits/{info['short_commit']}")["sha"]
    if resolved != sha:
        raise ValueError("Six-character commit is ambiguous or resolves to another commit")
    page = 1
    while True:
        releases = api(f"repos/{REPOSITORY}/releases?per_page=100&page={page}")
        if any(tags.get(release["tag_name"]) == sha
               or re.fullmatch(rf"v\d+\.\d+\.\d+-mfbd2\.g{info['short_commit']}", release["tag_name"])
               for release in releases):
            raise ValueError("This commit already has a fork release; reuse it instead of creating another version name")
        if len(releases) < 100:
            break
        page += 1
    tag = quote(info["tag"], safe="")
    if api(f"repos/{REPOSITORY}/releases/tags/{tag}", missing_ok=True) is not None:
        raise ValueError(f"Release {info['tag']} already exists; existing packages are never overwritten")
    existing_tag = api(f"repos/{REPOSITORY}/git/ref/tags/{tag}", missing_ok=True)
    if existing_tag and api(f"repos/{REPOSITORY}/commits/{tag}")["sha"] != sha:
        raise ValueError("Release tag already belongs to another commit")
    reserve_version(info)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"commit={sha}\ntag={info['tag']}\ninfo={json.dumps(info)}\n")
    print(f"Source ancestor tag: {upstream}")
    print(json.dumps(info, indent=2))


def package(root, output, rid, info):
    validate_info(info)
    if rid not in RIDS or not root.is_dir():
        raise ValueError("Missing publish directory or unsupported runtime")
    executable = root / ("MFAAvalonia.exe" if rid.startswith("win-") else "MFAAvalonia")
    if not executable.is_file() or not (root / "libs" / "MFAAvalonia.Core.dll").is_file():
        raise ValueError("Publish output does not contain the desktop client")
    write_json(root / STAMP, dict(info, rid=rid))
    output.mkdir(parents=True, exist_ok=True)
    target = output / asset_name(info, rid)
    if target.exists():
        raise ValueError(f"Refusing to overwrite {target}")
    if rid.startswith("win-"):
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    else:
        # Preserve Unix executable bits, including the updater and dependency helper.
        for path in root.rglob("*"):
            if path.is_file() and (path.name.startswith(("MFAAvalonia", "MFAUpdater")) or path.suffix == ".sh"):
                path.chmod(path.stat().st_mode | 0o111)
        with tarfile.open(target, "w:gz") as archive:
            for path in sorted(root.iterdir()):
                archive.add(path, arcname=path.name)
    return target


def archive_stamp(path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read(STAMP))
    with tarfile.open(path) as archive:
        stream = archive.extractfile(STAMP)
        if stream is None:
            raise ValueError(f"Missing build stamp in {path}")
        return json.load(stream)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect_assets(root, info):
    expected = {asset_name(info, rid): rid for rid in RIDS}
    actual = {p.name for p in root.iterdir() if p.is_file() and p.name != MANIFEST}
    if actual != set(expected):
        raise ValueError(f"Incomplete or unexpected packages: {sorted(actual ^ set(expected))}")
    assets = []
    for name, rid in expected.items():
        path = root / name
        stamp = archive_stamp(path)
        if stamp != dict(info, rid=rid):
            raise ValueError(f"Package source mismatch: {name}")
        assets.append(dict(name=name, size=path.stat().st_size, sha256=digest(path)))
    return assets


def verify_uploaded(expected, actual):
    by_name = {asset["name"]: asset for asset in actual}
    if len(by_name) != len(actual) or set(by_name) != {asset["name"] for asset in expected}:
        raise ValueError("Uploaded asset list differs from the complete local package set")
    for entry in expected:
        remote = by_name[entry["name"]]
        if (remote.get("state") != "uploaded" or remote.get("size") != entry["size"]
                or remote.get("digest") != f'sha256:{entry["sha256"]}'):
            raise ValueError(f'Uploaded size or checksum mismatch: {entry["name"]}')


def publish(root):
    info = read_info()
    check_context(info)
    verify_version(info)
    packages = collect_assets(root, info)
    write_json(root / MANIFEST, dict(info, packages=packages))
    expected = packages + [dict(name=MANIFEST, size=(root / MANIFEST).stat().st_size,
                               sha256=digest(root / MANIFEST))]
    tag = info["tag"]
    if api(f"repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}", missing_ok=True) is not None:
        raise ValueError("Release already exists; refusing to replace it")
    body = release_notes(info, os.environ['GITHUB_RUN_ID'])
    release = api(f"repos/{REPOSITORY}/releases", "POST", dict(
        tag_name=tag, target_commitish=info["commit"], name=display_version(info),
        body=body, draft=True, prerelease=True, make_latest="false"))
    write_json(STATE, dict(id=release["id"], tag=tag, commit=info["commit"]))
    command("gh", "release", "upload", tag, *(str(root / item["name"]) for item in expected), "--repo", REPOSITORY)
    uploaded = api(f"repos/{REPOSITORY}/releases/{release['id']}")
    verify_uploaded(expected, uploaded["assets"])
    # The lightweight tag is fixed before publishing. Existing tags must point to this source.
    ref_path = f"repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}"
    if api(ref_path, missing_ok=True) is None:
        api(f"repos/{REPOSITORY}/git/refs", "POST", dict(ref=f"refs/tags/{tag}", sha=info["commit"]))
    if api(f"repos/{REPOSITORY}/commits/{quote(tag, safe='')}")["sha"] != info["commit"]:
        raise ValueError("Tag does not point to the packaged commit")
    result = api(f"repos/{REPOSITORY}/releases/{release['id']}", "PATCH",
                 dict(draft=False, prerelease=True, make_latest="false"))
    if result["draft"] or not result["prerelease"]:
        raise ValueError("Release did not remain a prerelease")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write(f"## Fork prerelease\n\nCommit selector: **`{info['short_commit']}`**\n\n"
                     f"[{tag}]({result['html_url']})\n\nFull source: `{info['commit']}`\n")
    print(result["html_url"])


def cleanup():
    if not STATE.exists():
        return
    info = read_info()
    check_context(info)
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state["commit"] != info["commit"] or state["tag"] != info["tag"]:
        raise ValueError("Refusing to remove another build's draft")
    path = f"repos/{REPOSITORY}/releases/{state['id']}"
    release = api(path, missing_ok=True)
    if release and release["draft"] and release["tag_name"] == state["tag"]:
        api(path, "DELETE")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("metadata")
    pack = sub.add_parser("package")
    pack.add_argument("--publish-dir", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--rid", choices=RIDS, required=True)
    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--assets", type=Path, required=True)
    sub.add_parser("cleanup")
    args = parser.parse_args()
    if args.action == "metadata":
        metadata()
    elif args.action == "package":
        info = read_info()
        check_context(info)
        if command("git", "rev-parse", "HEAD") != info["commit"]:
            raise ValueError("Checked-out source differs from build metadata")
        print(package(args.publish_dir, args.output, args.rid, info))
    elif args.action == "publish":
        publish(args.assets)
    else:
        cleanup()


if __name__ == "__main__":
    main()
