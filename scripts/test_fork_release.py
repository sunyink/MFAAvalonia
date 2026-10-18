"""Contract tests for fork_release.py; requires only the Python standard library."""

import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

import fork_release


SHA = "00000a" + "1" * 34


def info_for(tag="v2.14.0"):
    return fork_release.build_info(SHA, tag)


class BuildMetadataTests(unittest.TestCase):
    def test_official_and_beta_tags_preserve_six_digit_prefix(self):
        for upstream in ("v2.14.0", "v2.14.0-beta.3"):
            with self.subTest(upstream=upstream):
                info = info_for(upstream)
                self.assertEqual(info["short_commit"], "00000a")
                self.assertEqual(info["tag"], "v2.14.0-mfbd2.g00000a")
                self.assertEqual(fork_release.validate_info(info), info)

    def test_validate_info_rejects_invalid_identity_and_tag_fields(self):
        mutations = (
            ("repository", "other/project"),
            ("branch", "master"),
            ("commit", "a" * 40),
            ("short_commit", "00000"),
            ("tag", "v2.14.0"),
        )
        for key, value in mutations:
            invalid = dict(info_for(), **{key: value})
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    fork_release.validate_info(invalid)

    def test_check_context_rejects_wrong_trigger_repository_ref_and_sha(self):
        info = info_for()
        good = {
            "GITHUB_REPOSITORY": fork_release.REPOSITORY,
            "GITHUB_REF": f"refs/heads/{fork_release.BRANCH}",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_SHA": SHA,
        }
        for key, value in (
            ("GITHUB_REF", "refs/heads/master"),
            ("GITHUB_REPOSITORY", "MaaXYZ/MFAAvalonia"),
            ("GITHUB_EVENT_NAME", "push"),
            ("GITHUB_SHA", "f" * 40),
        ):
            env = dict(good, **{key: value})
            with self.subTest(key=key), mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    fork_release.check_context(info)


class PackageTests(unittest.TestCase):
    def make_publish_dir(self, root, rid):
        root.mkdir(parents=True)
        executable = root / ("MFAAvalonia.exe" if rid.startswith("win-") else "MFAAvalonia")
        executable.write_bytes(b"client")
        libs = root / "libs"
        libs.mkdir()
        (libs / "MFAAvalonia.Core.dll").write_bytes(b"core")
        return root

    def test_package_creates_stamped_zip_and_tar_and_preserves_unix_executable_mode(self):
        info = info_for()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            win_root = self.make_publish_dir(base / "win", "win-x64")
            zip_path = fork_release.package(win_root, base / "out", "win-x64", info)
            self.assertTrue(zip_path.is_file())
            self.assertEqual(zip_path.name, fork_release.asset_name(info, "win-x64"))
            self.assertEqual(fork_release.archive_stamp(zip_path), dict(info, rid="win-x64"))
            with zipfile.ZipFile(zip_path) as archive:
                self.assertIn("MFAAvalonia.exe", archive.namelist())
                self.assertIn("libs/MFAAvalonia.Core.dll", archive.namelist())

            unix_root = self.make_publish_dir(base / "linux", "linux-x64")
            tar_path = fork_release.package(unix_root, base / "out", "linux-x64", info)
            self.assertTrue(tar_path.is_file())
            self.assertEqual(tar_path.name, fork_release.asset_name(info, "linux-x64"))
            self.assertEqual(fork_release.archive_stamp(tar_path), dict(info, rid="linux-x64"))
            with tarfile.open(tar_path) as archive:
                client = archive.getmember("MFAAvalonia")
                if os.name == "posix":
                    self.assertTrue(client.mode & stat.S_IXUSR)
                self.assertIn("libs/MFAAvalonia.Core.dll", archive.getnames())


