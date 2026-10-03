"""Make the Qt SVG captures friendlier to Illustrator without changing geometry."""
from __future__ import annotations

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mshub.native.navigation_symbols import STITCH_NAV_SVGS
from mshub.native.ui_icons import ICONS

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
NS = "{" + SVG + "}"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)

ICON_ORDER = [
    ("note_new", "header-new", "#FFFFFF"),
    ("edit", "header-edit", None),
    ("agent", "header-agent", "#FFFFFF"),
    ("search", "memory-search", None),
    ("inbox", "inbox", None),
    ("auto", "tidy", None),
    ("auto", "daily-report", None),
    ("copy", "duty-prompt", None),
    ("list", "index-source", None),
]
NAV_ORDER = [("memory", "nav-memory"), ("graph", "nav-graph"), ("skills", "nav-skills"),
             ("security", "nav-security"), ("settings", "nav-settings")]


def find_parent(root: ET.Element, target: ET.Element):
    for parent in root.iter():
        for index, child in enumerate(list(parent)):
            if child is target:
                return parent, index
    raise ValueError("SVG parent not found")


def vector_group(source: str, image: ET.Element, identifier: str, color: str | None = None,
                 *, viewbox_mode: str = "ui") -> ET.Element:
    if color:
        source = source.replace("COLOR", color)
    source_root = ET.fromstring(source)
    viewbox = source_root.attrib.get("viewBox", "0 0 24 24").split()
    min_x, min_y, vb_width, vb_height = map(float, viewbox)
    x = float(image.attrib.get("x", "0"))
    y = float(image.attrib.get("y", "0"))
    width = float(image.attrib.get("width", "24"))
    height = float(image.attrib.get("height", "24"))
    if viewbox_mode == "nav":
        transform = f"translate({x:g},{y + height:g}) scale({width / vb_width:g},{-height / vb_height:g})"
    else:
        transform = f"translate({x:g},{y:g}) scale({width / vb_width:g},{height / vb_height:g})"
    node = ET.Element(NS + "g", {"id": identifier, "data-role": identifier, "transform": transform})
    for child in list(source_root):
        node.append(child)
    return node


def parent_with_image(root: ET.Element, image: ET.Element):
    return find_parent(root, image)


def prepare(path: Path, mode: str) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    images = list(root.iter(NS + "image"))
    if len(images) != 18:
        raise RuntimeError(f"expected 18 Qt image surfaces, got {len(images)}")

    palette = {
        "bg": "#18181B" if mode == "dark" else "#E5E5E7",
        "ink": "#DAE2FD" if mode == "dark" else "#2E3040",
        "muted": "#94A3B8" if mode == "dark" else "#585A68",
        "faint": "#64748B" if mode == "dark" else "#8A8C9A",
    }
    canvas = images[0]
    parent, index = parent_with_image(root, canvas)
    background = ET.Element(NS + "rect", {
        "id": "canvas-background",
        "data-role": "canvas-background",
        "x": "0", "y": "0", "width": root.attrib.get("viewBox", "0 0 1440 900").split()[-2],
        "height": root.attrib.get("viewBox", "0 0 1440 900").split()[-1], "fill": palette["bg"],
    })
    parent.remove(canvas)
    parent.insert(index, background)
    parent.set("id", "layer-canvas")

    # Header/action icons and the search/task affordances are all generated
    # from the app's source SVG strings. This removes Qt's small PNG wrapper.
    for image, (name, identifier, fixed_color) in zip(images[1:10], ICON_ORDER):
        color = fixed_color or palette["muted"]
        p, i = parent_with_image(root, image)
        p.remove(image)
        p.insert(i, vector_group(ICONS[name], image, identifier, color))
        p.set("data-role", identifier.rsplit("-", 1)[0])

    # Brand logo is already an Illustrator-authored SVG in the repository.
    image = images[10]
    source = (ROOT / "packaging/native/icons/NEWmshublogo.svg").read_text(encoding="utf-8")
    p, i = parent_with_image(root, image)
    p.remove(image)
    p.insert(i, vector_group(source, image, "brand-logo"))
    p.set("id", "layer-brand")

    image = images[11]
    p, i = parent_with_image(root, image)
    p.remove(image)
    p.insert(i, vector_group(ICONS["chevron_up"], image, "task-chevron", palette["muted"]))
    p.set("id", "layer-task-controls")

    image = images[12]
    p, i = parent_with_image(root, image)
    p.remove(image)
    p.insert(i, vector_group(ICONS["clear"], image, "task-clear", palette["muted"]))
    p.set("data-role", "task-actions")

    # Navigation symbols are source SVG paths from navigation_symbols.py.
    for image, (name, identifier) in zip(images[13:18], NAV_ORDER):
        p, i = parent_with_image(root, image)
        p.remove(image)
        p.insert(i, vector_group(STITCH_NAV_SVGS[name].replace("COLOR", palette["ink"]), image, identifier, viewbox_mode="nav"))
        p.set("id", "layer-navigation")

    metadata = ET.Element(NS + "metadata", {"id": "export-metadata"})
    metadata.text = (
        f"123 MSHub v1.10.5 · 记忆仓库 · {mode} · 1440×900 · "
        "generated from the native Qt UI; fixture rows/tasks are review-only. "
        "Text, cards, borders, selection fills and source SVG icons remain editable."
    )
    root.insert(0, metadata)
    root.set("data-page", "memory-repository")
    root.set("data-theme", mode)
    root.set("data-source", "123mshub-native-v1.10.5")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    for mode in ("light", "dark"):
        raw = HERE / f"probe-{mode}.svg"
        out = HERE / f"123mshub-v1.10.5-记忆仓库-{('亮色' if mode == 'light' else '暗色')}.svg"
        raw.replace(out)
        prepare(out, mode)
        print(out)


if __name__ == "__main__":
    main()
