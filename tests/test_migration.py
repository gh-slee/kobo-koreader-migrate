"""Portable regression tests; no Kobo, macOS tools, or device writes required."""

from __future__ import annotations

import argparse

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "kobo-koreader-migrate.py"
SPEC = importlib.util.spec_from_file_location("kobo_migration_under_test", SCRIPT)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)


def write_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def tree_contents(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*") if p.is_file() and not p.is_symlink()
    }


def fake_ditto(command: list[str], label: str, env: dict | None = None) -> None:
    """Exercise archive/restore code with zipfile in place of macOS ditto."""
    if command[:4] == ["ditto", "-c", "-k", "--keepParent"]:
        source, archive = map(Path, command[4:])
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            for path in sorted(source.rglob("*")):
                zf.write(path, path.relative_to(source.parent).as_posix())
    elif command[:3] == ["ditto", "-x", "-k"]:
        archive, target = map(Path, command[3:])
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
    else:
        raise AssertionError(f"Unexpected subprocess: {command}")


class MigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def make_koreader(self, mount: Path, marker: bytes, device_id: str) -> Path:
        kr = mount / ".adds" / "koreader"
        write_file(kr / "reader.lua", marker)
        write_file(kr / "frontend" / "reader.lua", marker + b" frontend")
        write_file(kr / "plugins" / "example.koplugin" / "main.lua", marker + b" plugin")
        write_file(kr / "plugins" / "example.koplugin" / "_meta.lua", b"return {}")
        write_file(kr / "settings.reader.lua", (
            'return {\n    ["device_id"] = "' + device_id
            + '",\n    ["language"] = "en",\n}\n'
        ).encode())
        return kr

    def archive_koreader(self, mount: Path, archive_name: str) -> tuple[Path, dict]:
        archive = self.root / archive_name
        info = migration.inspect_device(mount)
        kr = mount / ".adds" / "koreader"
        plugins, warnings = migration.basic_plugin_audit(kr)
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto):
            manifest = migration.create_archive(
                kr, archive, archive.with_suffix(".manifest.json"), info, plugins, warnings
            )
        return archive, manifest


class IdentityTests(MigrationTestCase):
    def test_preserve_changes_only_identity(self) -> None:
        kr = self.make_koreader(self.root / "target", b"source", "SOURCE")
        before = (kr / "settings.reader.lua").read_text()
        result = migration.apply_identity_mode(kr, "preserve", "TARGET")
        self.assertEqual(result, "TARGET")
        self.assertEqual((kr / "settings.reader.lua").read_text(), before.replace("SOURCE", "TARGET"))
        self.assertFalse((kr / "settings.reader.lua.tmp-migration").exists())

    def test_clone_and_generate_new_identity(self) -> None:
        kr = self.make_koreader(self.root / "target", b"source", "SOURCE")
        before = (kr / "settings.reader.lua").read_bytes()
        self.assertEqual(migration.apply_identity_mode(kr, "clone", "TARGET"), "SOURCE")
        self.assertEqual((kr / "settings.reader.lua").read_bytes(), before)
        with mock.patch.object(migration.uuid, "uuid4") as uuid4:
            uuid4.return_value.hex = "abcdef123456"
            result = migration.apply_identity_mode(kr, "new", "TARGET")
        self.assertEqual(result, "ABCDEF123456")
        self.assertEqual(migration.read_device_id(kr / "settings.reader.lua"), result)

    def test_insert_identity_preserves_lua_preferences(self) -> None:
        settings = write_file(self.root / "settings.reader.lua", b'return {\n ["language"] = "en",\n}\n')
        migration.set_device_id(settings, "NEW-ID")
        self.assertEqual(migration.read_device_id(settings), "NEW-ID")
        self.assertIn('["language"] = "en"', settings.read_text())
        self.assertEqual(settings.read_text().count('["device_id"]'), 1)

    def test_invalid_identity_input_fails_without_changes(self) -> None:
        kr = self.make_koreader(self.root / "target", b"source", "SOURCE")
        before = tree_contents(kr)
        for mode, target_id in (("preserve", None), ("invalid", "TARGET")):
            with self.subTest(mode=mode), self.assertRaises(migration.MigrationError):
                migration.apply_identity_mode(kr, mode, target_id)
        self.assertEqual(tree_contents(kr), before)
        invalid = write_file(self.root / "not-settings.lua", b"print('hello')")
        with self.assertRaises(migration.MigrationError):
            migration.set_device_id(invalid, "NEW-ID")
        self.assertEqual(invalid.read_bytes(), b"print('hello')")


