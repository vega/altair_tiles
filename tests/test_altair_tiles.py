# ruff: noqa: SLF001
import altair as alt
import pytest

import altair_tiles as til


def test_raise_if_invalid_zoom_level():
    # Test minimum zoom
    with pytest.raises(ValueError, match="is not valid for the current tile provider"):
        til.create_tiles_chart(projection=alt.Projection(type="mercator"), zoom=-1)
    til.create_tiles_chart(
        projection=alt.Projection(type="mercator"),
        zoom=0,
    )

    # Test maximum zoom
    provider = til.providers.OpenStreetMap.Mapnik
    max_zoom = provider.max_zoom

    assert isinstance(max_zoom, int)
    with pytest.raises(ValueError, match="is not valid for the current tile provider"):
        til.create_tiles_chart(
            projection=alt.Projection(type="mercator"),
            zoom=max_zoom + 1,
            provider=provider,
        )

    til.create_tiles_chart(
        projection=alt.Projection(type="mercator"),
        zoom=max_zoom,
        provider=provider,
    )

    # Test if no zoom is provided but scale instead
    with pytest.raises(ValueError, match="is not valid for the current tile provider"):
        til.create_tiles_chart(
            projection=alt.Projection(type="mercator", scale=200_000_000),
            provider=provider,
        )


def test_validate_projection():
    # Test valid projection
    projection = alt.Projection(type="mercator")
    til._validate_projection(projection)

    # Test invalid projection
    projection = alt.Projection(type="albersUsa")
    with pytest.raises(ValueError, match="Projection must be of type 'mercator'."):
        til._validate_projection(projection)


def test_resolve_provider():
    # Test with string provider
    provider_name = "OpenStreetMap.Mapnik"
    assert til._resolve_provider(provider_name) is til.providers.OpenStreetMap.Mapnik

    # Test with TileProvider object
    provider_obj = til.providers.OpenStreetMap.Mapnik
    assert til._resolve_provider(provider_obj) is provider_obj


@pytest.mark.parametrize(
    (
        "provider",
        "attribution",
    ),
    [
        ("OpenStreetMap.Mapnik", True),
        (
            "OpenStreetMap.Mapnik",
            "Custom attribution",
        ),
        ("OpenStreetMap.DE", True),
        (til.providers.OpenStreetMap.Mapnik, True),
    ],
)
def test_add_attribution_with_attribution(provider, attribution):
    chart = alt.Chart()
    expected_attribution = (
        attribution
        if isinstance(attribution, str)
        else til._resolve_provider(provider).get("attribution")
    )

    chart_with_att = til.add_attribution(
        chart, provider=provider, attribution=attribution
    )

    assert isinstance(chart_with_att, alt.LayerChart)
    assert len(chart_with_att.layer) == 2
    att_layer = chart_with_att.layer[1]
    att_layer_spec = att_layer.to_dict()
    assert att_layer_spec["mark"]["type"] == "text"
    assert att_layer_spec["mark"]["text"] == expected_attribution


@pytest.mark.parametrize(
    "provider",
    [
        "OpenStreetMap.Mapnik",
        "OpenStreetMap.DE",
        til.providers.OpenStreetMap.Mapnik,
    ],
)
def test_add_attribution_without_attribution(provider):
    chart = alt.Chart()

    chart_with_att = til.add_attribution(chart, provider=provider, attribution=False)

    assert isinstance(chart_with_att, alt.Chart)
    assert chart_with_att is chart


def _validate_image_layer(image_layer: alt.Chart):
    image_layer_spec = image_layer.to_dict()
    assert image_layer_spec["mark"]["type"] == "image"
    assert image_layer_spec["encoding"]["x"]["type"] == "quantitative"
    assert image_layer_spec["encoding"]["y"]["type"] == "quantitative"
    assert image_layer_spec["encoding"]["url"]["type"] == "nominal"
    assert image_layer_spec["encoding"]["x"]["scale"] is None
    assert image_layer_spec["encoding"]["y"]["scale"] is None


class TestCreateTilesChart:
    def test_raise_if_invalid_zoom_type(self):
        with pytest.raises(TypeError, match="Zoom must be an integer or None"):
            til.create_tiles_chart(projection=alt.Projection(type="mercator"), zoom="1")

    def test_create_tiles_chart(self):
        chart = til.create_tiles_chart(projection=alt.Projection(type="mercator"))

        assert isinstance(chart, alt.LayerChart)
        assert len(chart.layer) == 2
        geoshape_layer = chart.layer[0]
        assert geoshape_layer.to_dict()["mark"]["type"] == "geoshape"

        image_layered_chart = chart.layer[1]
        assert isinstance(image_layered_chart, alt.LayerChart)

        image_layer = image_layered_chart.layer[0]
        _validate_image_layer(image_layer)

        attr_layer = image_layered_chart.layer[1]
        assert attr_layer.to_dict()["mark"]["type"] == "text"

    def test_non_standalone(self):
        chart = til.create_tiles_chart(
            projection=alt.Projection(type="mercator"), standalone=False
        )

        assert isinstance(chart, alt.LayerChart)
        assert len(chart.layer) == 2
        assert all(isinstance(layer, alt.Chart) for layer in chart.layer)

        image_chart = chart.layer[0]
        assert image_chart.to_dict()["mark"]["type"] == "image"

        attr_chart = chart.layer[1]
        assert attr_chart.to_dict()["mark"]["type"] == "text"

    def test_no_attribution(self):
        chart = til.create_tiles_chart(
            projection=alt.Projection(type="mercator"),
            attribution=False,
            standalone=False,
        )

        assert isinstance(chart, alt.Chart)
        assert chart.to_dict()["mark"]["type"] == "image"


class TestAddTiles:
    def test_raise_if_not_chart(self):
        with pytest.raises(
            TypeError, match="Only altair.Chart instances are supported"
        ):
            til.add_tiles(alt.LayerChart)

    def test_raise_if_no_projection_defined(self):
        with pytest.raises(ValueError, match="Projection must be defined"):
            til.add_tiles(alt.Chart().mark_geoshape())

    def test_raise_if_no_mark_geoshape(self):
        with pytest.raises(ValueError, match="Chart must have a geoshape mark"):
            til.add_tiles(alt.Chart().project(type="mercator"))

        with pytest.raises(ValueError, match="Chart must have a geoshape mark"):
            til.add_tiles(alt.Chart().mark_bar().project(type="mercator"))

    def test_add_tiles(self):
        chart = til.add_tiles(alt.Chart().mark_geoshape().project(type="mercator"))

        assert isinstance(chart, alt.LayerChart)
        assert len(chart.layer) == 3
        image_layer = chart.layer[0]
        _validate_image_layer(image_layer)

        geoshape_layer = chart.layer[1]
        assert geoshape_layer.to_dict()["mark"]["type"] == "geoshape"

        attr_layer = chart.layer[2]
        assert attr_layer.to_dict()["mark"]["type"] == "text"

    def test_no_attribution(self):
        chart = til.add_tiles(
            alt.Chart().mark_geoshape().project(type="mercator"), attribution=False
        )

        assert isinstance(chart, alt.LayerChart)
        assert len(chart.layer) == 2
