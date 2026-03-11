__version__ = "0.5.0dev"
__all__ = [
    "add_attribution",
    "add_tiles",
    "create_tiles_chart",
    "providers",
    "hconcat",
    "vconcat",
    "concat",
]

import copy
import hashlib
import json
import math
import re
from typing import Final, NamedTuple, Optional, Union, cast

import altair as alt
import mercantile as mt
import xyzservices.providers as providers
from xyzservices import TileProvider

# Tile size (pixels) used by OSM-compatible tile providers.
_DEFAULT_TILE_SIZE: Final[int] = 256


def _content_hash(*parts: object) -> str:
    """Return a 12-char deterministic hex digest of the given objects.

    Serialises each part to JSON (with sorted keys) and hashes the result
    with SHA-256.  Identical inputs always produce the same suffix; different
    inputs produce different suffixes with overwhelming probability.
    """
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


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

    """
    # Derive the view suffix from the chart's projection + dimensions only —
    # these are what make two panels require distinct param names, and hashing
    # the full chart dict (including inline GeoJSON) would be slow and fragile.
    _proj = chart.projection
    _chart_w = chart.width if chart.width is not alt.Undefined else None
    _chart_h = chart.height if chart.height is not alt.Undefined else None
    _suffix = _content_hash(
        _proj.to_dict() if hasattr(_proj, "to_dict") else str(_proj),
        width or _chart_w,
        height or _chart_h,
    )
    tiles = create_tiles_chart(
        provider=provider,
        zoom=zoom,
        # Set attribution to False here as we want to add it in the end so it is
        # on top of the geoshape layer.
        attribution=False,
        standalone=False,
        width=width,
        height=height,
        _view_suffix=_suffix,
    )

    final_chart = tiles + chart
    if attribution:
        final_chart = add_attribution(  # type: ignore[assignment]
            chart=final_chart, provider=provider, attribution=attribution
        )
    # Rewrite placeholder projection refs to the plain 'projection' signal name.
    # If this chart is later passed to at.hconcat/vconcat/concat, those wrappers
    # will override it again to concat_N_projection on the serialised dict.
    _rewrite_params_inplace(final_chart, "projection")

    return final_chart

def create_tiles_chart(
    provider: Union[str, TileProvider] = "OpenStreetMap.Mapnik",
    zoom: Optional[int] = None,
    attribution: Union[str, bool] = True,
    standalone: Union[bool, alt.Projection] = True,
    width: Optional[int] = None,
    height: Optional[int] = None,
    _view_suffix: Optional[str] = None,
) -> Union[alt.LayerChart, alt.Chart]:
    """Creates an Altair chart with tiles.

    Parameters
    ----------
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

    # Derive a deterministic suffix for param names and the view name.
    # Identical inputs always produce the same spec; different inputs (e.g. two
    # panels in an hconcat with different projections) produce different suffixes
    # so Altair does not collapse their params.  add_tiles passes the user chart's
    # content hash so the suffix differs between panels even when provider/zoom/
    # width/height are identical.
    view_suffix = _view_suffix or _content_hash(
        getattr(provider, "url", str(provider)), zoom, width, height
    )

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
        view_suffix=view_suffix,
    )

    if standalone:
        if standalone is True:
            standalone = alt.Projection(type="mercator")
        else:
            _validate_projection(standalone)
        base_layer = alt.Chart().mark_geoshape().properties(projection=standalone)
        # If we use tiles as the first layer then the chart is 20px by 20px by default.
        # Unclear why but the other way around works fine.
        result = base_layer + tiles
        # Rewrite placeholder projection refs to the plain 'projection' signal name
        # used by standalone Vega-Lite views, avoiding a to_dict/from_dict round-trip.
        _rewrite_params_inplace(result, "projection")
        return result
    else:
        return tiles

def _build_tile_url(provider: TileProvider, x: str, y: str, z: str) -> str:
    """Build a Vega expression string for a tile URL with x/y/z interpolated."""
    fmt = lambda v: f"' + {v} + '"
    return "'" + provider.build_url(x=fmt(x), y=fmt(y), z=fmt(z)) + "'"


