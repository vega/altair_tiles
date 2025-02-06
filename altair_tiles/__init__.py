__version__ = "0.4.0"
__all__ = ["add_attribution", "add_tiles", "create_tiles_chart", "providers"]

import math
import os
from dataclasses import dataclass
from typing import Final, Optional, Union, cast

import altair as alt
import mercantile as mt
import xyzservices.providers as providers
from xyzservices import TileProvider


def add_tiles(
    chart: alt.Chart,
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    zoom: Optional[int] = None,
    attribution: Union[str, bool] = True,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> alt.LayerChart:
    """Adds tiles to a chart. The chart must have a geoshape mark and a Mercator
    projection.

    Parameters
    ----------
    chart : alt.Chart
        A chart with a Mercator projection.
    provider : Union[str, TileProvider], optional
        The provider of the tiles. You can access all available preconfigured providers
        at `altair_tiles.providers` such as
        `altair_tiles.providers.OpenStreetMap.Mapnik`.
        For convenience, you can also pass the name as a string,
        for example "OpenStreetMap.Mapnik" (this is the default).
        You can pass a custom provider as a :class:`TileProvider` instance.
        This functionality is provided by the `xyzservices` package.
    zoom : Optional[int], optional
        If None an appropriate zoom level will be calculated automatically,
        by default None
    attribution : Union[str, bool], optional
        If True, the default attribution text for the provider, if available, is added
        to the chart. You can also provide a custom text as a string or disable
        the attribution text by setting this to False. By default True
    width : Optional[int], optional
        Manually set the width of the tile chart. This allows for using the tile chart
        in concatenation operations, where it may otherwise fail to detect the correct
        width.
    height : Optional[int], optional
        Manually set the height of the tile chart. This allows for using the tile chart
        in concatenation operations, where it may otherwise fail to detect the correct
        height.

    Returns
    -------
    alt.LayerChart

    Raises
    ------
    TypeError
        If chart is not an altair.Chart instance.
    ValueError
        If chart does not have a geoshape mark or a Mercator projection
        or no projection.
    """
    tiles = create_tiles_chart(
        provider=provider,
        zoom=zoom,
        # Set attribution to False here as we want to add it in the end so it is
        # on top of the geoshape layer.
        attribution=False,
        standalone=False,
        width=width,
        height=height,
    )

    final_chart = tiles + chart
    if attribution:
        final_chart = add_attribution(  # type: ignore[assignment]
            chart=final_chart, provider=provider, attribution=attribution
        )
    return final_chart


def create_tiles_chart(
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    zoom: Optional[int] = None,
    attribution: Union[str, bool] = True,
    standalone: Union[bool, alt.Projection] = True,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Union[alt.LayerChart, alt.Chart]:
    """Creates an Altair chart with tiles.

    Parameters
    ----------
    provider : Union[str, TileProvider], optional
        _description_, by default "OpenStreetMap.Mapnik"
    provider : Union[str, TileProvider], optional
        The provider of the tiles. You can access all available preconfigured providers
        at `altair_tiles.providers` such as
        `altair_tiles.providers.OpenStreetMap.Mapnik`.
        For convenience, you can also pass the name as a string,
        for example "OpenStreetMap.Mapnik" (this is the default).
        You can pass a custom provider as a :class:`TileProvider` instance.
        This functionality is provided by the `xyzservices` package.
    zoom : Optional[int], optional
        If None an appropriate zoom level will be calculated automatically,
        by default None
    attribution : Union[str, bool], optional
        If True, the default attribution text for the provider, if available, is added
        to the chart. You can also provide a custom text as a string or disable
        the attribution text by setting this to False. By default True
    standalone : Union[bool, alt.Projection], optional
        If True, the returned chart will have an additional layer with
        a geoshape mark and a mercator projection set which allows the tiles
        to properly show up and hence you can render the chart as-is.
        If False, the chart will be returned in a form where it can be added
        to an existing chart which must have a projection.
        You could also add a standalone chart to an existing chart
        but the resulting specification is slightly simpler if you choose standalone.
        To customize the projection which is set in the standalone chart, you can
        also pass an alt.Projection instance here which must have at least
        type set to mercator, e.g. `alt.Projection(type="mercator")`. If you already
        have a chart, you can pass the projection of the chart, e.g. `chart.projection`.
        Defaults to True.
    width : Optional[int], optional
        Manually set the width of the tile chart. This allows for using the tile chart
        in concatenation operations, where it may otherwise fail to detect the correct
        width.
    height : Optional[int], optional
        Manually set the height of the tile chart. This allows for using the tile chart
        in concatenation operations, where it may otherwise fail to detect the correct
        height.

    Returns
    -------
    Union[alt.LayerChart, alt.Chart]

    Raises
    ------
    TypeError
        If zoom is not an integer or None.
    """
    provider = _resolve_provider(provider)

    if zoom is not None and not isinstance(zoom, int):
        raise TypeError("Zoom must be an integer or None.")

    # For the tiles to show up, we need to ensure that a Vega Projection is created
    # which is used in the p_base_point parameter. This seems to only happen
    # if we layer the tiles together with another geoshape chart which also
    # has the projection attribute set.
    tiles = _create_nonstandalone_tiles_chart(
        provider=provider,
        zoom=zoom,
        attribution=attribution,
        width=width,
        height=height,
    )

    if standalone:
        if standalone is True:
            standalone = alt.Projection(type="mercator")
        else:
            # In this case it already is an instance of alt.Projection
            _validate_projection(standalone)
        base_layer = alt.Chart().mark_geoshape().properties(projection=standalone)
        # If we use tiles as the first layer then the chart is 20px by 20px by default.
        # Unclear why but the other way around works fine.
        return base_layer + tiles
    else:
        return tiles


def _create_nonstandalone_tiles_chart(
    provider: TileProvider,
    zoom: Optional[int],
    attribution: Union[str, bool],
    width: Optional[int],
    height: Optional[int],
) -> Union[alt.Chart, alt.LayerChart]:
    # The calculations below are based on initial implementations in Vega
    # https://github.com/vega/vega/issues/1212#issuecomment-384680678 and in Vega-Lite
    # https://github.com/vega/vega-lite/issues/5758#issuecomment-1462683219.

    p_pr_scale = alt.param(expr="geoScale('projection')", name="pr_scale")

    evaluated_zoom_level_ceil: Optional[int]
    if zoom is not None:
        p_zoom_level = alt.param(value=zoom, name="zoom_level")
        p_base_tile_size = alt.param(
            expr=f"(2 * PI * {p_pr_scale.name}) / pow(2, {p_zoom_level.name})",
            name="base_tile_size",
        )
        evaluated_zoom_level_ceil = math.ceil(zoom)
    else:
        # Calculate an appropriate zoom level based on the projection scale
        # and the tile size.
        default_base_tile_size = 256
        p_base_tile_size = alt.param(
            value=default_base_tile_size, name="base_tile_size"
        )
        p_zoom_level = alt.param(
            expr=f"log((2 * PI * {p_pr_scale.name}) / {p_base_tile_size.name}) /"
            + " log(2)",
            name="zoom_level",
        )
        # As we don't know the scale of the projection yet, we cannot evaluate
        # the zoom level.
        evaluated_zoom_level_ceil = None

    if evaluated_zoom_level_ceil is not None:
        _validate_zoom(evaluated_zoom_level_ceil, provider=provider)

    p_zoom_ceil = alt.param(expr=f"ceil({p_zoom_level.name})", name="zoom_ceil")
    # Number of tiles per column/row, whichever is larger. Total number of tiles
    # would then be this number squared. However, this number does not account
    # for tiles which will be outside of the view, i.e. what is visible on the chart.
    # It is therefore just the maximum if the whole earth would be visible.
    # If calculation of this is changed here, it should also be changed in the
    # _calculate_one_side_grid_size function which calculates this number
    # in Python.
    p_max_one_side_tiles_count = alt.param(
        expr=f"pow(2, {p_zoom_ceil.name})", name="max_one_side_tiles_count"
    )
    p_tile_size = alt.param(
        expr=p_base_tile_size.name
        + f" * pow(2, {p_zoom_level.name} - {p_zoom_ceil.name})",
        name="tile_size",
    )
    p_base_point = alt.param(expr="invert('projection', [0, 0])", name="base_point")
    p_dii = alt.param(
        expr=f"({p_base_point.name}[0] + 180) / 360"
        + f" * {p_max_one_side_tiles_count.name}",
        name="dii",
    )
    p_dii_floor = alt.param(expr=f"floor({p_dii.name})", name="dii_floor")
    p_dx = alt.param(
        expr=f"({p_dii_floor.name} - {p_dii.name}) * {p_tile_size.name}", name="dx"
    )
    p_djj = alt.param(
        expr=f"(1 - log(tan({p_base_point.name}[1] * PI / 180)"
        + f" + 1 / cos({p_base_point.name}[1] * PI / 180)) / PI)"
        + f" / 2 * {p_max_one_side_tiles_count.name}",
        name="djj",
    )
    p_djj_floor = alt.param(expr=f"floor({p_djj.name})", name="djj_floor")
    p_dy = alt.param(
        expr=f"round(({p_djj_floor.name} - {p_djj.name}) * {p_tile_size.name})",
        name="dy",
    )
    expr_url_x = (
        f"((datum.a + {p_dii_floor.name} + {p_max_one_side_tiles_count.name})"
        + f" % {p_max_one_side_tiles_count.name})"
    )
    expr_url_y = f"(datum.b + {p_djj_floor.name})"

    def build_url(provider: TileProvider, x: str, y: str, z: str) -> str:
        def format_value(v: str) -> str:
            return f"' + {v} + '"

        return (
            "'"
            + provider.build_url(
                x=format_value(x), y=format_value(y), z=format_value(z)
            )
            + "'"
        )

    one_side_grid_size = _calculate_one_side_grid_size(evaluated_zoom_level_ceil)

    tile_list = alt.sequence(
        0, one_side_grid_size, as_="a", name=f"tile_list_{os.urandom(6).hex()}"
    )

    # Can be a layerchart after adding attribution
    tiles = (
        alt.Chart(tile_list)
        .mark_image(
            clip=True,
            # For some settings, the tiles would show a fine gap between them. By adding
            # 1px to the height and width, we can avoid this.
            height=alt.expr(p_tile_size.name + " + 1"),
            width=alt.expr(p_tile_size.name + " + 1"),
        )
        .encode(alt.Url("url:N"), alt.X("x:Q").scale(None), alt.Y("y:Q").scale(None))
        .transform_calculate(b=f"sequence(0, {one_side_grid_size})")
        .transform_flatten(["b"])
        .transform_calculate(
            url=build_url(provider, x=expr_url_x, y=expr_url_y, z=p_zoom_ceil.name),
            x=f"datum.a * {p_tile_size.name} + {p_dx.name} + ({p_tile_size.name} / 2)",
            y=f"datum.b * {p_tile_size.name} + {p_dy.name} + ({p_tile_size.name} / 2)",
        )
    )

    # Remove tiles which would be outside of the chart. Some
    # of these tiles might even be duplicated without this step as they
    # would be placed again once we are 'around the world' but with x and y
    # values which are far outside of the chart. This also greatly speeds up the
    # rendering time of a chart and the time it takes to save it with
    # e.g. vl-convert-python as even if the tiles would not be visible in the chart,
    # they would still be downloaded.
    # x and y below refer to the x and y coordinates on the chart, not the x and y
    # in the tile urls.

    # Note that height and width may be (incorrectly) set to zero when used in a
    # concatenated chart. In those cases, the childHeight and childWidth signals are
    # instead set, but we cannot use these because they don't always exists and
    # referencing an undefined signal throws an error.
    #
    # Instead, just use the manually provided dimensions to allow the caller to override
    # the erroneous height or width signals.
    tiles = tiles.transform_filter(
        f"datum.x < ({width or 'width'} + tile_size / 2) && "
        + f"datum.y < ({height or 'height'} + tile_size / 2)"
    )

    # Remove tile urls which are not valid for the given provider. Else, they would
    # lead to errors when Vega tries to load and render them.
    provider_bounds = getattr(provider, "bounds", None)
    if provider_bounds is None:
        # Provider does not provide bounds, so we assume that they cover the whole
        # earth surface. We therefore only apply some simple heuristics to remove
        # invalid URLs

        # Min values: Only positive x and y values in URL as
        # tiles never have negative values
        # Max values: Only load as many tiles as we expect given p_one_side_tiles_count.
        # This again helps with speed but also avoids invalid tile urls
        # with x and y values which would be too large.
        # We need to subtract 1 from the tiles count as the tile indices start at 0
        tiles = _transform_filter_url_x_y_bounds(
            chart=tiles,
            x_min=0,
            y_min=0,
            x_max=f"({p_max_one_side_tiles_count.name} - 1)",
            y_max=f"({p_max_one_side_tiles_count.name} - 1)",
            expr_url_x=expr_url_x,
            expr_url_y=expr_url_y,
        )
    else:
        # Provider does provide bounds for which they provide tiles. This can happen
        # e.g. for providers which focus on a specific region or country.
        if evaluated_zoom_level_ceil is None:
            raise ValueError(
                "The provider only provides tiles for bounds. This currently only"
                + " works if you provide a fixed zoom level."
            )
        x_y_min_max = _bounds_to_x_y_min_max(
            bounds=provider_bounds, zoom=evaluated_zoom_level_ceil
        )
        tiles = _transform_filter_url_x_y_bounds(
            chart=tiles,
            x_min=x_y_min_max.x_min,
            y_min=x_y_min_max.y_min,
            x_max=x_y_min_max.x_max,
            y_max=x_y_min_max.y_max,
            expr_url_x=expr_url_x,
            expr_url_y=expr_url_y,
        )

    tiles = tiles.add_params(
        p_base_tile_size,
        p_pr_scale,
        p_zoom_level,
        p_zoom_ceil,
        p_max_one_side_tiles_count,
        p_tile_size,
        p_base_point,
        p_dii,
        p_dii_floor,
        p_dx,
        p_djj,
        p_djj_floor,
        p_dy,
    )

    tiles_final: Union[alt.Chart, alt.LayerChart]
    if attribution:
        tiles_final = add_attribution(tiles, provider, attribution)
    else:
        tiles_final = tiles
    return tiles_final


@dataclass
class _XYMinMax:
    x_min: int
    y_min: int
    x_max: int
    y_max: int


def _bounds_to_x_y_min_max(bounds: list[list[float]], zoom: int) -> _XYMinMax:
    south_west, north_east = bounds
    south, west = south_west
    north, east = north_east
    valid_tiles = list(
        mt.tiles(west=west, south=south, east=east, north=north, zooms=[zoom])
    )
    x_min = min(tile.x for tile in valid_tiles)
    x_max = max(tile.x for tile in valid_tiles)
    y_min = min(tile.y for tile in valid_tiles)
    y_max = max(tile.y for tile in valid_tiles)
    return _XYMinMax(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def _transform_filter_url_x_y_bounds(
    chart: alt.Chart,
    x_min: Union[str, int],
    x_max: Union[str, int],
    y_min: Union[str, int],
    y_max: Union[str, int],
    expr_url_x: str,
    expr_url_y: str,
) -> alt.Chart:
    chart = chart.transform_filter(
        # Lower bounds
        expr_url_x
        + f" >= {x_min} && "
        + expr_url_y
        + f" >= {y_min}"
        + " && "
        + expr_url_x
        + " <= "
        + str(x_max)
        + " && "
        + expr_url_y
        + " <= "
        + str(y_max)
    )
    return chart


def _validate_zoom(zoom: int, provider: TileProvider) -> None:
    # Follows very closely the implementation in contextily.tile._validate_zoom
    # https://github.com/geopandas/contextily/blob/0c8c9ce6d99f29e5fd250ee505f52a9bad30642b/contextily/tile.py#LL538C3-L538C3  # noqa: E501
    min_zoom = provider.get("min_zoom", 0)
    if "max_zoom" in provider:
        max_zoom = provider.get("max_zoom")
        max_zoom_known = True
    else:
        # 22 is known max in existing providers, taking some margin
        max_zoom = 30
        max_zoom_known = False

    if not (min_zoom <= zoom <= max_zoom):
        msg = f"The zoom level of {zoom} is not valid for the current tile provider"
        if max_zoom_known:
            msg += f" (valid zooms: {min_zoom} - {max_zoom})."
        else:
            msg += "."
        raise ValueError(msg)


def _calculate_one_side_grid_size(evaluated_zoom_level_ceil: Optional[int]) -> int:
    # Size of tile grid needs to be calculated in Python as it is not possible
    # yet to use an expression in a data generator such as a sequence.
    # See https://github.com/vega/vega-lite/issues/7410
    # The issue with this is that it depends on the size of the chart which
    # we cannot yet know at this point as it might be changed by e.g. a theme
    # or by the user themselves when working with the returned chart.
    # Therefore, we try to make the grid as large as possible but also limit
    # it to a reasonable size as at one point Vega will no longer be able to
    # generate the sequence if its too large or it just will be very slow.

    # Maximum value is arbitrary.
    maximum_value: Final[int] = 20
    one_side_grid_size: int
    if evaluated_zoom_level_ceil is not None:
        # This is the same formula as used in the Vega-Lite spec for the
        # max_one_side_tiles_count parameter.
        evaluated_max_one_side_tiles_count = 2**evaluated_zoom_level_ceil
        # Adding 2 to the evaluated tiles is arbitrary to make sure
        # that we have enough tiles. This might not be necessary.
        one_side_grid_size = min(evaluated_max_one_side_tiles_count + 2, maximum_value)
    else:
        one_side_grid_size = maximum_value

    return one_side_grid_size


def add_attribution(
    chart: Union[alt.Chart, alt.LayerChart],
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    attribution: Union[bool, str] = True,
) -> Union[alt.Chart, alt.LayerChart]:
    """This function is useful if the attribution added by add_tiles or
    create_tiles_chart would be partially hidden by another layer. In that case,
    you can set `attribution=False` when creating the tiles chart
    and then use this function to add the attribution in the end to the final chart.
    See the documentation for examples

    Parameters
    ----------
    chart : Union[alt.Chart, alt.LayerChart]
        A chart to which you want to have the attribution added.
    provider : Union[str, TileProvider], optional
        The provider of the tiles. You can access all available preconfigured providers
        at `altair_tiles.providers` such as
        `altair_tiles.providers.OpenStreetMap.Mapnik`.
        For convenience, you can also pass the name as a string, for example
        "OpenStreetMap.Mapnik" (this is the default).
        You can pass a custom provider as a :class:`TileProvider` instance.
        This functionality is provided by the `xyzservices` package.
    attribution : Union[str, bool], optional
        If True, the default attribution text for the provider, if available, is added
        to the chart. You can also provide a custom text as a string or disable
        the attribution text by setting this to False. By default True

    Returns
    -------
    Union[alt.Chart, alt.LayerChart]
    """
    provider = _resolve_provider(provider)

    attribution_text: Optional[str]
    if attribution:
        attribution_text = (
            attribution if isinstance(attribution, str) else provider.get("attribution")
        )
    else:
        attribution_text = None

    if attribution_text:
        text_attrib = (
            alt.Chart()
            .mark_text(text=attribution_text, dy=-8, dx=3, align="left")
            .encode(x=alt.value(0), y=alt.value(alt.expr("height")))
        )
        chart = chart + text_attrib

    return chart


def _resolve_provider(provider: Union[str, TileProvider]) -> TileProvider:
    if isinstance(provider, str):
        provider = cast(TileProvider, providers.query_name(provider))
    return provider


def _validate_projection(projection: alt.Projection) -> None:
    if not isinstance(projection, alt.Projection):
        raise TypeError("Projection must be an alt.Projection instance.")
    if projection.type != "mercator":
        raise ValueError("Projection must be of type 'mercator'.")
