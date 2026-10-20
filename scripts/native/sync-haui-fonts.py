"""Convert the licensed local WOFF2 fonts for Qt and sync graph presentation assets.

Build-time only: pip install 'fonttools[woff]'. No fonttools runtime dependency.
"""
import hashlib
import json
from pathlib import Path
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "src/mshub/native/haui"
manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
for source in (ASSETS / "fonts").glob("*.woff2"):
    font = TTFont(source)
    font.recalcTimestamp = False
    font.flavor = None
    target = source.with_suffix(".ttf")
    font.save(target)
    manifest["outputs"][target.relative_to(ASSETS).as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
(ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
graph = ROOT / "src/mshub/native/graph"
for filename in ("haui.js", "haui.css"):
    (graph / filename).write_bytes((ROOT / "web/native-graph" / filename).read_bytes())
themes = json.loads((ASSETS / "themes.json").read_text(encoding="utf-8"))["themes"]["nous"]["variants"]["default"]
data = {mode: themes[mode]["qt"] for mode in ("light", "dark")}
data["icons"] = json.loads((ASSETS / "icons.json").read_text(encoding="utf-8"))
(graph / "haui-tokens.js").write_text("window.mshubHaui = " + json.dumps(data) + ";\n", encoding="utf-8")
print("Converted licensed fonts and synced HAUI graph presentation (Sigma runtime unchanged).")
