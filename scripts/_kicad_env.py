"""Shared KiCad toolchain discovery for the hw_forge scripts.

Not a CLI: a private helper imported by preflight.py, kicad_gate.py,
kicad_fab.py and kicad_zonefill.py so all four agree on where kicad-cli and
KiCad's bundled python live.  Python 3 stdlib only.

Discovery order, for both the CLI and the bundled interpreter:

  1. an explicit env override  (KICAD_CLI / KICAD_PYTHON — full paths)
  2. KICAD_ROOT, if set, searched over the per-platform relative candidates
  3. the platform's default install root (darwin: /Applications/KiCad/...)
  4. PATH  (shutil.which)

Every failure returned from here is a (value, how) pair, so callers can print
*where* a tool came from — a preflight that says "found on PATH" when you
expected the bundle is how a toolchain mismatch gets caught early.
"""

import os
import re
import shutil
import subprocess
import sys

# Relative paths under a KiCad install root, most-specific first.
CLI_CANDIDATES = (
    os.path.join("MacOS", "kicad-cli"),          # darwin: KiCad.app/Contents
    os.path.join("bin", "kicad-cli"),            # linux/windows prefix
    "kicad-cli",
)
PY_CANDIDATES = (
    # darwin bundle: the only interpreter on the machine that can import pcbnew
    os.path.join("Frameworks", "Python.framework", "Versions", "Current",
                 "bin", "python3"),
    os.path.join("bin", "python3"),
)

DEFAULT_ROOTS = {
    "darwin": ("/Applications/KiCad/KiCad.app/Contents",),
    "linux": ("/usr", "/usr/local"),
    "win32": (r"C:\Program Files\KiCad\10.0",
              r"C:\Program Files\KiCad\9.0"),
}

# wxWidgets prints this to stderr on every headless pcbnew call.  It is noise,
# not an error: the KiCad libraries expect a wxApp that a headless script never
# creates.  Filtered everywhere so real errors stay visible.
WX_NOISE = re.compile(r"wxApp|assert .* failed in |stdpbase\.cpp")


def default_roots():
    return DEFAULT_ROOTS.get(sys.platform, ("/usr", "/usr/local"))


def _first_existing(root, candidates):
    for rel in candidates:
        p = os.path.join(root, rel)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _find(env_var, candidates, exe_name):
    """Return (path_or_None, how_string)."""
    override = os.environ.get(env_var)
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override, "%s=%s" % (env_var, override)
        return None, "%s=%s (not an executable file)" % (env_var, override)

    root = os.environ.get("KICAD_ROOT")
    if root:
        hit = _first_existing(root, candidates)
        if hit:
            return hit, "KICAD_ROOT=%s" % root
        return None, "KICAD_ROOT=%s (no %s under it)" % (root, exe_name)

    for cand_root in default_roots():
        hit = _first_existing(cand_root, candidates)
        if hit:
            return hit, "default install root %s" % cand_root

    hit = shutil.which(exe_name)
    if hit:
        return hit, "PATH"
    return None, "not found (checked KICAD_ROOT, %s, PATH)" % (
        ", ".join(default_roots()))


def find_cli():
    """(path, how) for kicad-cli."""
    return _find("KICAD_CLI", CLI_CANDIDATES, "kicad-cli")


def find_python():
    """(path, how) for a python that can import pcbnew.

    On darwin only KiCad's bundled interpreter can; on linux the distro
    packages pcbnew for the system python, so `sys.executable` is a legitimate
    answer and is offered as a last resort.
    """
    path, how = _find("KICAD_PYTHON", PY_CANDIDATES, "python3")
    if path:
        return path, how
    if have_pcbnew(sys.executable):
        return sys.executable, "the running interpreter (pcbnew importable)"
    return None, how


def run(argv, **kw):
    """subprocess.run with output captured as text and wx noise stripped.

    PYTHONDONTWRITEBYTECODE is forced on for every child: these tools probe
    other people's project trees, and a tool that was only asked to look must
    not leave __pycache__ directories behind in what it examined.
    """
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    env = dict(kw.pop("env", None) or os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(argv, universal_newlines=True, env=env, **kw)
    proc.stderr = strip_wx_noise(proc.stderr or "")
    return proc


def strip_wx_noise(text):
    return "\n".join(l for l in text.splitlines() if not WX_NOISE.search(l))


def cli_version(cli):
    """kicad-cli's version string, or None if it will not run."""
    try:
        proc = run([cli, "version"])
    except OSError:
        return None
    out = (proc.stdout or "").strip()
    return out.splitlines()[0].strip() if out else None


def have_pcbnew(python):
    """(ok, detail) — can `python` import pcbnew, and at what version."""
    try:
        proc = run([python, "-c",
                    "import pcbnew;print(pcbnew.GetBuildVersion())"])
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, detail[-1] if detail else "import failed"
    return True, (proc.stdout or "").strip()


def require_pcbnew(script_name):
    """Import and return pcbnew, or exit with the exact re-run command.

    Called by scripts that must run *under* the bundled interpreter.  Running
    them under the system python is the single most common mistake, so the
    error carries the command line that fixes it rather than a traceback.
    """
    try:
        import pcbnew                                  # noqa: F401
        return pcbnew
    except ImportError:
        pass
    kpy, how = find_python()
    here = os.path.abspath(script_name)
    if kpy and kpy != sys.executable:
        msg = ("this interpreter (%s) cannot import pcbnew.\n"
               "  fix: %s %s %s\n"
               "       (bundled python found via %s)"
               % (sys.executable, kpy, here,
                  " ".join(sys.argv[1:]) or "<args>", how))
    else:
        msg = ("no python on this machine can import pcbnew (%s).\n"
               "  fix: install KiCad 10, then re-run with its bundled "
               "interpreter, or set KICAD_PYTHON=/path/to/python3" % how)
    raise SystemExit("error: " + msg)


def kicad_version_tuple(version_string):
    """'10.0.5' (or a longer banner) -> (10, 0, 5); () if unparseable."""
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_string or "")
    if not m:
        return ()
    return tuple(int(g) for g in m.groups() if g is not None)
