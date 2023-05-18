# altair_basemaps

This package is in a **very early development stage** and should not yet be used for anything serious.

Inspired by [contextily](https://github.com/geopandas/contextily) and the work started in [the Vega-Lite PR 8885](https://github.com/vega/vega-lite/pull/8885) and the discussions which preceeded it. Currently, this package is used to test out how the extended Vega-Lite spec should look like for the previously mentioned PR. However, we might also release this package to bridge the time until the functionality is implemented in Vega-Lite.

---

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run linters (and soon tests) with
```bash
hatch run test
```