class FullMigrationTests(MigrationTestCase):
    def test_archive_round_trip_preserves_plugins_and_reading_data(self) -> None:
        source = self.root / "source"
        kr = self.make_koreader(source, b"source binary", "SOURCE")
        write_file(kr / "statistics.sqlite3", b"statistics fixture")
        write_file(kr / "settings" / "book.sdr" / "metadata.epub.lua", b"progress fixture")
        write_file(kr / "fonts" / "custom.ttf", b"font fixture")
        write_file(kr / "cache" / "fontlist" / "fontinfo.dat", b"stale cache")
        write_file(kr / ".DS_Store", b"finder metadata")
        write_file(kr / "plugins" / "._example", b"apple double")
        original = tree_contents(kr)
        archive, manifest = self.archive_koreader(source, "source.zip")
        self.assertEqual(tree_contents(kr), original, "Archiving must leave source unchanged")
        self.assertIn("statistics.sqlite3", manifest["files"])
        self.assertIn("fonts/custom.ttf", manifest["files"])
        self.assertNotIn("cache/fontlist/fontinfo.dat", manifest["files"])
        self.assertNotIn(".DS_Store", manifest["files"])
        self.assertNotIn("plugins/._example", manifest["files"])
        self.assertEqual(manifest["archive"]["sha256"], migration.sha256_file(archive))
        target = self.root / "target"
        (target / ".adds").mkdir(parents=True)
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto):
            migration.restore_zip(archive, target / ".adds")
        target_kr = target / ".adds" / "koreader"
        migration.remove_stale_caches(target_kr)
        migration.remove_macos_metadata(target_kr)
        migration.verify_restored_tree(target_kr, manifest)
        self.assertEqual(
            tree_contents(target_kr),
            {rel: data for rel, data in original.items() if not migration.should_exclude_rel(rel)},
        )

    def test_full_rollback_cleanly_replaces_failed_tree(self) -> None:
        target = self.root / "target"
        kr = self.make_koreader(target, b"original", "TARGET")
        write_file(kr / "original-only.txt", b"must return")
        write_file(target / "Books" / "untouched.epub", b"unrelated book")
        original = tree_contents(kr)
        archive, manifest = self.archive_koreader(target, "target-before.zip")
        shutil.rmtree(kr)
        self.make_koreader(target, b"failed restore", "SOURCE")
        write_file(kr / "new-only.txt", b"must be removed")
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto):
            migration.rollback_target(kr, target / ".adds", archive, manifest)
        self.assertEqual(tree_contents(kr), original)
        self.assertFalse((kr / "new-only.txt").exists())
        self.assertEqual((target / "Books" / "untouched.epub").read_bytes(), b"unrelated book")

    def test_rollback_removes_partial_install_when_no_original(self) -> None:
        target = self.root / "target"
        kr = self.make_koreader(target, b"failed restore", "SOURCE")
        write_file(target / "Books" / "untouched.epub", b"unrelated book")
        migration.rollback_target(kr, target / ".adds", None, None)
        self.assertFalse(kr.exists())
        self.assertEqual((target / "Books" / "untouched.epub").read_bytes(), b"unrelated book")

    def test_equal_size_corruption_is_detected(self) -> None:
        target = self.root / "target"
        kr = self.make_koreader(target, b"correct", "TARGET")
        _, manifest = self.archive_koreader(target, "before-corruption.zip")
        (kr / "reader.lua").write_bytes(b"corrupt")
        with self.assertRaisesRegex(migration.MigrationError, "checksum mismatch"):
            migration.verify_restored_tree(kr, manifest)

    def test_missing_required_tree_and_archive_fail_validation(self) -> None:
        target = self.root / "target"
        kr = self.make_koreader(target, b"correct", "TARGET")
        _, manifest = self.archive_koreader(target, "before-missing.zip")
        shutil.rmtree(kr / "frontend")
        with self.assertRaises(migration.MigrationError):
            migration.verify_restored_tree(kr, manifest)
        archive = self.root / "missing-reader.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("koreader/other.lua", "data")
        with self.assertRaises(migration.MigrationError):
            migration.build_manifest(
                archive, self.root / "bad.manifest.json", migration.inspect_device(target), [], []
            )

    def test_incomplete_target_can_be_backed_up_and_rolled_back(self) -> None:
        target = self.root / "target"
        kr = target / ".adds" / "koreader"
        write_file(kr / "settings.reader.lua", b'return {["language"] = "en"}')
        write_file(kr / "broken-install.txt", b"preserve incomplete installation")
        original = tree_contents(kr)
        archive = self.root / "partial-target.zip"
        info = migration.inspect_device(target)
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto):
            manifest = migration.create_archive(
                kr, archive, archive.with_suffix(".manifest.json"), info, [], [], strict_source=False
            )
            shutil.rmtree(kr)
            self.make_koreader(target, b"failed source", "SOURCE")
            migration.rollback_target(kr, target / ".adds", archive, manifest)
        self.assertEqual(tree_contents(kr), original)

    def test_existing_backup_is_never_overwritten(self) -> None:
        source = self.root / "source"
        kr = self.make_koreader(source, b"source", "SOURCE")
        for existing in ("archive", "manifest"):
            with self.subTest(existing=existing):
                archive = self.root / (existing + ".zip")
                manifest = archive.with_suffix(".manifest.json")
                collision = archive if existing == "archive" else manifest
                collision.write_bytes(b"existing backup")
                with mock.patch.object(migration, "run_with_spinner") as runner:
                    with self.assertRaises(migration.MigrationError):
                        migration.create_archive(kr, archive, manifest, migration.inspect_device(source), [], [])
                    runner.assert_not_called()
                self.assertEqual(collision.read_bytes(), b"existing backup")

    def test_koreader_zip_preflight_rejects_unsafe_members_before_extracting(self) -> None:
        for name, symlink in (
            ("koreader/../escape", False), ("/koreader/reader.lua", False),
            ("koreader\\reader.lua", False), ("unexpected/file", False),
            ("koreader/link", True),
        ):
            with self.subTest(name=name):
                archive = self.root / "unsafe.zip"
                with zipfile.ZipFile(archive, "w") as zf:
                    info = zipfile.ZipInfo(name)
                    if symlink:
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    zf.writestr(info, b"../../outside")
                with mock.patch.object(migration, "run_with_spinner") as runner:
                    with self.assertRaises(migration.MigrationError):
                        migration.restore_zip(archive, self.root / "target")
                    runner.assert_not_called()

    def test_symlink_in_full_source_is_rejected(self) -> None:
        source = self.root / "source"
        kr = self.make_koreader(source, b"source", "SOURCE")
        outside = write_file(self.root / "secret", b"outside the device")
        (kr / "linked-file").symlink_to(outside)
        with mock.patch.object(migration, "run_with_spinner") as runner:
            with self.assertRaises(migration.MigrationError):
                self.archive_koreader(source, "symlink.zip")
            runner.assert_not_called()


