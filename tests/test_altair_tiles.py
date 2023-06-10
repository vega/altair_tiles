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
