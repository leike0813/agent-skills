"""Offline entrypoint tests: every Git write is confined to TemporaryDirectory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class PublishGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.origin = self.root / "origin.git"
        self.git(self.root, "init", "--bare", str(self.origin))
        self.agg = self.root / "agg"
        self.git(self.root, "clone", str(self.origin), str(self.agg))
        self.git(self.agg, "checkout", "-b", "main")
        (self.agg / "README.md").write_text("# Fixture\n")
        (self.agg / ".gitignore").write_text("*.bak\n")
        self.commit(self.agg, "initial")
        self.git(self.agg, "push", "-u", "origin", "main")
        self.git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.dev = self.root / "dev"
        self.git(self.root, "init", "-b", "main", str(self.dev))
        self.pkg = self.dev / "paper"
        self.pkg.mkdir()
        (self.dev / ".skills").write_text("paper\n")
        (self.pkg / "SKILL.md").write_text("---\nname: paper\ndescription: fixture\n---\n# Paper\n")
        (self.pkg / "data.txt").write_text("original\n")
        self.commit(self.dev, "source")

    def run_cmd(self, args, cwd, env=None):
        return subprocess.run([str(a) for a in args], cwd=cwd, env=env or self.env,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def git(self, cwd, *args):
        p = self.run_cmd(["git", *args], cwd)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def commit(self, repo, subject):
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-m", subject)
        return self.git(repo, "rev-parse", "HEAD")

    def publish(self, *args, ok=True, env=None):
        p = self.run_cmd(["bash", SCRIPTS / "publish.sh", "--agg-wt", self.agg,
                          "--agg-url", self.origin, *args],
                         self.root if "--vendor-url" in args else self.dev, env)
        self.assertEqual(p.returncode == 0, ok, p.stdout + p.stderr)
        return p

    def baseline(self):
        self.publish()

    def remote_edit(self, ref="skill/paper", edit=None):
        clone = self.root / ("writer" + str(len(list(self.root.glob("writer*")))))
        self.git(self.root, "clone", "--branch", ref, str(self.origin), str(clone))
        package = clone / "skills/paper" if ref == "main" else clone
        if edit is None:
            (package / "data.txt").write_text("target correction\n")
        else:
            edit(package)
        sha = self.commit(clone, "target correction")
        self.git(clone, "push", "origin", ref)
        self.git(self.agg, "fetch", "origin")
        if ref == "main":
            self.git(self.agg, "merge", "--ff-only", "origin/main")
        else:
            self.git(self.agg, "branch", "-f", ref, "origin/" + ref)
        return sha

    def tips(self):
        return self.git(self.origin, "show-ref", "--heads"), self.git(self.agg, "show-ref", "--heads")

    def test_aligned_and_absent_local_branch_block_all_modes_without_writes(self):
        self.baseline()
        sha = self.remote_edit()
        for absent in (False, True):
            if absent:
                self.git(self.agg, "branch", "-D", "skill/paper")
            for mode in ((), ("--dry-run",), ("--only-main",), ("--only-skill-branch",)):
                with self.subTest(absent=absent, mode=mode):
                    before = self.tips()
                    p = self.publish(*mode, ok=False)
                    self.assertIn("origin/skill/paper", p.stderr)
                    self.assertIn(sha, p.stderr)
                    self.assertIn("data.txt", p.stderr)
                    self.assertEqual(self.tips(), before)
                    self.assertEqual((self.agg / "skills/paper/data.txt").read_text(), "original\n")

    def test_preserved_correction_allows_unrelated_upgrade_and_real_local_push(self):
        self.baseline()
        self.remote_edit()
        (self.pkg / "data.txt").write_text("target correction\n")
        (self.pkg / "profiles.txt").write_text("eight profiles\n")
        self.publish()
        for ref, prefix in (("main", "skills/paper/"), ("skill/paper", "")):
            self.assertEqual(self.git(self.origin, "show", ref + ":" + prefix + "data.txt"), "target correction")
            self.assertEqual(self.git(self.origin, "show", ref + ":" + prefix + "profiles.txt"), "eight profiles")

    def test_review_exact_sha_and_stale_or_invalid_acknowledgements(self):
        self.baseline()
        sha = self.remote_edit()
        (self.pkg / "data.txt").write_text("reviewed evolution\n")
        self.publish(ok=False)
        for value in ("origin/skill/paper=" + sha[:12], "origin/missing=" + sha, "*=true", "origin/main=" + sha):
            self.publish("--reviewed-target", value, "--dry-run", ok=False)
        self.publish("--reviewed-target", "origin/skill/paper=" + sha,
                     "--reviewed-target", "origin/main=" + self.git(self.agg, "rev-parse", "origin/main"),
                     "--dry-run")
        newer = self.remote_edit(edit=lambda p: (p / "later.txt").write_text("later\n"))
        p = self.publish("--reviewed-target", "origin/skill/paper=" + sha, ok=False)
        self.assertIn(newer, p.stderr)
        self.publish("--reviewed-target", "origin/skill/paper=" + newer,
                     "--reviewed-target", "origin/main=" + self.git(self.agg, "rev-parse", "origin/main"))

    def test_main_only_correction_is_checked_even_for_skill_only(self):
        self.baseline()
        sha = self.remote_edit("main")
        before = self.tips()
        p = self.publish("--only-skill-branch", ok=False)
        self.assertIn(sha, p.stderr)
        self.assertEqual(self.tips(), before)
        (self.pkg / "data.txt").write_text("target correction\n")
        self.publish()

    def test_deletions_additions_modes_spaces_and_symlinks(self):
        (self.pkg / "deleted.txt").write_text("remove me\n")
        (self.pkg / "executable").write_text("#!/bin/sh\n")
        (self.pkg / "link").symlink_to("data.txt")
        self.baseline()
        def changes(p):
            (p / "deleted.txt").unlink()
            (p / "space name.txt").write_text("added\n")
            (p / "executable").chmod(0o755)
            (p / "link").unlink()
            (p / "link").symlink_to("executable")
        self.remote_edit(edit=changes)
        self.publish(ok=False)
        changes(self.pkg)
        self.publish()
        self.assertIn("100755", self.git(self.origin, "ls-tree", "skill/paper", "executable"))
        self.assertIn("120000", self.git(self.origin, "ls-tree", "skill/paper", "link"))
        self.assertEqual(self.git(self.origin, "show", "skill/paper:link"), "executable")
        self.assertEqual(self.git(self.origin, "ls-tree", "skill/paper", "deleted.txt"), "")

    def test_existing_target_without_known_baseline_requires_exact_tree(self):
        self.git(self.agg, "checkout", "--orphan", "skill/paper")
        self.git(self.agg, "rm", "-rf", ".")
        for file in self.pkg.iterdir():
            shutil.copy2(file, self.agg / file.name)
        self.commit(self.agg, "unrecognized package import")
        self.git(self.agg, "push", "origin", "skill/paper")
        self.git(self.agg, "checkout", "main")
        self.publish("--dry-run")
        (self.pkg / "data.txt").write_text("different\n")
        self.publish("--dry-run", ok=False)

    def test_custom_directory_and_branch_prefix_baselines(self):
        flags = ("--agg-skills-dir", "packages", "--skill-branch-prefix", "pkg/")
        self.publish(*flags)
        self.publish(*flags, "--dry-run")
        self.assertEqual(self.git(self.origin, "show", "main:packages/paper/data.txt"), "original")
        self.assertEqual(self.git(self.origin, "show", "pkg/paper:data.txt"), "original")

    def test_step_two_fetch_rechecks_only_skill_snapshot(self):
        self.baseline()
        old_skill = self.git(self.origin, "rev-parse", "skill/paper")
        writer = self.root / "race-writer"
        self.git(self.root, "clone", "--branch", "skill/paper", str(self.origin), str(writer))
        (writer / "data.txt").write_text("racing correction\n")
        new_skill = self.commit(writer, "racing correction")
        self.git(writer, "push", "origin", "HEAD:refs/heads/race-prepared")
        hook = self.origin / "hooks/post-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                        "  if [ \"$ref\" = refs/heads/main ]; then\n"
                        f"    git update-ref refs/heads/skill/paper {new_skill} {old_skill}\n"
                        "  fi\ndone\n")
        hook.chmod(0o755)
        (self.pkg / "profiles.txt").write_text("source upgrade\n")
        p = self.publish("--reviewed-target", "origin/skill/paper=" + old_skill, ok=False)
        self.assertIn(new_skill, p.stderr)
        self.assertEqual(self.git(self.origin, "rev-parse", "skill/paper"), new_skill)
        self.assertEqual(self.git(self.origin, "show", "skill/paper:data.txt"), "racing correction")

    def test_unknown_main_baseline_requires_equality_or_explicit_review(self):
        destination = self.agg / "skills/paper"
        shutil.copytree(self.pkg, destination)
        self.commit(self.agg, "manual import without publication subject")
        self.git(self.agg, "push", "origin", "main")
        self.publish("--dry-run")
        (self.pkg / "data.txt").write_text("source evolved\n")
        self.publish("--dry-run", ok=False)
        self.publish("--dry-run", "--reviewed-target",
                     "origin/main=" + self.git(self.agg, "rev-parse", "origin/main"))

    def install_external_main_update_hook(self):
        hook = self.origin / "hooks/post-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                        "  if [ \"$ref\" = refs/heads/main ] && [ ! -f hooks/raced ]; then\n"
                        "    touch hooks/raced\n"
                        "    tree=$(git rev-parse \"$new^{tree}\") || exit 1\n"
                        "    extra=$(printf 'external main update\\n' | git commit-tree \"$tree\" -p \"$new\") || exit 1\n"
                        "    git update-ref refs/heads/main \"$extra\" \"$new\" || exit 1\n"
                        "  fi\ndone\n")
        hook.chmod(0o755)

    def assert_multi_package_main_review(self, external=False):
        second = self.dev / "second"
        shutil.copytree(self.pkg, second)
        (second / "SKILL.md").write_text("---\nname: second\ndescription: fixture\n---\n# Second\n")
        (self.dev / ".skills").write_text("paper\nsecond\n")
        initial = self.git(self.agg, "rev-parse", "origin/main")
        if external:
            self.install_external_main_update_hook()
        p = self.publish("--only-main", "--reviewed-target", "origin/main=" + initial, ok=not external)
        self.assertEqual(self.git(self.origin, "show", "main:skills/paper/data.txt"), "original")
        if external:
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("main", p.stderr)
        else:
            self.assertEqual(self.git(self.origin, "show", "main:skills/second/data.txt"), "original")

    def test_multiple_packages_advance_only_own_main_review(self):
        self.assert_multi_package_main_review()

    def test_multiple_packages_do_not_acknowledge_external_main_update(self):
        self.assert_multi_package_main_review(external=True)

    def assert_multi_vendor_main_review(self, external=False):
        vendor = self.root / "vendor.git"
        self.git(self.root, "clone", "--bare", str(self.dev), str(vendor))
        env = dict(self.env, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="url." + str(self.root) + "/.insteadOf",
                   GIT_CONFIG_VALUE_0="https://github.com/fixture/")
        url = "https://github.com/fixture/vendor/tree/main/paper"
        audit = self.agg / ".vendor-audit.jsonl"
        audit.write_text("".join(json.dumps({"skill": skill, "url": url, "commit": ""}) + "\n"
                                 for skill in ("paper", "second")))
        self.commit(self.agg, "fixture vendor entries")
        self.git(self.agg, "push", "origin", "main")
        initial = self.git(self.agg, "rev-parse", "main")
        if external:
            self.install_external_main_update_hook()
        p = self.run_cmd(["bash", SCRIPTS / "update-vendor.sh", "--agg-wt", self.agg,
                          "--agg-url", self.origin, "--only-main", "--reviewed-target",
                          "origin/main=" + initial], self.dev, env)
        self.assertEqual(p.returncode == 0, not external, p.stdout + p.stderr)
        self.assertEqual(self.git(self.origin, "show", "main:skills/paper/data.txt"), "original")
        if not external:
            self.assertEqual(self.git(self.origin, "show", "main:skills/second/data.txt"), "original")

    @unittest.skipUnless(shutil.which("jq"), "update-vendor.sh requires existing jq")
    def test_multiple_vendor_entries_advance_only_own_main_review(self):
        self.assert_multi_vendor_main_review()

    @unittest.skipUnless(shutil.which("jq"), "update-vendor.sh requires existing jq")
    def test_multiple_vendor_entries_do_not_acknowledge_external_main_update(self):
        self.assert_multi_vendor_main_review(external=True)

    @unittest.skipUnless(shutil.which("jq"), "update-vendor.sh requires existing jq")
    def test_vendor_cli_uses_same_guard_without_network_or_target_changes(self):
        vendor = self.root / "vendor.git"
        self.git(self.root, "clone", "--bare", str(self.dev), str(vendor))
        env = dict(self.env, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="url." + str(self.root) + "/.insteadOf",
                   GIT_CONFIG_VALUE_0="https://github.com/fixture/")
        url = "https://github.com/fixture/vendor/tree/main/paper"
        self.publish("--vendor-url", url, "--skill", "paper", env=env)
        self.assertTrue(self.git(self.origin, "show", "main:skills/paper/README.md").startswith("# paper"))
        self.assertEqual(self.git(self.origin, "ls-tree", "skill/paper", "README.md"), "")
        # Ensure upstream advances, so the batch does not legitimately skip an unchanged audit entry.
        (self.pkg / "upstream.txt").write_text("new upstream\n")
        self.commit(self.dev, "upstream update")
        self.git(self.dev, "push", str(vendor), "main")
        self.remote_edit()
        before = self.tips()
        for flags in ((), ("--dry-run",), ("--only-main",), ("--only-skill-branch",)):
            p = self.run_cmd(["bash", SCRIPTS / "update-vendor.sh", "--agg-wt", self.agg,
                              "--agg-url", self.origin, *flags], self.dev, env)
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("reconciliation", p.stderr)
            self.assertEqual(self.tips(), before)
        paper_tree = self.git(self.origin, "rev-parse", "main:skills/paper")
        skill_tip = self.git(self.origin, "rev-parse", "skill/paper")
        audit = self.agg / ".vendor-audit.jsonl"
        with audit.open("a") as stream:
            stream.write(json.dumps({"skill": "independent", "url": url, "commit": ""}) + "\n")
        self.commit(self.agg, "fixture independent vendor entry")
        self.git(self.agg, "push", "origin", "main")
        p = self.run_cmd(["bash", SCRIPTS / "update-vendor.sh", "--agg-wt", self.agg,
                          "--agg-url", self.origin], self.dev, env)
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.git(self.origin, "rev-parse", "main:skills/paper"), paper_tree)
        self.assertEqual(self.git(self.origin, "rev-parse", "skill/paper"), skill_tip)
        self.assertEqual(self.git(self.origin, "show", "skill/independent:upstream.txt"), "new upstream")


if __name__ == "__main__":
    unittest.main()
