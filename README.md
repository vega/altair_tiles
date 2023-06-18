<img src="https://raw.githubusercontent.com/altair-viz/altair_tiles/main/doc/logo.svg" height="110"></img>

This package is in an **early development stage**. You should expect things to break unannounced until we release a version `1.0.0`.

You can use altair_tiles to add tiles from any xyz tile provider to your Altair chart. The goal is to build a counterpart to the amazing [contextily](https://github.com/geopandas/contextily) package which provides this functionality for [matplotlib](https://matplotlib.org/).

You can find the documentation [here](https://altair-viz.github.io/altair_tiles).

## Installation
We have not yet put the package on pypi but you can install it from GitHub with:

```bash
pip install git+https://github.com/altair-viz/altair_tiles.git
```

## Development
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run linters and tests with
```bash
hatch run test
```

Build and view the documentation with
```bash
hatch run doc:clean
hatch run doc:build
hatch run doc:serve
```

To run a clean build and publish, run
```bash
hatch run doc:build-and-publish
```
