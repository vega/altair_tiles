__version__ = "0.1.0dev"
__all__ = ["add_tiles", "add_attribution", "create_tiles_chart", "providers"]

import math
from typing import Optional, Union, cast

import altair as alt
import mercantile as mt
import xyzservices.providers as providers
from xyzservices import TileProvider


def add_tiles(
    chart: alt.Chart,
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    zoom: Optional[int] = None,
    attribution: Union[str, bool] = True,
) -> alt.LayerChart:
    """Adds tiles to a chart. The chart must have a geoshape mark and a Mercator
    projection.

    Parameters
    ----------
    chart : alt.Chart
        A chart with a geoshape mark and a Mercator projection.
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
    if not isinstance(chart, alt.Chart):
        raise TypeError(
            "Only altair.Chart instances are supported. If you want to add"
            + " tiles to a layer chart, use create_tiles_chart to create the tiles"
            + " and then add them as a normal layer to the existing layer chart."
        )

    if chart.projection is alt.Undefined:
        raise ValueError("Projection must be defined and be of type Mercator.")

    if (
        chart.mark is alt.Undefined
        or (isinstance(chart.mark, str) and chart.mark != "geoshape")
        or (isinstance(chart.mark, alt.MarkDef) and chart.mark.type != "geoshape")
    ):
        raise ValueError("Chart must have a geoshape mark.")

    tiles = create_tiles_chart(
        projection=chart.projection,
        provider=provider,
        zoom=zoom,
        # Set attribution to False here as we want to add it in the end so it is
        # on top of the geoshape layer.
        attribution=False,
        standalone=False,
    )

    final_chart = tiles + chart
    if attribution:
        final_chart = add_attribution(
            chart=final_chart, provider=provider, attribution=attribution
        )
    return final_chart


def create_tiles_chart(
    projection: alt.Projection,
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    zoom: Optional[int] = None,
    attribution: Union[str, bool] = True,
    standalone: bool = True,
) -> Union[alt.LayerChart, alt.Chart]:
    """Creates an Altair chart with tiles.

    Parameters
    ----------
    projection : alt.Projection
        The projection of the chart. It must at least specify the type of the projection
        which must be scale, e.g. `alt.Projection(type="mercator")`. If you already
        have a chart, you can pass the projection of the chart, e.g. `chart.projection`.
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
    standalone : bool, optional
        If True, the chart will be returned as a chart which can be rendered standalone.
        It has an additional layer with a geoshape mark and the projection set. This is
        required for the tiles to properly show up. If False, the chart will be returned
        in a form where it can be added to an existing chart with a geoshape
        mark. You culd also add a standalone chart to an existing chart
        but the resulting specification is slightly simpler if you choose standalone.
        Defaults to True.


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
        projection=projection,
        provider=provider,
        zoom=zoom,
        attribution=attribution,
    )

    if standalone:
        base_layer = alt.Chart().mark_geoshape().properties(projection=projection)
        # If we use tiles as the first layer then the chart is 20px by 20px by default.
        # Unclear why but the other way around works fine.
        return base_layer + tiles
    else:
        return tiles


