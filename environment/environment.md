# Reproduction environment

- Python 3.12 (the version range is also declared in `pyproject.toml`).
- Install the two pinned requirements from `requirements.txt`.
- Install this package in editable mode with `python -m pip install -e .`.
- Run `python scripts/reproduce.py --mode smoke --output <external-output>/smoke.json`.

The runtime uses only the Python standard library plus the declared package
metadata; `pandas` is pinned for the release environment contract and
`pytest` is pinned for verification. Reports are written outside the immutable
repository tree.