class PayloadTests(MigrationTestCase):
    def test_scan_includes_formats_unicode_sidecars_central_metadata_and_fonts(self) -> None:
        source = self.root / "source"
        expected = {
            "Books/Comics/漫畫.CBZ": b"comic",
            "Books/novel.kepub.epub": b"novel",
            "Books/novel.kepub.sdr/metadata.epub.lua": b"progress",
            "Books/novel.kepub.sdr/cover.jpg": b"cover",
            "Books/archive.fb2.zip": b"fb2",
            ".adds/koreader/docsettings/mnt/onboard/Books/novel.kepub.sdr/metadata.epub.lua": b"central progress",
            ".adds/koreader/hashdocsettings/ab/abcdef.sdr/metadata.epub.lua": b"hashed progress",
            ".adds/koreader/history/legacy.lua": b"legacy",
            "fonts/Custom/Book.TTF": b"font",
            "fonts/custom.otf": b"font two",
        }
        for rel, data in expected.items():
            write_file(source / rel, data)
        excluded = {
            ".kobo/hidden.epub": b"system", ".hidden/book.epub": b"hidden",
            "Books/.hidden.epub": b"hidden book", "Books/orphan.sdr/metadata.epub.lua": b"orphan",
            "fonts/README.txt": b"font documentation", "Books/unknown.xyz": b"unknown",
            ".adds/koreader/reader.lua": b"application",
        }
        for rel, data in excluded.items():
            write_file(source / rel, data)
        files, report = migration.scan_payload(source, True, True)
        self.assertEqual(set(files), set(expected))
        self.assertEqual(report["file_count"], len(expected))
        self.assertEqual(report["total_bytes"], sum(map(len, expected.values())))
        self.assertIn("Books/unknown.xyz", report["unrecognized"])
        self.assertEqual(len(report["books"]), 3)
        self.assertEqual(len(report["sidecars"]), 2)
        self.assertEqual(len(report["central_metadata"]), 3)

    def test_scan_selection_and_extra_extensions(self) -> None:
        source = self.root / "source"
        for rel in ("Books/book.epub", "Books/other.zip", "Books/Ignore/ignored.pdf", "Elsewhere/outside.pdf"):
            write_file(source / rel, rel.encode())
        write_file(source / "Books/book.sdr/metadata.epub.lua", b"progress")
        write_file(source / ".adds/koreader/docsettings/metadata.lua", b"central")
        write_file(source / "fonts/font.ttf", b"font")
        files, _ = migration.scan_payload(
            source, True, False, include_metadata=False, include_dirs=["Books"],
            exclude_dirs=["Books/Ignore"], extra_extensions=["ZIP"],
        )
        self.assertEqual(set(files), {"Books/book.epub", "Books/other.zip"})
        fonts, _ = migration.scan_payload(source, False, True)
        self.assertEqual(set(fonts), {"fonts/font.ttf"})

    def test_scoped_scan_retains_adjacent_metadata_and_excludes_unrelated_central_trees(self) -> None:
        source = self.root / "source"
        for rel in (
            "Selected/book.epub", "Selected/book.sdr/metadata.epub.lua", "Other/book.epub",
            ".adds/koreader/docsettings/mnt/onboard/Other/book.sdr/metadata.epub.lua",
            ".adds/koreader/hashdocsettings/ab/shared.sdr/metadata.epub.lua",
        ):
            write_file(source / rel, rel.encode())
        for selection in ({"include_dirs": ["Selected"]}, {"exclude_dirs": ["Other"]}):
            with self.subTest(selection=selection):
                files, report = migration.scan_payload(source, True, False, **selection)
                self.assertEqual(set(files), {"Selected/book.epub", "Selected/book.sdr/metadata.epub.lua"})
                self.assertFalse(report["central_metadata"])
                self.assertTrue(any("central metadata excluded" in warning for warning in report["warnings"]))

    def test_source_symlinks_are_not_followed(self) -> None:
        source = self.root / "source"
        write_file(source / "Books/book.epub", b"regular")
        outside = write_file(self.root / "outside/book.epub", b"outside")
        (source / "Books/link.epub").symlink_to(outside)
        (source / "linked-dir").symlink_to(outside.parent, target_is_directory=True)
        files, report = migration.scan_payload(source, True, False)
        self.assertEqual(set(files), {"Books/book.epub"})
        self.assertIn("Books/link.epub", report["skipped_symlinks"])
        self.assertIn("linked-dir", report["skipped_symlinks"])

    def test_payload_paths_reject_traversal_system_paths_and_destination_symlinks(self) -> None:
        target = self.root / "target"
        target.mkdir()
        outside = write_file(self.root / "outside/book.epub", b"outside")
        (target / "linked").symlink_to(outside.parent, target_is_directory=True)
        (target / "book.epub").symlink_to(outside)
        write_file(target / "file-parent", b"file")
        for rel in (
            "../escape.epub", "/absolute.epub", "Books/../escape.epub", "Books//book.epub",
            ".kobo/book.epub", ".adds/koreader/settings.reader.lua", "linked/book.epub",
            "book.epub", "file-parent/book.epub",
        ):
            with self.subTest(rel=rel), self.assertRaises(migration.MigrationError):
                migration.payload_path(target, rel)
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_incremental_copy_and_exact_paths_preserve_unrelated_target_files(self) -> None:
        source, target = self.root / "source", self.root / "target"
        source_data = {
            "Books/unchanged.epub": b"same",
            "Books/existing.epub": b"new content",
            "Books/Comics/漫畫.CBZ": b"new comic",
            "Books/existing.sdr/metadata.epub.lua": b"new progress",
            "fonts/custom.ttf": b"new font",
        }
        for rel, data in source_data.items():
            write_file(source / rel, data)
        write_file(target / "Books/unchanged.epub", b"same")
        write_file(target / "Books/existing.epub", b"old content")
        write_file(target / "Books/unrelated.pdf", b"keep this")
        files, _ = migration.scan_payload(source, True, True)
        archive = self.root / "payload.zip"
        manifest = migration.create_payload_archive(source, files, archive)
        plan = migration.plan_payload(target, manifest)
        self.assertEqual(plan["skip"], ["Books/unchanged.epub"])
        self.assertEqual(set(plan["existing"]), {"Books/existing.epub"})
        self.assertEqual(set(plan["copy"]), set(source_data) - set(plan["skip"]))
        journal = {"touched": [], "created_dirs": []}
        migration.restore_payload(target, archive, plan["copy"], journal)
        for rel, data in source_data.items():
            self.assertEqual((target / rel).read_bytes(), data)
        self.assertEqual((target / "Books/unrelated.pdf").read_bytes(), b"keep this")
        self.assertNotIn("Books/unchanged.epub", journal["touched"])
        self.assertEqual(len(migration.plan_payload(target, manifest)["skip"]), len(source_data))

    def test_keep_target_conflicts_still_copy_new_files(self) -> None:
        source, target = self.root / "source", self.root / "target"
        write_file(source / "existing.epub", b"source")
        write_file(source / "new.epub", b"new")
        write_file(target / "existing.epub", b"target")
        files, _ = migration.scan_payload(source, True, False)
        manifest = migration.hash_payload(source, files)
        plan = migration.plan_payload(target, manifest, conflict="keep-target")
        self.assertEqual(plan["conflicts_kept"], ["existing.epub"])
        self.assertEqual(set(plan["copy"]), {"new.epub"})
        self.assertFalse(plan["existing"])

    def test_keep_target_conflicting_book_protects_its_sidecars_and_central_metadata(self) -> None:
        source, target = self.root / "source", self.root / "target"
        for rel in (
            "Books/existing.epub", "Books/existing.sdr/metadata.epub.lua",
            "Books/new.epub", "Books/new.sdr/metadata.epub.lua",
            ".adds/koreader/docsettings/mnt/onboard/Books/existing.sdr/metadata.epub.lua",
            ".adds/koreader/hashdocsettings/ab/shared.sdr/metadata.epub.lua",
        ):
            write_file(source / rel, b"source " + rel.encode())
        write_file(target / "Books/existing.epub", b"retained target edition")
        write_file(target / "Books/existing.sdr/metadata.epub.lua", b"retained reading progress")
        files, _ = migration.scan_payload(source, True, False)
        manifest = migration.hash_payload(source, files)
        plan = migration.plan_payload(target, manifest, conflict="keep-target")
        self.assertIn("Books/existing.epub", plan["conflicts_kept"])
        self.assertNotIn("Books/existing.sdr/metadata.epub.lua", plan["copy"])
        self.assertTrue(all(not rel.startswith(".adds/") for rel in plan["copy"]))
        self.assertEqual(set(plan["copy"]), {"Books/new.epub", "Books/new.sdr/metadata.epub.lua"})
        self.assertEqual(len(plan["metadata_skipped"]), 2)

    def test_failure_rollback_restores_overwrite_and_removes_created_paths(self) -> None:
        source, target = self.root / "source", self.root / "target"
        write_file(source / "A/existing.epub", b"new existing")
        write_file(source / "Z/new/book.cbz", b"new comic")
        write_file(target / "A/existing.epub", b"original target")
        write_file(target / "unrelated.pdf", b"unrelated")
        before = tree_contents(target)
        files, _ = migration.scan_payload(source, True, False)
        archive = self.root / "payload.zip"
        manifest = migration.create_payload_archive(source, files, archive)
        plan = migration.plan_payload(target, manifest)
        backup = self.root / "payload-before.zip"
        previous = migration.create_payload_archive(target, plan["existing"], backup)["files"]
        broken = {rel: dict(meta) for rel, meta in plan["copy"].items()}
        broken["Z/new/book.cbz"]["sha256"] = "0" * 64
        journal = {"touched": [], "created_dirs": []}
        with self.assertRaises(migration.MigrationError):
            migration.restore_payload(target, archive, broken, journal)
        migration.rollback_payload(target, backup, previous, journal)
        self.assertEqual(tree_contents(target), before)
        self.assertFalse((target / "Z").exists())

    def test_collision_paths_are_rejected(self) -> None:
        # A case-insensitive Mac filesystem cannot contain both real spellings.
        # Validate synthetic source inventories as well as a real destination.
        for paths in (
            ["Book.epub", "book.epub"],
            ["Books/one.epub", "books/two.epub"],
            ["Books", "Books/book.epub"],
            ["caf\u00e9.epub", "cafe\u0301.epub"],
        ):
            with self.subTest(paths=paths), self.assertRaises(migration.MigrationError):
                migration.assert_unique_paths(paths)
        target = self.root / "target"
        target.mkdir()
        write_file(target / "Books/book.epub", b"existing")
        manifest = {"files": {"books/book.epub": {"size": 3, "sha256": hashlib.sha256(b"new").hexdigest()}}}
        with self.assertRaises(migration.MigrationError):
            migration.plan_payload(target, manifest)

    def test_symlink_payload_archive_is_rejected_before_any_write(self) -> None:
        target = self.root / "target"
        write_file(target / "Books/book.epub", b"original")
        archive = self.root / "symlink-payload.zip"
        content = b"../../outside"
        with zipfile.ZipFile(archive, "w") as zf:
            info = zipfile.ZipInfo("Books/book.epub")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, content)
        files = {"Books/book.epub": {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}}
        journal = {"touched": [], "created_dirs": []}
        with self.assertRaises(migration.MigrationError):
            migration.restore_payload(target, archive, files, journal)
        self.assertEqual((target / "Books/book.epub").read_bytes(), b"original")
        self.assertFalse(journal["touched"])

    def test_payload_archive_preflight_rejects_duplicate_members_and_wrong_sizes(self) -> None:
        target = self.root / "target"
        write_file(target / "book.epub", b"original")
        content = b"new"
        files = {"book.epub": {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}}
        archive = self.root / "duplicate-payload.zip"
        with warnings.catch_warnings(), zipfile.ZipFile(archive, "w") as zf:
            warnings.simplefilter("ignore", UserWarning)
            zf.writestr("book.epub", content)
            zf.writestr("book.epub", content)
        with self.assertRaises(migration.MigrationError):
            migration.restore_payload(target, archive, files, {"touched": [], "created_dirs": []})
        self.assertEqual((target / "book.epub").read_bytes(), b"original")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("book.epub", b"unexpected length")
        with self.assertRaises(migration.MigrationError):
            migration.restore_payload(target, archive, files, {"touched": [], "created_dirs": []})
        self.assertEqual((target / "book.epub").read_bytes(), b"original")


