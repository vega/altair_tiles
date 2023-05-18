# altair_basemap

This package is in a **very early development stage** and should not yet be used for anything serious. You can find some examples in [this notebook](https://nbviewer.org/github/binste/altair_basemap/blob/main/Examples.ipynb).

Inspired by [contextily](https://github.com/geopandas/contextily) and based on initial implementations [in Vega](https://github.com/vega/vega/issues/1212#issuecomment-384680678) and [in Vega-Lite](https://github.com/vega/vega-lite/issues/5758#issuecomment-1462683219). Currently, this package is used to test out how the extended Vega-Lite spec should look like for an implementation [in Vega-Lite as part of the geoshape mark](https://github.com/vega/vega-lite/pull/8885). However, we might also release this package to bridge the time until the functionality is implemented in Vega-Lite.

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
