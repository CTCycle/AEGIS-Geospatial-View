from __future__ import annotations

from pathlib import Path


###############################################################################
def test_app_shell_does_not_depend_on_external_font_or_icon_css() -> None:
    index_html = (
        Path(__file__).resolve().parents[2] / "client" / "src" / "index.html"
    ).read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in index_html
    assert "fonts.gstatic.com" not in index_html
    assert "Material+Icons" not in index_html
