__version__ = "0.1.0dev"
__all__ = ["add_basemap", "providers"]

import math
from typing import Optional

import altair as alt
import xyzservices.providers as providers
from xyzservices import TileProvider


def add_basemap(
    chart: alt.Chart,
    source: TileProvider = providers.OpenStreetMap.Mapnik,
    zoom: Optional[int] = None,
    grid_num_columns: int = 10,
    grid_num_rows: int = 10,
) -> alt.LayerChart:
    # Size of tile grid needs to be calculated in Python as it is not possible
    # yet to use an expression in a data generator such as a sequence.
    # See https://github.com/vega/vega-lite/issues/7410
    # The issue with this is that it depends on the size of the chart which
    # we cannot yet know at this point as it might be changed by e.g. a theme
    # or by the user themselves when working with the returned layered chart.
    # The default values for num_grid_columns and num_grid_rows are the same
    # to produce a quadratic grid which should be large
    # enough for most use cases. The user can use the input arguments
    # to overwrite this in case the default size is not large enough.
    # Tiles seem to be only fetched in a browser if they are visible and not clipped
    # so there should be not much of a downside when using a large grid by default.
    # If we could access the size of the chart in the Python code, we could
    # calculate the grid size using something like
    # grid_num_columns = ceil(width/p_tile_size +1)
    # grid_num_rows = ceil(height/p_tile_size +1)

    if not isinstance(chart, alt.Chart):
        raise TypeError("Only altair.Chart instances are supported.")

    if zoom is not None and not isinstance(zoom, int):
        raise TypeError("Zoom must be an integer or None.")

    _validate_chart(chart)

    if (
        chart.projection is not alt.Undefined
        and chart.projection.scale is not alt.Undefined
    ):
        scale = chart.projection.scale
    else:
        # Need to figure out default value for scale for mercator projection.
        # 961 / math.tau does not work. Found here:
        # https://github.com/d3/d3-geo/blob/main/src/projection/mercator.js#L13
        raise NotImplementedError
        scale = 961 / math.tau
    # Convert to string in case it is a Vega expression
    p_pr_scale = alt.param(expr=str(scale), name="pr_scale")

    if zoom is not None:
        p_zoom_level = alt.param(value=zoom, name="zoom_level")
        p_base_tile_size = alt.param(
            expr=f"(2 * PI * {p_pr_scale.name}) / pow(2, {p_zoom_level.name})",
            name="base_tile_size",
        )
    else:
        # Calculate an appropriate zoom level based on the projection scale
        # and the tile size.
        p_base_tile_size = alt.param(value=256, name="base_tile_size")
        p_zoom_level = alt.param(
            expr=f"log((2 * PI * {p_pr_scale.name}) / {p_base_tile_size.name}) / log(2)",
            name="zoom_level",
        )

    p_zoom_ceil = alt.param(expr=f"ceil({p_zoom_level.name})", name="zoom_ceil")
    p_tiles_count = alt.param(expr=f"pow(2, {p_zoom_ceil.name})", name="tiles_count")
    p_tile_size = alt.param(
        expr=p_base_tile_size.name
        + f" * pow(2, {p_zoom_level.name} - {p_zoom_ceil.name})",
        name="tile_size",
    )
    p_base_point = alt.param(expr="invert('projection', [0, 0])", name="base_point")
    p_dii = alt.param(
        expr=f"({p_base_point.name}[0] + 180) / 360 * {p_tiles_count.name}", name="dii"
    )
    p_dii_floor = alt.param(expr=f"floor({p_dii.name})", name="dii_floor")
    p_dx = alt.param(
        expr=f"({p_dii_floor.name} - {p_dii.name}) * {p_tile_size.name}", name="dx"
    )
    p_djj = alt.param(
        expr=f"(1 - log(tan({p_base_point.name}[1] * PI / 180)"
        + f" + 1 / cos({p_base_point.name}[1] * PI / 180)) / PI)"
        + f" / 2 * {p_tiles_count.name}",
        name="djj",
    )
    p_djj_floor = alt.param(expr=f"floor({p_djj.name})", name="djj_floor")
    p_dy = alt.param(
        expr=f"round(({p_djj_floor.name} - {p_djj.name}) * {p_tile_size.name})",
        name="dy",
    )
    expr_url_x = (
        f"((datum.a + {p_dii_floor.name} + {p_tiles_count.name})"
        + f" % {p_tiles_count.name})"
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

    tile_list = alt.sequence(0, grid_num_columns, as_="a", name="tile_list")
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
        .transform_calculate(b=f"sequence(0, {grid_num_rows})")
        .transform_flatten(["b"])
        .transform_calculate(
            url=build_url(source, x=expr_url_x, y=expr_url_y, z=p_zoom_ceil.name),
            x=f"datum.a * {p_tile_size.name} + {p_dx.name} + ({p_tile_size.name} / 2)",
            y=f"datum.b * {p_tile_size.name} + {p_dy.name} + ({p_tile_size.name} / 2)",
        )
    )

    layered_chart = (tiles + chart).add_params(
        p_base_tile_size,
        p_pr_scale,
        p_zoom_level,
        p_zoom_ceil,
        p_tiles_count,
        p_tile_size,
        p_base_point,
        p_dii,
        p_dii_floor,
        p_dx,
        p_djj,
        p_djj_floor,
        p_dy,
    )
    return layered_chart


def _validate_chart(chart: alt.Chart) -> None:
    if chart.projection is alt.Undefined or chart.projection.type != "mercator":
        raise ValueError("Chart must have a Mercator projection.")

    if chart.projection is alt.Undefined or chart.projection.scale is alt.Undefined:
        raise ValueError("Chart must have a projection scale set.")
