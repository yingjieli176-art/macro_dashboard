"""Isolated full-tree restoration evidence; never a production rollback claim."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8502')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = {'environment': 'isolated CI restored tree, real snapshots, external sources offline',
              'production_rollback_verified': False, 'cloud_verified': False, 'status': 'failed'}
    try:
        actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual == args.sha, (actual, args.sha)
        report['restored_sha'] = actual
        files = [root/'app.py', root/'requirements.txt', *sorted((root/'data_snapshots').rglob('*.json'))]
        report['restored_file_sha256'] = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        report['installed_dependencies'] = {name: version(name) for name in ('streamlit', 'pandas', 'plotly', 'requests')}
        errors = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_function("document.querySelectorAll('[data-testid=stButtonGroup]').length === 13", timeout=60000)
            page.wait_for_function("document.querySelectorAll('[data-testid=stEChartsChart][aria-busy=false]').length >= 8", timeout=60000)
            assert page.get_by_test_id('stException').count() == 0
            assert page.get_by_test_id('stEChartsChartError').count() == 0
            paints = page.get_by_test_id('stEChartsChart').evaluate_all("""elements => elements.map(element =>
                [...element.querySelectorAll('canvas')].some(canvas => {
                    if (!canvas.width || !canvas.height) return false;
                    const data=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
                    for(let i=3;i<data.length;i+=4) if(data[i]>0) return true;
                    return false;
                }))""")
            assert all(paints) and len(paints) >= 8, paints
            assert not errors, errors
            report['chart_positions'] = 13
            report['painted_native_charts'] = len(paints)
            report['missing_data_labels'] = page.get_by_text('该图表目前没有可验证的有效观测数据', exact=False).count()
            report['page_errors'] = errors
            page.screenshot(path='rollback_acceptance.png', full_page=True)
            browser.close()
        report['status'] = 'passed'
        report['release_gate'] = 'NOT_APPROVED: restored offline tree still has incomplete source data; Cloud rollback remains unverified'
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        Path('rollback_acceptance.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