class DiagnosticsTests(MigrationTestCase):
    def test_statistics_database_is_checked_read_only_and_counts_are_reported(self) -> None:
        mount = self.root / "device"
        kr = self.make_koreader(mount, b"runtime", "DEVICE")
        db = kr / "settings/statistics.sqlite3"
        db.parent.mkdir()
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE book (id INTEGER)")
            conn.execute("CREATE TABLE page_stat_data (id INTEGER)")
            conn.executemany("INSERT INTO book VALUES (?)", [(1,), (2,)])
            conn.executemany("INSERT INTO page_stat_data VALUES (?)", [(1,), (2,), (3,)])
        write_file(kr / "history.lua", b'return {"/mnt/onboard/Books/exists.epub", "/mnt/onboard/Books/missing.epub"}')
        write_file(mount / "Books/exists.epub", b"book")
        before = tree_contents(mount)
        result = migration.device_diagnostics(mount)
        self.assertEqual(result["statistics"], {"quick_check": "ok", "rows": {"book": 2, "page_stat_data": 3}})
        self.assertEqual(result["missing_references"], [{"file": "history.lua", "path": "/mnt/onboard/Books/missing.epub"}])
        self.assertEqual(tree_contents(mount), before)

    def test_pending_statistics_wal_blocks_unreliable_copy(self) -> None:
        mount = self.root / "device"
        kr = self.make_koreader(mount, b"runtime", "DEVICE")
        write_file(kr / "settings/statistics.sqlite3", b"fixture database")
        write_file(kr / "settings/statistics.sqlite3-wal", b"pending changes")
        with self.assertRaisesRegex(migration.MigrationError, "WAL"):
            migration.device_diagnostics(mount)

    def test_device_identity_and_backup_location_guards(self) -> None:
        mount = self.root / "device"
        write_file(mount / ".kobo/version", b"expected fingerprint")
        fingerprint = migration.device_fingerprint(mount)[0]
        migration.confirm_device(mount, fingerprint)
        write_file(mount / ".kobo/version", b"unexpected fingerprint")
        with self.assertRaises(migration.MigrationError):
            migration.confirm_device(mount, fingerprint)
        for backup in (mount, mount / "backups"):
            with self.subTest(backup=backup), self.assertRaises(migration.MigrationError):
                migration.ensure_local_backup(backup, mount)