def _create_nonstandalone_tiles_chart(
    provider: TileProvider,
    zoom: Optional[int],
    attribution: Union[str, bool],
    width: Optional[int],
    height: Optional[int],
    view_suffix: str,
) -> Union[alt.Chart, alt.LayerChart]:
    # The calculations below are based on initial implementations in Vega
    # https://github.com/vega/vega/issues/1212#issuecomment-384680678 and in Vega-Lite
    # https://github.com/vega/vega-lite/issues/5758#issuecomment-1462683219.

    # The view name for this tile chart. Vega-Lite derives the projection signal
    # name as "{view_name}_projection", so this must be unique per tile chart
    # instance when multiple tile charts are used together in a concat layout.
    view_name = f"tiles_{view_suffix}"

    # All param names include the view_suffix so that when two tile charts are
    # placed in an hconcat/vconcat, Altair does not deduplicate them (which would
    # collapse the two independent projection references into one).
    def pname(base: str) -> str:
        return f"{base}_{view_suffix}"

    p_pr_scale = alt.param(
        expr=f"geoScale('{view_name}_projection')", name=pname("pr_scale")
    )

    if zoom is not None:
        p_zoom_level = alt.param(value=zoom, name=pname("zoom_level"))
        p_base_tile_size = alt.param(
            expr=f"(2 * PI * {p_pr_scale.name}) / pow(2, {p_zoom_level.name})",
            name=pname("base_tile_size"),
        )
        evaluated_zoom_level_ceil = math.ceil(zoom)
    else:
        p_base_tile_size = alt.param(value=_DEFAULT_TILE_SIZE, name=pname("base_tile_size"))
        p_zoom_level = alt.param(
            expr=f"log((2 * PI * {p_pr_scale.name}) / {p_base_tile_size.name}) /"
            + " log(2)",
            name=pname("zoom_level"),
        )
        evaluated_zoom_level_ceil = None

    if evaluated_zoom_level_ceil is not None:
        _validate_zoom(evaluated_zoom_level_ceil, provider=provider)

    p_zoom_ceil = alt.param(
        expr=f"ceil({p_zoom_level.name})", name=pname("zoom_ceil")
    )
    # Number of tiles per column/row, whichever is larger. Total number of tiles
    # would then be this number squared. However, this number does not account
    # for tiles which will be outside of the view, i.e. what is visible on the chart.
    # It is therefore just the maximum if the whole earth would be visible.
    # If calculation of this is changed here, it should also be changed in the
    # _calculate_one_side_grid_size function which calculates this number
    # in Python.
    p_max_one_side_tiles_count = alt.param(
        expr=f"pow(2, {p_zoom_ceil.name})", name=pname("max_one_side_tiles_count")
    )
    p_tile_size = alt.param(
        expr=p_base_tile_size.name
        + f" * pow(2, {p_zoom_level.name} - {p_zoom_ceil.name})",
        name=pname("tile_size"),
    )
    p_base_point = alt.param(
        expr=f"invert('{view_name}_projection', [0, 0])", name=pname("base_point")
    )
    p_dii = alt.param(
        expr=f"({p_base_point.name}[0] + 180) / 360"
        + f" * {p_max_one_side_tiles_count.name}",
        name=pname("dii"),
    )
    p_dii_floor = alt.param(expr=f"floor({p_dii.name})", name=pname("dii_floor"))
    p_dx = alt.param(
        expr=f"({p_dii_floor.name} - {p_dii.name}) * {p_tile_size.name}",
        name=pname("dx"),
    )
    p_djj = alt.param(
        expr=f"(1 - log(tan({p_base_point.name}[1] * PI / 180)"
        + f" + 1 / cos({p_base_point.name}[1] * PI / 180)) / PI)"
        + f" / 2 * {p_max_one_side_tiles_count.name}",
        name=pname("djj"),
    )
    p_djj_floor = alt.param(expr=f"floor({p_djj.name})", name=pname("djj_floor"))
    p_dy = alt.param(
        expr=f"round(({p_djj_floor.name} - {p_djj.name}) * {p_tile_size.name})",
        name=pname("dy"),
    )
    expr_url_x = (
        f"((datum.a + {p_dii_floor.name} + {p_max_one_side_tiles_count.name})"
        + f" % {p_max_one_side_tiles_count.name})"
    )
    expr_url_y = f"(datum.b + {p_djj_floor.name})"

    one_side_grid_size = _calculate_one_side_grid_size(evaluated_zoom_level_ceil)

    tile_list = alt.sequence(
        0, one_side_grid_size, as_="a", name=f"tile_list_{view_suffix}"
    )

    # Can be a layerchart after adding attribution.
    # The view_name is set on the image Chart (layer[0]) so that:
    # - add_tiles can read tiles.name to propagate it to the outer LayerChart
    # - it appears only on the first layer item, not duplicated on the LayerChart
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
            url=_build_tile_url(provider, x=expr_url_x, y=expr_url_y, z=p_zoom_ceil.name),
            x=f"datum.a * {p_tile_size.name} + {p_dx.name} + ({p_tile_size.name} / 2)",
            y=f"datum.b * {p_tile_size.name} + {p_dy.name} + ({p_tile_size.name} / 2)",
        )
        .properties(name=view_name)
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
        f"datum.x < ({width or 'width'} + {p_tile_size.name} / 2) && "
        + f"datum.y < ({height or 'height'} + {p_tile_size.name} / 2)"
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
        tiles = tiles.transform_filter(
            f"{expr_url_x} >= 0 && {expr_url_y} >= 0"
            + f" && {expr_url_x} <= ({p_max_one_side_tiles_count.name} - 1)"
            + f" && {expr_url_y} <= ({p_max_one_side_tiles_count.name} - 1)"
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
        tiles = tiles.transform_filter(
            f"{expr_url_x} >= {x_y_min_max.x_min} && {expr_url_y} >= {x_y_min_max.y_min}"
            + f" && {expr_url_x} <= {x_y_min_max.x_max} && {expr_url_y} <= {x_y_min_max.y_max}"
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

    if attribution:
        return add_attribution(tiles, provider, attribution)
    return tiles

class _XYMinMax(NamedTuple):
    x_min: int
    y_min: int
    x_max: int
    y_max: int

def _bounds_to_x_y_min_max(bounds: list[list[float]], zoom: int) -> _XYMinMax:
    south_west, north_east = bounds
    south, west = south_west
    north, east = north_east
    xs, ys = zip(*((t.x, t.y) for t in mt.tiles(west=west, south=south, east=east, north=north, zooms=[zoom])))
    return _XYMinMax(x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))

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
        detail = f" (valid zooms: {min_zoom} - {max_zoom})" if max_zoom_known else ""
        raise ValueError(
            f"The zoom level of {zoom} is not valid for the current tile provider{detail}."
        )

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
    if evaluated_zoom_level_ceil is not None:
        # Same formula as max_one_side_tiles_count in the Vega-Lite spec.
        # +2 is a small buffer to ensure edge tiles are covered.
        return min(2**evaluated_zoom_level_ceil + 2, maximum_value)
    return maximum_value

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

# ---------------------------------------------------------------------------
# Projection signal name rewriting
# ---------------------------------------------------------------------------

_TILE_PROJ_RE = re.compile(r"tiles_[0-9a-f]+_projection")
_ANY_PROJ_RE = re.compile(r"'[^']*projection[^']*'")

# The internal view name prefix used by altair_tiles for tile layer charts.
_TILE_VIEW_PREFIX = "tiles_"

def _rewrite_params_inplace(chart: alt.LayerChart, replacement: str) -> None:
    """Mutate ``geoScale`` / ``invert`` tile projection references in-place on
    *chart* and all of its sublayers, replacing every ``tiles_*_projection``
    occurrence with *replacement* (e.g. ``'projection'`` or
    ``'concat_0_projection'``).

    This avoids a ``to_dict`` / ``from_dict`` round-trip which would add a
    top-level ``$schema`` field and make the chart unusable as a subchart.
    """
    params = getattr(chart, "params", None)
    if params and not isinstance(params, type(alt.Undefined)):
        for p in params:
            expr = getattr(p, "expr", None)
            if expr and not isinstance(expr, type(alt.Undefined)):
                new_expr = _TILE_PROJ_RE.sub(replacement, str(expr))
                if new_expr != str(expr):
                    p["expr"] = new_expr
    layer = getattr(chart, "layer", None)
    if layer and not isinstance(layer, type(alt.Undefined)):
        for sub in layer:
            _rewrite_params_inplace(sub, replacement)

def _rewrite_tile_projection_refs(spec: dict) -> dict:
    """Post-process a Vega-Lite spec dict to rewrite tile projection signal
    references so that they match the signal names Vega-Lite's normalizer
    produces at runtime.

    Each tile chart's params are named with a unique suffix
    (e.g. ``pr_scale_abc123``), and each tile LayerChart is named
    ``tiles_abc123``. When placed into a concat, Vega-Lite assigns the
    projection signal name ``concat_{i}_projection`` to the i-th cell.

    This function matches param-name suffixes to concat-cell positions and
    rewrites the ``geoScale`` / ``invert`` expressions from
    ``geoScale('projection')`` to ``geoScale('concat_i_projection')``.

    Parameters
    ----------
    spec : dict
        A Vega-Lite spec dict as returned by ``chart.to_dict()``.

    Returns
    -------
    dict
        A new spec dict with the projection references rewritten.
    """
    spec = copy.deepcopy(spec)

    # Build map: param suffix -> Vega projection signal name
    # by matching the tile view names in concat cells to their positions.
    suffix_to_signal: dict[str, str] = {}

    def _collect_cells(cells: list, prefix: str) -> None:
        for i, cell in enumerate(cells):
            # The tile name is on layer[0] (the image mark), not on the outer LayerChart.
            # Walk the first layer item to find it.
            name = cell.get("name", "")
            if not name.startswith(_TILE_VIEW_PREFIX):
                # Name is on layer[0] (image mark), not the outer LayerChart.
                layers = cell.get("layer", [])
                if layers:
                    name = layers[0].get("name", "")
            if name.startswith(_TILE_VIEW_PREFIX):
                suffix = name[len(_TILE_VIEW_PREFIX):]
                suffix_to_signal[suffix] = f"{prefix}{i}_projection"
            for nested_key in ("hconcat", "vconcat", "concat"):
                if nested_key in cell:
                    _collect_cells(cell[nested_key], f"{prefix}{i}_{nested_key[0]}concat_")

    for concat_key in ("hconcat", "vconcat", "concat"):
        if concat_key in spec:
            _collect_cells(spec[concat_key], "concat_")
            break

    if not suffix_to_signal:
        return spec  # no tile concat cells found, nothing to rewrite

    # Rewrite params: identify each param's tile suffix from its name,
    # then replace whatever projection signal is in the expr with the correct name.
    # Param names follow the pattern: "{base}_{suffix}" (e.g. "pr_scale_abc123").
    # The expr may reference 'projection' (after standalone rewrite) or
    # 'tiles_{suffix}_projection' (when coming from add_tiles / standalone=False).
    # We replace either form with the correct 'concat_N_projection' signal.
    for p in spec.get("params", []):
        pname = p.get("name", "")
        expr = p.get("expr", "")
        if not expr:
            continue
        parts = pname.rsplit("_", 1)
        if len(parts) == 2 and parts[1] in suffix_to_signal:
            signal = suffix_to_signal[parts[1]]
            p["expr"] = _ANY_PROJ_RE.sub(f"'{signal}'", expr)

    return spec

# ---------------------------------------------------------------------------
# Concat wrappers
# ---------------------------------------------------------------------------

def _wrap_concat(alt_fn, *charts, **kwargs):
    """Internal helper: call an altair concat function then rewrite projection refs.

    We serialise to a dict, rewrite the tile projection signal names to match
    what Vega-Lite's normalizer will produce at runtime, and round-trip back to
    a proper altair chart object via ``Chart.from_dict``.  The round-trip is
    inexpensive and keeps the return type as a fully-featured altair object.
    """
    combined = alt_fn(*charts, **kwargs)
    rewritten = _rewrite_tile_projection_refs(combined.to_dict())
    return alt.Chart.from_dict(rewritten)

def hconcat(*charts, **kwargs) -> alt.ConcatChart:
    """Horizontally concatenate charts, correctly rewriting tile projection
    signal references for each concat cell.

    This is a thin wrapper around :func:`altair.hconcat` that fixes the
    ``geoScale`` / ``invert`` projection name in tile chart params.
    Use this instead of ``alt.hconcat`` whenever any of the charts were
    created with :func:`create_tiles_chart` or :func:`add_tiles`.

    All arguments are forwarded verbatim to ``alt.hconcat``.
    """
    return _wrap_concat(alt.hconcat, *charts, **kwargs)

def vconcat(*charts, **kwargs) -> alt.ConcatChart:
    """Vertically concatenate charts, correctly rewriting tile projection
    signal references for each concat cell.

    This is a thin wrapper around :func:`altair.vconcat` that fixes the
    ``geoScale`` / ``invert`` projection name in tile chart params.
    Use this instead of ``alt.vconcat`` whenever any of the charts were
    created with :func:`create_tiles_chart` or :func:`add_tiles`.

    All arguments are forwarded verbatim to ``alt.vconcat``.
    """
    return _wrap_concat(alt.vconcat, *charts, **kwargs)

def concat(*charts, **kwargs) -> alt.ConcatChart:
    """Concatenate charts (wrappable grid), correctly rewriting tile projection
    signal references for each concat cell.

    This is a thin wrapper around :func:`altair.concat` that fixes the
    ``geoScale`` / ``invert`` projection name in tile chart params.
    Use this instead of ``alt.concat`` whenever any of the charts were
    created with :func:`create_tiles_chart` or :func:`add_tiles`.

    All arguments are forwarded verbatim to ``alt.concat``.
    """
    return _wrap_concat(alt.concat, *charts, **kwargs)