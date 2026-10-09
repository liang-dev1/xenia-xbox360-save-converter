"""Collect notices for the Windows portable EXE from its pinned build inputs.

Run with the same Python environment used by PyInstaller, after freezing the app.
The Rust list is a conservative Cargo.lock superset, not a claim about which
crates the published cryptography wheel actually compiled.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from importlib import metadata
import io
import json
from pathlib import Path, PurePosixPath
import ssl
import sys
import tarfile
import tkinter
import tomllib
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".local" / "license-cache"
CRYPTO_SDIST_SHA256 = "7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5"
PYINSTALLER_SDIST_SHA256 = "05eb2f5615503e72939a7224d68b4aff572c6b0438ee4a17d0a4b481f399362d"
OPENSSL_TAGS = {"3.0.19", "4.0.3"}
OPENSSL_LICENSE_SHA256 = "7d5450cb2d142651b8afa315b5f238efc805dad827d91ba367d8516bc9d49e7a"
TCL_LICENSE_SHA256 = "c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16"
LICENSE_NAMES = ("license", "licence", "copying", "notice", "copyright")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def save_bytes(output, target, data, source, entries, **details):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    entries.append({"path": target.relative_to(output).as_posix(), "source": source,
                    "sha256": sha256(data), "bytes": len(data), **details})


def fetch(url, cache_path, expected=None):
    if cache_path.exists():
        data = cache_path.read_bytes()
        if expected is None or sha256(data) == expected:
            return data
    with urlopen(url, timeout=45) as response:
        data = response.read()
    if expected is not None and sha256(data) != expected:
        raise ValueError(f"SHA-256 mismatch: {url}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    return data


def packaged_licenses(name):
    dist = metadata.distribution(name)
    found = []
    for item in dist.files or []:
        path = PurePosixPath(str(item).replace("\\", "/"))
        if not any(part.endswith(".dist-info") for part in path.parts[:-1]):
            continue
        if path.name.lower().startswith(LICENSE_NAMES):
            actual = Path(dist.locate_file(item))
            if actual.is_file():
                found.append((path.name, actual.read_bytes(), str(path)))
    if not found:
        raise ValueError(f"No installed license texts for {name} {dist.version}")
    return dist.version, found


def collect_crate(package):
    name, version = package["name"], package["version"]
    expected = package["checksum"]
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    raw = fetch(url, CACHE / "crates" / f"{name}-{version}.crate", expected)
    files = []
    manifest = None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != f"{name}-{version}":
                raise ValueError(f"unsafe crate archive member: {member.name}")
            if len(rel.parts) == 2 and rel.name == "Cargo.toml.orig":
                manifest = tomllib.loads(archive.extractfile(member).read().decode("utf-8"))
            elif len(rel.parts) == 2 and rel.name == "Cargo.toml" and manifest is None:
                manifest = tomllib.loads(archive.extractfile(member).read().decode("utf-8"))
            elif rel.name.lower().startswith(LICENSE_NAMES):
                files.append((str(PurePosixPath(*rel.parts[1:])), archive.extractfile(member).read()))
    if manifest is None:
        raise ValueError(f"Cargo.toml missing: {name} {version}")
    meta = manifest.get("package", {})
    expression = meta.get("license")
    license_file = meta.get("license-file")
    if not expression and not license_file:
        raise ValueError(f"license declaration missing: {name} {version}")
    if not files:
        raise ValueError(f"license/notice text missing: {name} {version} ({expression or license_file})")
    if license_file and not any(path == license_file for path, _ in files):
        raise ValueError(f"declared license-file missing: {name} {version}: {license_file}")
    return package, url, expression, license_file, files


def cryptography_lock():
    url = "https://files.pythonhosted.org/packages/source/c/cryptography/cryptography-50.0.2.tar.gz"
    local = ROOT / ".research" / "gui-build" / "cryptography-50.0.2.tar.gz"
    if local.is_file() and sha256(local.read_bytes()) == CRYPTO_SDIST_SHA256:
        archive_bytes = local.read_bytes()
    else:
        archive_bytes = fetch(url, CACHE / "cryptography-50.0.2.tar.gz", CRYPTO_SDIST_SHA256)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        lock_bytes = archive.extractfile("cryptography-50.0.2/Cargo.lock").read()
    return tomllib.loads(lock_bytes.decode("utf-8")), url


def pyinstaller_zlib_license():
    url = "https://files.pythonhosted.org/packages/source/p/pyinstaller/pyinstaller-6.22.3.tar.gz"
    local = ROOT / ".research" / "gui-build" / "pyinstaller-6.22.3.tar.gz"
    if local.is_file() and sha256(local.read_bytes()) == PYINSTALLER_SDIST_SHA256:
        archive_bytes = local.read_bytes()
    else:
        archive_bytes = fetch(url, CACHE / "pyinstaller-6.22.3.tar.gz", PYINSTALLER_SDIST_SHA256)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        license_bytes = archive.extractfile("pyinstaller-6.22.3/bootloader/zlib/LICENSE").read()
    return license_bytes, url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error(f"output already exists: {out}")
    if out.parent.name != "XSaveConverter" or not (out.parent / "XSaveConverter.exe").is_file():
        parser.error("output must be THIRD_PARTY in an existing XSaveConverter bundle")
    if not out.is_relative_to(ROOT / ".local"):
        parser.error("output must stay under project .local")
    if sys.platform != "win32" or sys.version_info[:3] != (3, 14, 4):
        parser.error("official Windows CPython 3.14.4 build environment is required")
    if metadata.version("cryptography") != "50.0.2":
        parser.error("pinned cryptography 50.0.2 is required")
    from cryptography.hazmat.backends.openssl.backend import backend
    crypto_openssl = backend.openssl_version_text()
    if ssl.OPENSSL_VERSION.split()[1] != "3.0.19" or crypto_openssl.split()[1] != "4.0.3":
        parser.error("OpenSSL runtime versions differ from the two pinned notice texts")
    tcl_version = tkinter.Tcl().eval("info patchlevel")
    if tcl_version != "8.6.15":
        parser.error("Tcl runtime differs from the pinned Tcl 8.6.15 notice")
    lock, sdist_url = cryptography_lock()
    crates = [item for item in lock["package"] if item.get("source", "").startswith("registry+")]
    # Fetch and checksum-verify all crates before writing notices; an incomplete
    # network run must never produce a seemingly complete notice directory.
    with ThreadPoolExecutor(max_workers=6) as pool:
        crate_results = list(pool.map(collect_crate, crates))
    package_names = ("cryptography", "cffi", "pycparser", "PyInstaller", "pyinstaller-hooks-contrib")
    package_results = {name: packaged_licenses(name) for name in package_names}
    zlib_license, pyinstaller_sdist_url = pyinstaller_zlib_license()
    base = Path(sys.base_prefix)
    python_license = (base / "LICENSE.txt").read_bytes()
    tk_license = (base / "tcl" / "tk8.6" / "license.terms").read_bytes()
    tcl_url = "https://raw.githubusercontent.com/tcltk/tcl/core-8-6-15/license.terms"
    tcl_license = fetch(tcl_url, CACHE / "tcl-8.6.15-license.terms", TCL_LICENSE_SHA256)
    openssl_results = []
    for version in sorted(OPENSSL_TAGS):
        url = f"https://raw.githubusercontent.com/openssl/openssl/openssl-{version}/LICENSE.txt"
        data = fetch(url, CACHE / f"openssl-{version}-LICENSE.txt", OPENSSL_LICENSE_SHA256)
        openssl_results.append((version, url, data))
    out.mkdir(parents=True)
    entries = []
    package_inventory = []
    for name in package_names:
        version, licenses = package_results[name]
        package_inventory.append({"name": name, "version": version,
                                  "role": "build-environment-only" if name == "pycparser" else
                                          "runtime-or-backend" if name in package_names[:2] else
                                          "build-tool-and-embedded-hook-notices",
                                  "license_expression": metadata.distribution(name).metadata.get("License-Expression")})
        for filename, content, source in licenses:
            save_bytes(out, out / "python-packages" / name / filename, content,
                       f"installed:{name}:{source}", entries, package=name, version=version)
    save_bytes(out, out / "pyinstaller-bootloader" / "zlib-LICENSE", zlib_license,
               f"{pyinstaller_sdist_url}!/bootloader/zlib/LICENSE", entries,
               package="zlib", version="PyInstaller 6.22.3 bootloader copy")
    save_bytes(out, out / "python" / "LICENSE.txt", python_license,
               "installed-CPython/LICENSE.txt", entries, package="CPython", version=sys.version.split()[0])
    save_bytes(out, out / "tcl-tk" / "tk-license.terms", tk_license,
               "installed-Tk/tk8.6/license.terms", entries,
               package="Tk", version="8.6.15")
    save_bytes(out, out / "tcl-tk" / "tcl-license.terms", tcl_license,
               tcl_url, entries, package="Tcl", version="8.6.15")
    openssl_inventory = []
    for version, url, data in openssl_results:
        save_bytes(out, out / "openssl" / version / "LICENSE.txt", data, url, entries,
                   package="OpenSSL", version=version)
        openssl_inventory.append({"version": version, "license_source": url,
                                  "license_sha256": sha256(data)})
    crate_inventory = []
    for package, url, expression, license_file, files in crate_results:
        name, version = package["name"], package["version"]
        for filename, data in files:
            save_bytes(out, out / "rust-crates" / f"{name}-{version}" / filename, data,
                       f"{url}!/{filename}", entries, package=name, version=version)
        crate_inventory.append({"name": name, "version": version, "source": url,
                                "archive_sha256": package["checksum"], "license": expression,
                                "license_file": license_file,
                                "notice_files": [filename for filename, _ in files]})
    manifest = {"scope": "conservative-cargo-lock-superset; not an exact compiled-crate SBOM",
                "python": sys.version, "stdlib_openssl": ssl.OPENSSL_VERSION,
                "cryptography_openssl": crypto_openssl, "tcl_version": tcl_version,
                "python_packages": package_inventory, "openssl": openssl_inventory,
                "cryptography_sdist": {"url": sdist_url, "sha256": CRYPTO_SDIST_SHA256},
                "pyinstaller_sdist": {"url": pyinstaller_sdist_url, "sha256": PYINSTALLER_SDIST_SHA256},
                "rust_crates": crate_inventory, "files": entries}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Collected {len(entries)} license/notice files for {len(crate_inventory)} locked crates: {out}")


if __name__ == "__main__":
    main()
