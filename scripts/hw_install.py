#!/usr/bin/env python3
"""Install hw_forge's optional third-party toolchain, exactly as verified.

Three pieces of software are not part of any KiCad install and are not
fetched by anything else in this repository: the Freerouting jar
(`scripts/kicad_route.py`'s `route`), the Fabrication Toolkit JLCPCB plugin
(`kb/fabs/jlcpcb.md`), and KiCadRoutingTools (`scripts/kicad_route.py`'s
`route-krt`). This script codifies exactly the install performed and
measured on this machine on 2026-09-20 (`references/autorouting.md` §6,
`kb/runs/hexpad-autoroute-2026-09-20.md`), so a new machine gets the same
toolchain, at the same pinned versions, in one command.

    python3 scripts/hw_install.py --check          # report only, changes nothing
    python3 scripts/hw_install.py --router          # Freerouting jar
    python3 scripts/hw_install.py --jlc-plugin      # Fabrication Toolkit, KiCad 10
    python3 scripts/hw_install.py --routing-tools   # KiCadRoutingTools + its venv
    python3 scripts/hw_install.py --all             # all three

Every fetch prints its URL before downloading. Every checksum is a pinned
SHA-256, verified after download and before the file is used anywhere;
a mismatch is a hard failure with no fallback. On any failure, the exact
manual command is printed, the same one this script would have run, so a
network problem never leaves you without a next step.

**`--check` never downloads, clones, or writes anything.** It only reports
what is present, at what version, and whether each component's own smoke
test passes. `--router`, `--jlc-plugin`, and `--routing-tools` are each
idempotent (safe to re-run; they skip work that is already correctly in
place) but each performs real network fetches, which is why this script's own
regression pass runs `--check` only, never the installing paths.

Discovery is shared, not duplicated: the router-related `--check` calls
`kicad_route.find_java` / `find_freerouting_jar` / `find_krt_root` /
`find_krt_venv_python` directly, the same functions `kicad_route.py` itself
uses, so the two scripts can never disagree about where a tool lives.

stdlib only. Downloads use `urllib.request`; archives use `zipfile`; the git
clone and `build_router.py` / `pip` steps shell out via `subprocess`. No
third-party package is required to run this installer itself; the venv it
creates for KiCadRoutingTools has its own requirements, installed by `pip`
inside that venv, not by this script's own interpreter.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

sys.dont_write_bytecode = True      # never leave __pycache__ behind
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_route   # share find_java / find_freerouting_jar / KRT discovery


# ------------------------------------------------------------- Freerouting

FREEROUTING_VERSION = "2.4.1"
FREEROUTING_SHA256 = ("251101c3eeac22d7e7dfcf6796603279e5d1000283eb82d8"
                      "f093780f7afc6aa9")
FREEROUTING_SIZE = 64076787
FREEROUTING_URL = (
    "https://github.com/freerouting/freerouting/releases/download/v%s/"
    "freerouting-%s.jar" % (FREEROUTING_VERSION, FREEROUTING_VERSION))
FREEROUTING_DIR = os.path.expanduser("~/.freerouting")
FREEROUTING_JAR = os.path.join(FREEROUTING_DIR,
                               "freerouting-%s.jar" % FREEROUTING_VERSION)
FREEROUTING_LINK = os.path.join(FREEROUTING_DIR, "freerouting.jar")

FREEROUTING_SMOKE_TIMEOUT_S = 30


# ------------------------------------------------------------- JLC plugin

JLC_PLUGIN_VERSION = "5.3.1"
JLC_PLUGIN_SHA256 = ("80b05531c887cca4c7d801c6613e3fdbe17ae5ec8b802e87a6"
                     "d16c3b9a0f4c45")
JLC_PLUGIN_URL = (
    "https://github.com/bennymeg/Fabrication-Toolkit/releases/download/"
    "%s/Fabrication-Toolkit-%s.zip" % (JLC_PLUGIN_VERSION, JLC_PLUGIN_VERSION))
JLC_PLUGIN_MODULE = "com_github_bennymeg_JLC-Plugin-for-KiCad"
JLC_PLUGIN_DIR = os.path.expanduser(
    "~/Documents/KiCad/10.0/3rdparty/plugins/" + JLC_PLUGIN_MODULE)
JLC_RESOURCES_DIR = os.path.expanduser(
    "~/Documents/KiCad/10.0/3rdparty/resources/" + JLC_PLUGIN_MODULE)
# Files expected inside the module directory after extraction, per the
# 5.3.1 zip layout read directly on 2026-09-20.
JLC_PLUGIN_FILES = ("cli.py", "plugin.py", "process.py", "thread.py",
                    "utils.py", "options.py", "config.py", "events.py",
                    "transformations.csv", "metadata.json", "icon.png")


# --------------------------------------------------------- KiCadRoutingTools

KRT_COMMIT = "ab8d0c3648209d6a2ac6c1c0fb71a0ddcb545aa6"
KRT_GIT_URL = "https://github.com/drandyhaas/KiCadRoutingTools.git"
KRT_ROOT = os.path.expanduser(
    os.environ.get("KRT_ROOT") or "~/.hw_forge/KiCadRoutingTools")
KRT_VENV = os.path.expanduser(os.environ.get("KRT_VENV") or "~/.hw_forge/venv")

KRT_SMOKE_IMPORTS = ("numpy", "scipy", "shapely", "PIL")


# ------------------------------------------------------------------ helpers

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, out_path, expect_sha256=None, expect_size=None):
    """Fetch `url` to `out_path`, verifying the pinned checksum.

    Downloads to a sibling temp file first and renames on success, so a
    failed or interrupted download never leaves a file that LOOKS installed
    at `out_path`.
    """
    print("  fetching %s" % url)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(out_path) or ".",
                                        prefix=".hw_install-")
    os.close(tmp_fd)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, \
             open(tmp_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        size = os.path.getsize(tmp_path)
        if expect_size is not None and size != expect_size:
            raise SystemExit(
                "error: %s downloaded as %d bytes, expected %d\n"
                "  fix: re-run, or fetch by hand:\n"
                "       curl -L -o %s %s" % (url, size, expect_size,
                                              out_path, url))
        if expect_sha256 is not None:
            got = sha256_of(tmp_path)
            if got != expect_sha256:
                raise SystemExit(
                    "error: %s SHA-256 mismatch\n"
                    "  expected %s\n"
                    "  got      %s\n"
                    "  fix: this is either a network problem or the "
                    "upstream file changed under a\n"
                    "       version this script still has pinned to the "
                    "old hash. Do not use it.\n"
                    "       Re-run, or investigate by hand:\n"
                    "       curl -L -o %s %s" % (url, expect_sha256, got,
                                                  out_path, url))
        os.replace(tmp_path, out_path)
        print("  verified sha256 %s" % (expect_sha256 or "(unchecked)"))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def run_logged(argv, cwd=None, timeout=None):
    print("  %s" % " ".join(argv))
    proc = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True,
                          timeout=timeout)
    if proc.stdout:
        for line in proc.stdout.splitlines():
            print("    %s" % line)
    return proc.returncode


# --------------------------------------------------------------------- router

def router_manual_hint():
    return (
        "  manual install:\n"
        "    mkdir -p %s\n"
        "    curl -L -o %s \\\n"
        "      %s\n"
        "    ln -sf %s %s"
        % (FREEROUTING_DIR, FREEROUTING_JAR, FREEROUTING_URL,
           os.path.basename(FREEROUTING_JAR), FREEROUTING_LINK))


def install_router():
    print("--- Freerouting v%s ---" % FREEROUTING_VERSION)
    if os.path.isfile(FREEROUTING_JAR):
        got = sha256_of(FREEROUTING_JAR)
        if got == FREEROUTING_SHA256:
            print("  already present and verified: %s" % FREEROUTING_JAR)
        else:
            raise SystemExit(
                "error: %s exists but its SHA-256 does not match the "
                "pinned v%s hash\n  (got %s)\n  fix: remove it and re-run, "
                "or investigate why it differs:\n    rm %s"
                % (FREEROUTING_JAR, FREEROUTING_VERSION, got, FREEROUTING_JAR))
    else:
        try:
            download(FREEROUTING_URL, FREEROUTING_JAR,
                    expect_sha256=FREEROUTING_SHA256,
                    expect_size=FREEROUTING_SIZE)
        except (OSError, urllib.error.URLError) as exc:
            raise SystemExit("error: download failed: %s\n%s"
                             % (exc, router_manual_hint()))

    if os.path.islink(FREEROUTING_LINK) or os.path.exists(FREEROUTING_LINK):
        if os.path.realpath(FREEROUTING_LINK) != os.path.realpath(FREEROUTING_JAR):
            os.remove(FREEROUTING_LINK)
            os.symlink(os.path.basename(FREEROUTING_JAR), FREEROUTING_LINK)
    else:
        os.symlink(os.path.basename(FREEROUTING_JAR), FREEROUTING_LINK)
    print("  symlinked %s -> %s" % (FREEROUTING_LINK,
                                    os.path.basename(FREEROUTING_JAR)))

    router_smoke_test(quiet=False)


def router_smoke_test(quiet=True):
    """Run the jar's own --help under the best `java` this machine has.

    Read-only: `--help` prints and exits, no board is loaded, no file is
    written. This is what tells "the jar is present" apart from "the jar
    actually runs on this machine's java", which v2.4.1 vs. OpenJDK 21 vs. 25
    proved is not the same question (see `kicad_route.py`'s `find_java`).
    """
    java, java_how = kicad_route.find_java()
    jar, jar_how = kicad_route.find_freerouting_jar()
    if not (java and jar):
        return False, "java=%s jar=%s" % (java or "MISSING", jar or "MISSING")
    argv = [java, "-jar", jar, "--gui.enabled=false", "--help"]
    if not quiet:
        print("  smoke test: %s" % " ".join(argv))
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True,
                              timeout=FREEROUTING_SMOKE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, ("--help did not exit within %ds: this is the same "
                       "symptom as a pre-v2.1 jar with no --gui.enabled "
                       "support (see kicad_route.py's docstring); the "
                       "process may still be running, find and end it "
                       "yourself" % FREEROUTING_SMOKE_TIMEOUT_S)
    ok = proc.returncode == 0 and "UnsupportedClassVersionError" not in (proc.stdout or "")
    detail = (proc.stdout or "").strip().splitlines()
    tail = detail[-1] if detail else "(no output)"
    if not quiet:
        for line in detail[:3]:
            print("    %s" % line)
    return ok, ("%s (java via %s, jar via %s)" % (tail, java_how, jar_how)
               if ok else
               "exit %d: %s (java via %s)" % (proc.returncode, tail, java_how))


# ------------------------------------------------------------------ jlc plugin

def jlc_manual_hint():
    return (
        "  manual install:\n"
        "    curl -L -o /tmp/Fabrication-Toolkit-%s.zip \\\n"
        "      %s\n"
        "    unzip -o /tmp/Fabrication-Toolkit-%s.zip -d %s\n"
        "    (KiCad's own PCM install does the equivalent under Preferences "
        "> Plugin and\n"
        "     Content Manager; this script reproduces that layout by hand "
        "for a headless\n"
        "     machine with no GUI session to run the PCM from)"
        % (JLC_PLUGIN_VERSION, JLC_PLUGIN_URL, JLC_PLUGIN_VERSION,
           os.path.dirname(JLC_PLUGIN_DIR)))


def jlc_plugin_status():
    """(ok, detail) for whether the pinned files are present, unchecked SHA
    (the zip's own hash is verified at download time, not re-derivable from
    the extracted, already-unpacked files)."""
    if not os.path.isdir(JLC_PLUGIN_DIR):
        return False, "not installed: %s does not exist" % JLC_PLUGIN_DIR
    missing = [f for f in JLC_PLUGIN_FILES
              if not os.path.isfile(os.path.join(JLC_PLUGIN_DIR, f))]
    if missing:
        return False, ("%s exists but is missing: %s"
                       % (JLC_PLUGIN_DIR, ", ".join(missing)))
    version = None
    meta_path = os.path.join(JLC_PLUGIN_DIR, "metadata.json")
    try:
        with open(meta_path) as fh:
            meta = json.load(fh)
        versions = meta.get("versions") or []
        version = versions[0].get("version") if versions else meta.get("version")
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return True, ("%s (version %s)" % (JLC_PLUGIN_DIR, version or "unknown"))


def install_jlc_plugin():
    print("--- Fabrication Toolkit v%s (KiCad 10) ---" % JLC_PLUGIN_VERSION)
    ok, detail = jlc_plugin_status()
    if ok:
        print("  already present: %s" % detail)
        return

    with tempfile.TemporaryDirectory(prefix="hw_install-jlc-") as tmp:
        zip_path = os.path.join(tmp, "Fabrication-Toolkit-%s.zip"
                                % JLC_PLUGIN_VERSION)
        try:
            download(JLC_PLUGIN_URL, zip_path, expect_sha256=JLC_PLUGIN_SHA256)
        except (OSError, urllib.error.URLError) as exc:
            raise SystemExit("error: download failed: %s\n%s"
                             % (exc, jlc_manual_hint()))

        extract_dir = os.path.join(tmp, "extracted")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        # The zip's own top-level layout mirrors the PCM install: a
        # `plugins/<module>` directory and a `resources/<module>` directory.
        # Locate them by name rather than assuming a fixed depth, since a
        # GitHub release zip commonly wraps everything in one extra
        # top-level folder.
        src_plugin = _find_dir(extract_dir, JLC_PLUGIN_MODULE, under="plugins")
        src_resources = _find_dir(extract_dir, JLC_PLUGIN_MODULE, under="resources")
        if not src_plugin:
            raise SystemExit(
                "error: extracted zip has no plugins/%s directory\n"
                "  fix: inspect /tmp manually, the release layout may have "
                "changed:\n    unzip -l %s" % (JLC_PLUGIN_MODULE, zip_path))

        os.makedirs(os.path.dirname(JLC_PLUGIN_DIR), exist_ok=True)
        if os.path.isdir(JLC_PLUGIN_DIR):
            shutil.rmtree(JLC_PLUGIN_DIR)
        shutil.copytree(src_plugin, JLC_PLUGIN_DIR)
        print("  installed %s" % JLC_PLUGIN_DIR)

        if src_resources:
            os.makedirs(os.path.dirname(JLC_RESOURCES_DIR), exist_ok=True)
            if os.path.isdir(JLC_RESOURCES_DIR):
                shutil.rmtree(JLC_RESOURCES_DIR)
            shutil.copytree(src_resources, JLC_RESOURCES_DIR)
            print("  installed %s" % JLC_RESOURCES_DIR)

    ok, detail = jlc_plugin_status()
    print("  %s: %s" % ("ok" if ok else "FAIL", detail))
    if not ok:
        raise SystemExit("error: install completed but the expected files "
                         "are still missing\n%s" % jlc_manual_hint())


def _find_dir(root, name, under=None):
    """First directory under `root` named `name`, optionally requiring an
    ancestor path component `under` (e.g. 'plugins' vs. 'resources'), since
    a release zip's layout commonly nests everything one level deeper than
    expected."""
    for dirpath, dirnames, _files in os.walk(root):
        if os.path.basename(dirpath) == name:
            if under is None or under in dirpath.split(os.sep):
                return dirpath
    return None


# --------------------------------------------------------- routing tools

def krt_manual_hint():
    return (
        "  manual install:\n"
        "    git clone %s %s\n"
        "    git -C %s checkout %s\n"
        "    cd %s && python3 build_router.py\n"
        "    python3 -m venv %s\n"
        "    %s/bin/pip install -r %s/requirements.txt"
        % (KRT_GIT_URL, KRT_ROOT, KRT_ROOT, KRT_COMMIT, KRT_ROOT, KRT_VENV,
           KRT_VENV, KRT_ROOT))


def krt_git_status():
    """(present, commit_or_None, matches_pinned)."""
    if not os.path.isdir(os.path.join(KRT_ROOT, ".git")):
        return False, None, False
    proc = subprocess.run(["git", "-C", KRT_ROOT, "rev-parse", "HEAD"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True)
    if proc.returncode != 0:
        return True, None, False
    commit = proc.stdout.strip()
    return True, commit, commit == KRT_COMMIT


def krt_venv_status():
    """(present, {module: version_or_error})."""
    py, _how = kicad_route.find_krt_venv_python()
    if not py:
        return False, {}
    results = {}
    for mod in KRT_SMOKE_IMPORTS:
        proc = subprocess.run(
            [py, "-c", "import %s; print(getattr(%s, '__version__', 'ok'))"
                       % (mod, mod)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True)
        if proc.returncode == 0:
            results[mod] = (proc.stdout or "").strip()
        else:
            err_lines = (proc.stderr or "").strip().splitlines()
            results[mod] = "FAIL: %s" % (err_lines[-1] if err_lines
                                         else "import failed")
    return True, results


def rust_router_status():
    """Does the prebuilt/native router extension exist under KRT_ROOT."""
    candidates = []
    rr_dir = os.path.join(KRT_ROOT, "rust_router")
    if os.path.isdir(rr_dir):
        for name in os.listdir(rr_dir):
            if name.endswith((".so", ".pyd", ".dylib")):
                candidates.append(os.path.join(rr_dir, name))
    return candidates


def install_routing_tools():
    print("--- KiCadRoutingTools @ %s ---" % KRT_COMMIT[:12])
    present, commit, matches = krt_git_status()
    if present and matches:
        print("  already present at the pinned commit: %s" % KRT_ROOT)
    elif present and not matches:
        raise SystemExit(
            "error: %s exists at commit %s, not the pinned %s\n"
            "  fix: this script does not overwrite a checkout that may "
            "hold local changes.\n"
            "       Inspect it, then either update the pin or reset it "
            "yourself:\n"
            "         git -C %s fetch && git -C %s checkout %s"
            % (KRT_ROOT, commit or "unknown", KRT_COMMIT, KRT_ROOT, KRT_ROOT,
               KRT_COMMIT))
    else:
        print("  cloning %s" % KRT_GIT_URL)
        os.makedirs(os.path.dirname(KRT_ROOT), exist_ok=True)
        rc = run_logged(["git", "clone", KRT_GIT_URL, KRT_ROOT])
        if rc != 0:
            raise SystemExit("error: git clone failed\n%s" % krt_manual_hint())
        rc = run_logged(["git", "-C", KRT_ROOT, "checkout", KRT_COMMIT])
        if rc != 0:
            raise SystemExit("error: git checkout %s failed\n%s"
                             % (KRT_COMMIT, krt_manual_hint()))

    if not rust_router_status():
        print("  building the Rust router (fetches a prebuilt binary; see "
              "build_router.py --help for --from-source)")
        rc = run_logged([sys.executable, "build_router.py"], cwd=KRT_ROOT,
                        timeout=600)
        if rc != 0:
            raise SystemExit("error: build_router.py failed\n%s"
                             % krt_manual_hint())
    else:
        print("  rust router extension already present: %s"
              % rust_router_status()[0])

    py = os.path.join(KRT_VENV, "bin", "python3")
    if not os.path.isfile(py):
        print("  creating venv: %s" % KRT_VENV)
        rc = run_logged([sys.executable, "-m", "venv", KRT_VENV])
        if rc != 0:
            raise SystemExit("error: venv creation failed\n%s"
                             % krt_manual_hint())
    else:
        print("  venv already present: %s" % KRT_VENV)

    req = os.path.join(KRT_ROOT, "requirements.txt")
    pip = os.path.join(KRT_VENV, "bin", "pip")
    print("  installing %s into the venv" % req)
    rc = run_logged([pip, "install", "-r", req], timeout=600)
    if rc != 0:
        raise SystemExit("error: pip install failed\n%s" % krt_manual_hint())

    present2, results = krt_venv_status()
    print("  smoke test:", results if present2 else "venv python not found")


# ------------------------------------------------------------------- --check

def check():
    print("--- hw_forge optional toolchain check (changes nothing) ---")
    failures = 0

    print("\nFreerouting:")
    jar, jar_how = kicad_route.find_freerouting_jar()
    java, java_how = kicad_route.find_java()
    if jar:
        got = sha256_of(jar)
        pinned = " (matches pinned v%s)" % FREEROUTING_VERSION \
            if got == FREEROUTING_SHA256 else \
            " (DOES NOT match pinned v%s hash: %s)" % (FREEROUTING_VERSION, got)
        print("  jar    %s  via %s%s" % (jar, jar_how, pinned))
    else:
        print("  jar    MISSING (%s)" % jar_how)
        print(kicad_route.jar_install_hint())
        failures += 1
    if java:
        print("  java   %s  via %s" % (java, java_how))
    else:
        print("  java   MISSING (%s)" % java_how)
        print(kicad_route.java_install_hint())
        failures += 1
    if jar and java:
        ok, detail = router_smoke_test(quiet=True)
        print("  smoke  %s: %s" % ("ok" if ok else "FAIL", detail))
        if not ok:
            failures += 1

    print("\nFabrication Toolkit (JLCPCB, KiCad 10):")
    ok, detail = jlc_plugin_status()
    print("  %s: %s" % ("ok" if ok else "MISSING", detail))
    if not ok:
        print(jlc_manual_hint())
        failures += 1

    print("\nKiCadRoutingTools:")
    present, commit, matches = krt_git_status()
    if present:
        note = "matches pinned commit" if matches else \
            "DOES NOT match pinned commit %s" % KRT_COMMIT
        print("  checkout  %s  @ %s (%s)"
             % (KRT_ROOT, (commit or "unknown")[:12], note))
        if not matches:
            failures += 1
    else:
        print("  checkout  MISSING: %s" % KRT_ROOT)
        failures += 1
    rr = rust_router_status()
    print("  router ext  %s" % (rr[0] if rr else "MISSING (run build_router.py)"))
    if not rr:
        failures += 1
    venv_present, results = krt_venv_status()
    if venv_present:
        for mod, ver in results.items():
            print("  venv %-8s %s" % (mod, ver))
            if isinstance(ver, str) and ver.startswith("FAIL"):
                failures += 1
    else:
        print("  venv      MISSING: %s" % KRT_VENV)
        failures += 1
    root_ok, root_how = kicad_route.find_krt_root()
    venv_py_ok, venv_py_how = kicad_route.find_krt_venv_python()
    print("  discovery (as kicad_route.py sees it): root=%s venv_py=%s"
         % (root_ok or "MISSING (%s)" % root_how,
            venv_py_ok or "MISSING (%s)" % venv_py_how))
    if not root_ok or not venv_py_ok:
        failures += 1

    print()
    if failures:
        print("%d component(s) need attention; commands to fix each are "
             "printed above." % failures)
    else:
        print("all optional toolchain components present and passing their "
             "smoke tests.")
    return failures


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--router", action="store_true",
                    help="install the Freerouting jar")
    ap.add_argument("--jlc-plugin", action="store_true",
                    help="install the Fabrication Toolkit JLCPCB plugin for "
                         "KiCad 10")
    ap.add_argument("--routing-tools", action="store_true",
                    help="clone KiCadRoutingTools at its pinned commit and "
                         "set up its venv")
    ap.add_argument("--all", action="store_true",
                    help="all three of the above")
    ap.add_argument("--check", action="store_true",
                    help="report what is present, at what version, and "
                         "whether each smoke test passes; changes nothing")
    args = ap.parse_args()

    if not any((args.router, args.jlc_plugin, args.routing_tools, args.all,
               args.check)):
        ap.error("pass at least one of --router --jlc-plugin "
                 "--routing-tools --all --check")

    if args.check:
        sys.exit(1 if check() else 0)

    if args.router or args.all:
        install_router()
    if args.jlc_plugin or args.all:
        install_jlc_plugin()
    if args.routing_tools or args.all:
        install_routing_tools()


if __name__ == "__main__":
    main()
