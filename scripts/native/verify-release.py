"""Verify all shipped file hashes, frozen source modules and ZIP membership/CRC."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib
import types
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mshub import __version__


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized(code):
    if not isinstance(code, types.CodeType):
        return code
    return code.replace(co_filename="", co_firstlineno=1, co_linetable=b"",
                        co_consts=tuple(normalized(value) for value in code.co_consts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    package = next(p for p in locked["package"] if p["name"] == "mshub")
    web = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    web_lock = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
    assert project["project"]["version"] == package["version"] == web["version"] == web_lock["version"] == web_lock["packages"][""]["version"] == __version__
    assert "native" in package["optional-dependencies"]
    release = ROOT / f"release/native-v{__version__}"
    bundle = release / "123mshub"
    manifest_path = bundle / "RELEASE-MANIFEST.json"
    files = {p.relative_to(bundle).as_posix(): digest(p) for p in sorted(bundle.rglob("*"))
             if p.is_file() and p != manifest_path}
    if args.manifest_only:
        manifest_path.write_text(json.dumps({"product": "123mshub", "version": __version__,
                                            "design_system": "HAUI 0.1.0 native adapter",
                                            "files": files}, indent=2), encoding="utf-8")
        print(f"Manifest: {len(files)} files")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == __version__ and manifest["files"] == files
    from PyInstaller.archive.readers import CArchiveReader
    exe = bundle / "123mshub.exe"
    archive = CArchiveReader(str(exe))
    pyz = archive.open_embedded_archive("PYZ.pyz")
    modules = []
    for module in sorted(pyz.toc):
        if module != "mshub" and not module.startswith("mshub."):
            continue
        source = ROOT / "src" / (module.replace(".", "/") + ".py")
        if not source.is_file():
            source = source.with_suffix("") / "__init__.py"
        frozen = pyz.extract(module)
        assert normalized(frozen) == normalized(compile(source.read_bytes(), frozen.co_filename, "exec", dont_inherit=True)), module
        modules.append(module)
    assets = []
    for folder in ("native/haui", "native/graph"):
        for source in (ROOT / "src/mshub" / folder).rglob("*"):
            if not source.is_file() or source.suffix in {".py", ".pyc"}:
                continue
            relative = source.relative_to(ROOT / "src").as_posix()
            assert digest(source) == digest(bundle / "_internal" / relative), relative
            assets.append(relative)
    zipped_path = ROOT / f"release/123mshub-native-v{__version__}-win64.zip"
    expected = {"123mshub/" + name: sha for name, sha in files.items()}
    expected["123mshub/RELEASE-MANIFEST.json"] = digest(manifest_path)
    with zipfile.ZipFile(zipped_path) as zipped:
        members = [m for m in zipped.infolist() if not m.is_dir()]
        assert len(members) == len(expected)
        assert {m.filename.replace('\\', '/') for m in members} == set(expected)
        for member in members:
            with zipped.open(member) as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == expected[member.filename.replace('\\', '/')], member.filename
    result = {"version": __version__, "version_metadata_matches": True, "files": len(expected), "zip_crc_and_all_file_hashes": "pass",
              "manifest_matches_bundle": True, "frozen_source_modules": modules, "assets": assets,
              "exe_sha256": digest(exe), "zip_sha256": digest(zipped_path),
              "zip_bytes": zipped_path.stat().st_size,
              "bundle_bytes": sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())}
    (release / "bundle-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: (len(value) if isinstance(value, list) else value) for key, value in result.items()}, indent=2))


if __name__ == "__main__":
    main()
