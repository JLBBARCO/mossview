from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


VERSION_LINE = re.compile(r"^(release|pre-release)=(\S+)\s*$")
PYPROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"[^"]+"')
PEP440_VERSION = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:(?P<pre>a|b|rc)(?P<pre_number>\d+))?$"
)


def read_versions(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    versions: dict[str, str] = {}
    for line in lines:
        match = VERSION_LINE.match(line)
        if match:
            versions[match.group(1)] = match.group(2)
    if set(versions) != {"release", "pre-release"}:
        raise ValueError("version.txt must define release and pre-release")
    return lines, versions


def version_exists_on_pypi(package: str, version: str) -> bool:
    try:
        with urlopen(f"https://pypi.org/pypi/{package}/json", timeout=15) as response:
            releases = json.load(response).get("releases", {})
    except (HTTPError, URLError, TimeoutError):
        return False
    return bool(releases.get(version))


def version_exists_as_tag(version: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--quiet", "--verify", f"refs/tags/v{version}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def increment(version: str, prerelease: bool) -> str:
    match = PEP440_VERSION.fullmatch(version)
    if not match:
        raise ValueError(
            f"Unsupported version '{version}'. Use MAJOR.MINOR.PATCH with an optional "
            "aN, bN, or rcN suffix."
        )

    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    pre = match.group("pre")
    pre_number = match.group("pre_number")

    if prerelease:
        if pre:
            return f"{major}.{minor}.{patch}{pre}{int(pre_number) + 1}"
        return f"{major}.{minor}.{patch + 1}b0"
    return f"{major}.{minor}.{patch + 1}"


def update_version_file(path: Path, key: str, version: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = False
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = f"{key}={version}"
            updated = True
            break
    if not updated:
        raise ValueError(f"Missing {key}= entry in {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_pyproject(path: Path, version: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = PYPROJECT_VERSION.subn(f'version = "{version}"', content, count=1)
    if count != 1:
        raise ValueError(f"Could not find project.version in {path}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: prepare_release.py <branch> <version.txt> <pyproject.toml>")

    branch, version_file_name, pyproject_name = sys.argv[1:]
    version_file = Path(version_file_name)
    pyproject = Path(pyproject_name)
    package_name = "mossview"
    key = "release" if branch == "main" else "pre-release"
    prerelease = key == "pre-release"

    _, versions = read_versions(version_file)
    version = versions[key]
    if prerelease and not re.search(r"(a|b|rc)\d+$", version):
        version = f"{version}b0"
    while version_exists_on_pypi(package_name, version) or version_exists_as_tag(version):
        version = increment(version, prerelease)

    update_version_file(version_file, key, version)
    update_pyproject(pyproject, version)

    is_prerelease = bool(re.search(r"(a|b|rc)\d+$", version))
    github_output = Path(os.environ["GITHUB_OUTPUT"])
    with github_output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")
        output.write(f"prerelease={'true' if is_prerelease else 'false'}\n")

    print(f"Using {key} version {version}")


if __name__ == "__main__":
    main()
