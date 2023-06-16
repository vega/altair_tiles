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
    til._resolve_provider(provider_name) == til.providers.OpenStreetMap.Mapnik

    # Test with TileProvider object
    provider_obj = TileProvider()
    assert _resolve_provider(provider_obj) == provider_obj
