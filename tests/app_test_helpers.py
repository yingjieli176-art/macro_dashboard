"""Load isolated application functions without executing Streamlit startup.

One cached parse serves the test suite. Each caller gets copied AST nodes, so
stripping decorators in one fixture cannot change another fixture's cache tests.
"""
import ast
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=16)
def _source_tree(path, revision):
    return ast.parse(Path(path).read_text(encoding='utf-8'))


def load_functions(names, namespace, *, filename='app.py', constants=(),
                   import_modules=(), strip_decorators=False):
    source = ROOT / filename
    stat = source.stat()
    tree = _source_tree(str(source), (stat.st_mtime_ns, stat.st_size))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id in constants
                           for target in node.targets)]
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module in import_modules]
    nodes = deepcopy(assignments + imports + functions)
    if strip_decorators:
        for node in nodes:
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


def frame(dates, column, values):
    import pandas as pd
    return pd.DataFrame({'observation_date': pd.to_datetime(dates), column: values})


def builders():
    import pandas as pd
    import plotly.graph_objects as go
    from macro_platform.chart_axes import RANGE_OFFSETS
    names = {'add_line', '_mark_missing_series', 'filter_range',
             'build_fig1', 'build_fig9', 'build_fig10', 'build_fig11', 'build_fig12'}
    namespace = {'pd': pd, 'go': go, 'RANGE_OFFSETS': RANGE_OFFSETS,
        'load_correlation_snapshot': lambda symbol: frame([], symbol, []),
        'load_tail_risk_snapshot': lambda symbol: frame([], symbol, []),
        'load_spx_put_call_snapshot': lambda: frame([], 'SPX_PCR', []),
        'apply_chart_style': lambda fig, *args: fig,
        'chart_height': lambda *args: 420}
    return load_functions(names, namespace)
