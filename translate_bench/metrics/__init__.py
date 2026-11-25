"""Metrics with the exact versions of the release. chrF++ needs only sacreBLEU; COMET-22 and MetricX-24 are
optional extras, imported only when requested."""


class MissingDependency(RuntimeError):
    """An optional metric was requested without its extra installed."""


def require(modules, extra):
    import importlib.util

    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    if missing:
        raise MissingDependency(
            f"{', '.join(missing)} not installed. Install the extra with: python -m pip install -e '.[{extra}]'"
        )
