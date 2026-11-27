PYTHON ?= python3
RUFF ?= ruff
export PYTHONDONTWRITEBYTECODE := 1
# One BLAS thread keeps the bootstrap's floating-point sums identical across machines.
export OPENBLAS_NUM_THREADS := 1
export VECLIB_MAXIMUM_THREADS := 1

.PHONY: check verify test lint public-tree generated overall site readme figures

check: lint test public-tree verify generated

lint:
	$(RUFF) check --no-cache translate_bench tests tools

test:
	$(PYTHON) -m unittest discover -s tests -t .

public-tree:
	$(PYTHON) tools/check_public_tree.py --history

verify:
	$(PYTHON) -m translate_bench.cli verify

# results/v1.1/overall.json, the generated blocks of the READMEs and docs, and site/data.js must match the results.
generated:
	$(PYTHON) -m translate_bench.overall --check
	$(PYTHON) -m translate_bench.export.readme --check
	$(PYTHON) -m translate_bench.export.site_data --check

# Write results/v1.1/overall.json from results/v1/ and results/ltb-v1/; run before `make readme` and `make site`.
overall:
	$(PYTHON) -m translate_bench.overall

site:
	$(PYTHON) -m translate_bench.export.site_data

readme:
	$(PYTHON) -m translate_bench.export.readme

# Needs the figures extra: python -m pip install -e '.[figures]'
figures:
	$(PYTHON) -m translate_bench.export.figures