class AssetCollectionTests(unittest.TestCase):
    def create_all_assets(self, root, info):
        for rid in fork_release.RIDS:
            publish_root = root.parent / f"publish-{rid}"
            publish_root.mkdir()
            executable = publish_root / ("MFAAvalonia.exe" if rid.startswith("win-") else "MFAAvalonia")
            executable.write_bytes(b"client")
            libs = publish_root / "libs"
            libs.mkdir()
            (libs / "MFAAvalonia.Core.dll").write_bytes(b"core")
            fork_release.package(publish_root, root, rid, info)

    def test_collect_requires_exact_six_runtime_packages(self):
        info = info_for()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "assets"
            root.mkdir()
            self.create_all_assets(root, info)
            self.assertEqual(len(fork_release.collect_assets(root, info)), 6)

            missing = next(root / fork_release.asset_name(info, rid) for rid in fork_release.RIDS)
            missing.unlink()
            with self.assertRaises(ValueError):
                fork_release.collect_assets(root, info)

    def test_collect_rejects_extra_package(self):
        info = info_for()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "assets"
            root.mkdir()
            self.create_all_assets(root, info)
            (root / "unexpected.zip").write_bytes(b"extra")
            with self.assertRaises(ValueError):
                fork_release.collect_assets(root, info)

    def test_collect_rejects_package_with_wrong_stamp(self):
        info = info_for()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "assets"
            root.mkdir()
            self.create_all_assets(root, info)
            target = root / fork_release.asset_name(info, "win-x64")
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr(fork_release.STAMP, json.dumps(dict(info, rid="win-arm64")))
            with self.assertRaises(ValueError):
                fork_release.collect_assets(root, info)


class UploadVerificationTests(unittest.TestCase):
    def setUp(self):
        self.expected = [
            {"name": "one.zip", "size": 5, "sha256": "a" * 64},
            {"name": "two.tar.gz", "size": 7, "sha256": "b" * 64},
        ]
        self.actual = [
            {"name": item["name"], "size": item["size"],
             "digest": f"sha256:{item['sha256']}", "state": "uploaded"}
            for item in self.expected
        ]

    def test_complete_uploaded_set_passes(self):
        fork_release.verify_uploaded(self.expected, self.actual)

    def test_missing_duplicate_and_mismatched_uploads_are_rejected(self):
        cases = [self.actual[:1], self.actual + [dict(self.actual[0])]]
        for field, value in (("size", 999), ("digest", "sha256:" + "c" * 64), ("state", "new")):
            changed = [dict(item) for item in self.actual]
            changed[0][field] = value
            cases.append(changed)
        for actual in cases:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                fork_release.verify_uploaded(self.expected, actual)


class CleanupTests(unittest.TestCase):
    def run_cleanup(self, info, release):
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(json.dumps({"id": 123, "tag": info["tag"], "commit": info["commit"]}),
                                  encoding="utf-8")
            env = {
                "GITHUB_REPOSITORY": fork_release.REPOSITORY,
                "GITHUB_REF": f"refs/heads/{fork_release.BRANCH}",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_SHA": info["commit"],
                "MFAA_BUILD_INFO": json.dumps(info),
            }
            with mock.patch.object(fork_release, "STATE", state_path), \
                    mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(fork_release, "api", return_value=release) as api_mock:
                fork_release.cleanup()
                return api_mock

    def test_cleanup_deletes_this_run_draft_release(self):
        info = info_for()
        api_mock = self.run_cleanup(info, {"draft": True, "tag_name": info["tag"]})
        self.assertEqual(api_mock.call_count, 2)
        self.assertEqual(api_mock.call_args.args[1], "DELETE")

    def test_cleanup_keeps_published_release(self):
        info = info_for()
        api_mock = self.run_cleanup(info, {"draft": False, "tag_name": info["tag"]})
        self.assertEqual(api_mock.call_count, 1)

    def test_cleanup_rejects_state_from_another_commit(self):
        info = info_for()
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(json.dumps({"id": 123, "tag": info["tag"], "commit": "f" * 40}),
                                  encoding="utf-8")
            env = {
                "GITHUB_REPOSITORY": fork_release.REPOSITORY,
                "GITHUB_REF": f"refs/heads/{fork_release.BRANCH}",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_SHA": info["commit"],
                "MFAA_BUILD_INFO": json.dumps(info),
            }
            with mock.patch.object(fork_release, "STATE", state_path), \
                    mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(fork_release, "api") as api_mock:
                with self.assertRaises(ValueError):
                    fork_release.cleanup()
                api_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
