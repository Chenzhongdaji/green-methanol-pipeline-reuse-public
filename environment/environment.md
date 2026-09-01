# Reproduction environment

- Python 3.12 (the version range is also declared in `pyproject.toml`).
- Install the five pinned dependencies from `requirements.txt`:
  `numpy==2.5.1`, `pandas==3.0.1`, `matplotlib==3.11.1`, `networkx==3.5`,
  and `pytest==8.4.2`.
- Install this package in editable mode with `python -m pip install -e .`.
- Run `python scripts/reproduce.py --mode smoke --output <external-output>/smoke.json`.

The runtime uses the five pinned scientific/verification dependencies listed
above plus the Python standard library and declared package metadata. The
release-facing `--output` option always names a report file (for example
`full_reproduction.json`), while logs and generated artifacts are written in
that report's external parent directory.