class WorkflowTests(MigrationTestCase):
    def prepare_devices(self) -> tuple[Path, Path]:
        source, target = self.root / "source", self.root / "target"
        source_kr = self.make_koreader(source, b"source runtime", "SOURCE")
        target_kr = self.make_koreader(target, b"target runtime", "TARGET")
        write_file(source / ".kobo/version", b"SOURCE-SERIAL,firmware")
        write_file(target / ".kobo/version", b"TARGET-SERIAL,firmware")
        write_file(source_kr / "crash.log", b"Detected a Kobo Clara 2E (id)")
        write_file(target_kr / "crash.log", b"Detected a Kobo Libra 2 (id)")
        write_file(source / "Books/book.epub", b"new book")
        write_file(source / "Books/book.sdr/metadata.epub.lua", b"new reading progress")
        write_file(source / "fonts/custom.ttf", b"custom font")
        write_file(source_kr / "docsettings/mnt/onboard/Books/book.sdr/metadata.epub.lua", b"central reading progress")
        write_file(target / "Books/book.epub", b"old book")
        write_file(target / "Books/unrelated.pdf", b"keep unrelated")
        write_file(target / "fonts/custom.ttf", b"target font")
        write_file(target_kr / "target-only.txt", b"old installation")
        return source, target

    def run_workflow(self, source: Path, target: Path, mode: str, dry_run: bool = False,
                     conflict: str = "overwrite", books: bool | None = True,
                     fonts: bool | None = True) -> int:
        backup_dir = self.root / "backups"
        backup_dir.mkdir(exist_ok=True)
        args = SimpleNamespace(
            mode=mode, dry_run=dry_run, books=books, fonts=fonts, reading_data=True,
            conflict=conflict, include_dir=[], exclude_dir=[], extra_extension=[],
        )
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto), \
                mock.patch.object(migration, "wait_for_single_kobo", side_effect=[source, target]), \
                mock.patch.object(migration, "safe_eject"), \
                mock.patch.object(migration, "choose", return_value="1"), \
                mock.patch.object(migration, "choose_identity_mode", return_value="preserve"), \
                mock.patch.object(migration, "prompt_yes_no", return_value=True), \
                mock.patch("builtins.input", return_value=""):
            return migration.migrate(args, backup_dir, "test-run", backup_dir / "test.log")

    def test_full_workflow_still_clean_replaces_and_preserves_target_identity(self) -> None:
        source, target = self.prepare_devices()
        before_source = tree_contents(source)
        self.assertEqual(self.run_workflow(source, target, "full"), 0)
        self.assertEqual(tree_contents(source), before_source)
        kr = target / ".adds/koreader"
        self.assertEqual((kr / "reader.lua").read_bytes(), b"source runtime")
        self.assertFalse((kr / "target-only.txt").exists())
        self.assertEqual(migration.read_device_id(kr / "settings.reader.lua"), "TARGET")
        self.assertEqual((target / "Books/book.epub").read_bytes(), b"new book")
        self.assertEqual((target / "Books/unrelated.pdf").read_bytes(), b"keep unrelated")
        self.assertEqual((target / "fonts/custom.ttf").read_bytes(), b"custom font")
        result = json.loads((self.root / "backups/koreader-migration-result-test-run.json").read_text())
        self.assertEqual(result["mode"], "full")
        self.assertTrue(Path(result["target_backup"]).is_file())

    def test_full_defaults_include_books_reading_data_and_fonts_without_content_prompts(self) -> None:
        source, target = self.prepare_devices()

        def confirm_operation(question: str, default: bool = False) -> bool:
            self.assertNotIn("Include ebooks", question)
            self.assertNotIn("Include root fonts", question)
            return True

        backup_dir = self.root / "backups"
        backup_dir.mkdir()
        args = SimpleNamespace(
            mode="full", dry_run=False, books=None, fonts=None, reading_data=True,
            conflict="overwrite", include_dir=[], exclude_dir=[], extra_extension=[],
        )
        with mock.patch.object(migration, "run_with_spinner", side_effect=fake_ditto), \
                mock.patch.object(migration, "wait_for_single_kobo", side_effect=[source, target]), \
                mock.patch.object(migration, "safe_eject"), \
                mock.patch.object(migration, "choose", return_value="1"), \
                mock.patch.object(migration, "choose_identity_mode", return_value="preserve"), \
                mock.patch.object(migration, "prompt_yes_no", side_effect=confirm_operation), \
                mock.patch("builtins.input", return_value=""):
            self.assertEqual(migration.migrate(args, backup_dir, "defaults", backup_dir / "test.log"), 0)
        self.assertEqual((target / "Books/book.epub").read_bytes(), b"new book")
        self.assertEqual((target / "Books/book.sdr/metadata.epub.lua").read_bytes(), b"new reading progress")
        self.assertEqual((target / "fonts/custom.ttf").read_bytes(), b"custom font")

    def test_koreader_mode_clean_replaces_only_koreader_tree(self) -> None:
        source, target = self.prepare_devices()
        source_before = tree_contents(source)
        original_books = tree_contents(target / "Books")
        original_fonts = tree_contents(target / "fonts")
        self.assertEqual(self.run_workflow(source, target, "koreader", books=None, fonts=None), 0)
        self.assertEqual(tree_contents(source), source_before)
        self.assertEqual(tree_contents(target / "Books"), original_books)
        self.assertEqual(tree_contents(target / "fonts"), original_fonts)
        kr = target / ".adds/koreader"
        self.assertEqual((kr / "reader.lua").read_bytes(), b"source runtime")
        self.assertFalse((kr / "target-only.txt").exists())
        self.assertEqual(migration.read_device_id(kr / "settings.reader.lua"), "TARGET")
        result = json.loads((self.root / "backups/koreader-migration-result-test-run.json").read_text())
        self.assertEqual(result["mode"], "koreader")
        self.assertEqual(result["payload_copied"], 0)
        self.assertIsNone(result["source_payload"])

    def test_full_can_explicitly_skip_root_fonts_while_still_copying_books(self) -> None:
        source, target = self.prepare_devices()
        fonts_before = tree_contents(target / "fonts")
        self.assertEqual(self.run_workflow(source, target, "full", books=None, fonts=False), 0)
        self.assertEqual((target / "Books/book.epub").read_bytes(), b"new book")
        self.assertEqual((target / "Books/book.sdr/metadata.epub.lua").read_bytes(), b"new reading progress")
        self.assertEqual(tree_contents(target / "fonts"), fonts_before)

    def test_library_workflow_retains_installed_runtime_and_identity(self) -> None:
        source, target = self.prepare_devices()
        kr = target / ".adds/koreader"
        original = tree_contents(kr)
        self.assertEqual(self.run_workflow(source, target, "library"), 0)
        after = tree_contents(kr)
        for rel, data in original.items():
            self.assertEqual(after[rel], data)
        self.assertEqual(migration.read_device_id(kr / "settings.reader.lua"), "TARGET")
        self.assertEqual((target / "Books/book.sdr/metadata.epub.lua").read_bytes(), b"new reading progress")
        self.assertEqual((target / "Books/unrelated.pdf").read_bytes(), b"keep unrelated")
        self.assertIn("docsettings/mnt/onboard/Books/book.sdr/metadata.epub.lua", after)

    def test_dry_run_leaves_devices_byte_for_byte_unchanged(self) -> None:
        source, target = self.prepare_devices()
        before_source, before_target = tree_contents(source), tree_contents(target)
        self.assertEqual(self.run_workflow(source, target, "full", dry_run=True), 0)
        self.assertEqual(tree_contents(source), before_source)
        self.assertEqual(tree_contents(target), before_target)
        self.assertFalse(list((self.root / "backups").glob("*.zip")))
        report = json.loads((self.root / "backups/koreader-scan-test-run.json").read_text())
        self.assertTrue(report["dry_run"])
        self.assertIn("plan", report)

    def test_audit_leaves_devices_unchanged_without_explicit_dry_run(self) -> None:
        source, target = self.prepare_devices()
        before_source, before_target = tree_contents(source), tree_contents(target)
        self.assertEqual(self.run_workflow(source, target, "audit"), 0)
        self.assertEqual(tree_contents(source), before_source)
        self.assertEqual(tree_contents(target), before_target)
        self.assertFalse(list((self.root / "backups").glob("*.zip")))

    def test_full_keep_target_conflict_is_rejected_before_target_changes(self) -> None:
        source, target = self.prepare_devices()
        before_source, before_target = tree_contents(source), tree_contents(target)
        with self.assertRaisesRegex(migration.MigrationError, "only supported by LIBRARY or AUDIT"):
            self.run_workflow(source, target, "full", conflict="keep-target")
        self.assertEqual(tree_contents(source), before_source)
        self.assertEqual(tree_contents(target), before_target)
        self.assertFalse(list((self.root / "backups").glob("*pre-migration*")))

    def test_failure_after_full_replacement_restores_both_runtime_and_library(self) -> None:
        source, target = self.prepare_devices()
        before_source, before_target = tree_contents(source), tree_contents(target)
        real_restore = migration.restore_payload

        def restore_then_fail(target_mount, archive, files, journal):
            real_restore(target_mount, archive, files, journal)
            if "library-source" in archive.name:
                raise migration.MigrationError("Injected failure after payload writes")

        with mock.patch.object(migration, "restore_payload", side_effect=restore_then_fail):
            self.assertEqual(self.run_workflow(source, target, "full"), 2)
        self.assertEqual(tree_contents(source), before_source)
        self.assertEqual(tree_contents(target), before_target)
        self.assertFalse((self.root / "backups/koreader-migration-result-test-run.json").exists())