def _create_nonstandalone_tiles_chart(
    projection: alt.Projection,
    provider: TileProvider,
    zoom: Optional[int],
    attribution: Union[str, bool],
) -> Union[alt.Chart, alt.LayerChart]:
    # The calculations below are based on initial implementations in Vega
    # https://github.com/vega/vega/issues/1212#issuecomment-384680678 and in Vega-Lite
    # https://github.com/vega/vega-lite/issues/5758#issuecomment-1462683219.
    _validate_projection(projection)

    if projection.scale is not alt.Undefined:
        scale = projection.scale
        if isinstance(scale, alt.Parameter):
            scale = scale.name
    else:
        # Found here:
        # https://github.com/d3/d3-geo/blob/main/src/projection/mercator.js#L13
        # This value is projection specific and would need to be changed.
        # Check below guards for the case were we support more projections in
        # the future.
        if projection.type != "mercator":
            raise ValueError("Scale must be defined for non-Mercator projections.")
        scale = 961 / math.tau
    # We use expr and not value below in case it is a Vega expression. expr always
    # expects a string and therefore we use str to convert potential numeric values
    p_pr_scale = alt.param(expr=str(scale), name="pr_scale")

    evaluated_zoom_level_ceil: Optional[int] = None
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
        if isinstance(scale, (float, int)):
            # In this case, we can also evaluate the zoom level.
            # Else, it could be a Vega expression in which case we can't evaluate
            # it in Python.
            evaluated_zoom_level_ceil = math.ceil(
                math.log((2 * math.pi * scale) / default_base_tile_size) / math.log(2)
            )

    evaluated_tiles_count: Optional[int] = None
    if evaluated_zoom_level_ceil is not None:
        _validate_zoom(evaluated_zoom_level_ceil, provider=provider)
        evaluated_tiles_count = 2**evaluated_zoom_level_ceil

    p_zoom_ceil = alt.param(expr=f"ceil({p_zoom_level.name})", name="zoom_ceil")
    # Number of tiles per column/row, whichever is larger. Total number of tiles
    # would then be this number squared although it does not account for tiles
    # which will be clipped if chart has non-quadratic aspect ratio.
    p_one_side_tiles_count = alt.param(
        expr=f"pow(2, {p_zoom_ceil.name})", name="tiles_count"
    )
    p_tile_size = alt.param(
        expr=p_base_tile_size.name
        + f" * pow(2, {p_zoom_level.name} - {p_zoom_ceil.name})",
        name="tile_size",
    )
    p_base_point = alt.param(expr="invert('projection', [0, 0])", name="base_point")
    p_dii = alt.param(
        expr=f"({p_base_point.name}[0] + 180) / 360 * {p_one_side_tiles_count.name}",
        name="dii",
    )
    p_dii_floor = alt.param(expr=f"floor({p_dii.name})", name="dii_floor")
    p_dx = alt.param(
        expr=f"({p_dii_floor.name} - {p_dii.name}) * {p_tile_size.name}", name="dx"
    )
    p_djj = alt.param(
        expr=f"(1 - log(tan({p_base_point.name}[1] * PI / 180)"
        + f" + 1 / cos({p_base_point.name}[1] * PI / 180)) / PI)"
        + f" / 2 * {p_one_side_tiles_count.name}",
        name="djj",
    )
    p_djj_floor = alt.param(expr=f"floor({p_djj.name})", name="djj_floor")
    p_dy = alt.param(
        expr=f"round(({p_djj_floor.name} - {p_djj.name}) * {p_tile_size.name})",
        name="dy",
    )
    expr_url_x = (
        f"((datum.a + {p_dii_floor.name} + {p_one_side_tiles_count.name})"
        + f" % {p_one_side_tiles_count.name})"
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

    # Size of tile grid needs to be calculated in Python as it is not possible
    # yet to use an expression in a data generator such as a sequence.
    # See https://github.com/vega/vega-lite/issues/7410
    # The issue with this is that it depends on the size of the chart which
    # we cannot yet know at this point as it might be changed by e.g. a theme
    # or by the user themselves when working with the returned layered chart.

    # Fallback value of 10 is arbitrary. Ideally, there would be a better heuristic
    # but it's also only used if the scale is a Vega expression which should
    # be rare. Adding 2 to the evaluated tiles is also arbitrary to make sure
    # that we have enough tiles. This might not be necessary. We then remove
    # the unnecessary tiles again in the transform_filter statement below which is
    # needed anyway to remove the ones with negative indices.
    grid_size = evaluated_tiles_count + 2 if evaluated_tiles_count is not None else 10

    tile_list = alt.sequence(0, grid_size, as_="a", name="tile_list")
    # Can be a layerchart after adding attribution
    tiles: Union[alt.Chart, alt.LayerChart] = (
        alt.Chart(tile_list, projection=projection)
        .mark_image(
            clip=True,
            # For some settings, the tiles would show a fine gap between them. By adding
            # 1px to the height and width, we can avoid this.
            height=alt.expr(p_tile_size.name + " + 1"),
            width=alt.expr(p_tile_size.name + " + 1"),
        )
        .encode(alt.Url("url:N"), alt.X("x:Q").scale(None), alt.Y("y:Q").scale(None))
        .transform_calculate(b=f"sequence(0, {grid_size})")
        .transform_flatten(["b"])
        .transform_calculate(
            url=build_url(provider, x=expr_url_x, y=expr_url_y, z=p_zoom_ceil.name),
            x=f"datum.a * {p_tile_size.name} + {p_dx.name} + ({p_tile_size.name} / 2)",
            y=f"datum.b * {p_tile_size.name} + {p_dy.name} + ({p_tile_size.name} / 2)",
        )
        .transform_filter(
            # Remove tiles which are not valid. Else, they would lead to errors
            # when Vega tries to load and render them.
            # This also removes tiles which are not needed for the current
            # size of the chart. Vega does not seem to load images anyway
            # which are not visible but this might still be useful to avoid
            # unnecessary requests.
            expr_url_x
            + " >= 0 && "
            + expr_url_y
            + " >= 0"
            + " && "
            + expr_url_x
            + " <= "
            # We need to subtract 1 from the tiles count as the tile indices start at 0
            + f"({p_one_side_tiles_count.name} - 1)"
            + " && "
            + expr_url_y
            + " <= "
            + f"({p_one_side_tiles_count.name} - 1)"
        )
        .transform_filter(
            # Remove some more tiles which would be outside of the chart. Some
            # of these tiles might even be duplicated without this step as they
            # woudl be placed again once we are 'around the world' but with x and y
            # values which are far outside of the chart.
            "datum.x < (width + tile_size / 2) && datum.y < (height + tile_size / 2)"
        )
    )

    tiles = tiles.add_params(
        p_base_tile_size,
        p_pr_scale,
        p_zoom_level,
        p_zoom_ceil,
        p_one_side_tiles_count,
        p_tile_size,
        p_base_point,
        p_dii,
        p_dii_floor,
        p_dx,
        p_djj,
        p_djj_floor,
        p_dy,
    )

    if attribution:
        tiles = add_attribution(tiles, provider, attribution)
    return tiles


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
    if projection.type != "mercator":
        raise ValueError("Projection must be of type 'mercator'.")
