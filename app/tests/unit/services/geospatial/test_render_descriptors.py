from __future__ import annotations

from server.services.geospatial.render_descriptors import RenderDescriptorService


###############################################################################
def test_render_descriptor_service_builds_complete_wms_template() -> None:
    template = RenderDescriptorService.build_wms_tile_template(
        url="https://example.test/wms",
        layer_id="layer",
        crs="EPSG:3857",
        image_format="image/png",
        style="default",
        time="2026-06-18",
        version="1.1.1",
        exceptions="application/vnd.ogc.se_inimage",
    )

    assert "service=WMS" in template
    assert "request=GetMap" in template
    assert "layers=layer" in template
    assert "srs=EPSG:3857" in template
    assert "bbox={bbox-epsg-3857}" in template
    assert "width=256" in template
    assert "height=256" in template
    assert "transparent=true" in template
    assert "time=2026-06-18" in template


###############################################################################
def test_render_descriptor_service_builds_complete_wmts_template() -> None:
    template = RenderDescriptorService.build_wmts_tile_template(
        url="https://example.test/wmts",
        layer_id="layer",
        style="default",
        image_format="image/png",
        tile_matrix_set="GoogleMapsCompatible_Level9",
        time="2026-06-18",
    )

    assert "service=WMTS" in template
    assert "request=GetTile" in template
    assert "layer=layer" in template
    assert "style=default" in template
    assert "tilematrixset=GoogleMapsCompatible_Level9" in template
    assert "tilematrix=GoogleMapsCompatible_Level9:{z}" in template
    assert "tilerow={y}" in template
    assert "tilecol={x}" in template
    assert "format=image/png" in template
    assert "time=2026-06-18" in template