class CancellationTests(unittest.TestCase):
    def test_normal_cancellation_is_logged_without_error_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as td:
            args = argparse.Namespace(self_test=False, backup_dir=Path(td))
            output = io.StringIO()
            message = "Migration cancelled. No target files were modified."
            with mock.patch.object(migration, "parse_args", return_value=args),                     mock.patch.object(migration, "require_macos_tools"),                     mock.patch.object(migration, "migrate", side_effect=migration.MigrationCancelled(message)),                     mock.patch("sys.stdout", new=output):
                self.assertEqual(migration.main(), 0)
            log = next(Path(td).glob("runs/*/*.log")).read_text()
            self.assertIn(message, output.getvalue())
            self.assertIn(message, log)
            self.assertNotIn("Run stopped:", log)
            self.assertNotIn("ERROR:", log)

    def test_real_migration_error_remains_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            args = argparse.Namespace(self_test=False, backup_dir=Path(td))
            with mock.patch.object(migration, "parse_args", return_value=args),                     mock.patch.object(migration, "require_macos_tools"),                     mock.patch.object(migration, "migrate", side_effect=migration.MigrationError("Checksum failed")),                     mock.patch("sys.stdout", new=io.StringIO()):
                with self.assertRaises(migration.MigrationError):
                    migration.main()
            log = next(Path(td).glob("runs/*/*.log")).read_text()
            self.assertIn("Run stopped: MigrationError: Checksum failed", log)


class ProgressTests(unittest.TestCase):
    def test_byte_progress_reports_throttled_rate_and_eta(self):
        with mock.patch.object(migration.time, "monotonic", side_effect=[0, 1, 3, 4]),                 mock.patch.object(migration, "log_status") as status:
            progress = migration.ByteProgress("test file", 100)
            progress.update(25)
            self.assertEqual(status.call_count, 1)
            progress.update(25)
            self.assertIn("50.0%", status.call_args.args[0])
            self.assertIn("ETA", status.call_args.args[0])
            progress.update(50, final=True)
            self.assertIn("100.0%", status.call_args.args[0])

    def test_copy_logging_preserves_exact_bytes(self):
        source = io.BytesIO(b"book" * 1000)
        target = io.BytesIO()
        migration.copy_with_progress(source, target, "test", 4000)
        self.assertEqual(target.getvalue(), b"book" * 1000)


class ConflictPolicyTests(unittest.TestCase):
    def test_only_library_prompts_for_conflict_policy(self):
        with mock.patch.object(migration, "choose", return_value="2") as choice:
            for mode in ("full", "koreader", "audit"):
                self.assertEqual(migration.select_conflict_policy(mode, None), "overwrite")
            choice.assert_not_called()
            self.assertEqual(migration.select_conflict_policy("library", None), "keep-target")
            choice.assert_called_once()

    def test_explicit_keep_target_rejected_for_full_directory_modes(self):
        with mock.patch.object(migration, "choose") as choice:
            for mode in ("full", "koreader"):
                with self.assertRaises(migration.MigrationError):
                    migration.select_conflict_policy(mode, "keep-target")
            self.assertEqual(migration.select_conflict_policy("library", "keep-target"), "keep-target")
            self.assertEqual(migration.select_conflict_policy("audit", "keep-target"), "keep-target")
            choice.assert_not_called()


class CliTests(MigrationTestCase):
    def test_supported_modes_parse_and_default_full_payload_options_are_unspecified(self) -> None:
        for mode in ("full", "koreader", "library", "audit"):
            with self.subTest(mode=mode), mock.patch.object(sys, "argv", [str(SCRIPT), "--mode", mode]):
                args = migration.parse_args()
                self.assertEqual(args.mode, mode)
                self.assertIsNone(args.books)
                self.assertIsNone(args.fonts)
                self.assertTrue(args.reading_data)

    def test_conflicting_cli_options_reject_before_device_access(self) -> None:
        for mode, options in (
            ("full", ["--no-books"]), ("full", ["--no-reading-data"]),
            ("koreader", ["--books"]), ("koreader", ["--fonts"]),
            ("full", ["--include-dir", "Books"]), ("full", ["--exclude-dir", "Books"]),
        ):
            with self.subTest(mode=mode, options=options):
                backup = self.root / f"{mode}-{options[0][2:]}"
                argv = [str(SCRIPT), "--mode", mode, *options, "--backup-dir", str(backup)]
                with mock.patch.object(sys, "argv", argv), \
                        mock.patch.object(migration, "require_macos_tools"), \
                        mock.patch.object(migration, "wait_for_single_kobo") as wait_for_device, \
                        mock.patch.object(migration, "prompt_yes_no", return_value=True), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises((migration.MigrationError, SystemExit)) as raised:
                        migration.main()
                    if isinstance(raised.exception, SystemExit):
                        self.assertNotEqual(raised.exception.code, 0)
                    wait_for_device.assert_not_called()
                self.assertFalse(list(backup.glob("*.zip")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
