#!/usr/bin/env python3
"""Open a local interactive formatting preview; never changes saved options."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import webbrowser
import pace_config


def render(cfg):
    template = (Path(__file__).resolve().parent.parent / 'preview' / 'index.html').read_text()
    # JSON is embedded in script text, where HTML closing tags must be escaped.
    return template.replace('__CONFIG__', json.dumps(cfg).replace('<', '\\u003c'))


def preview_config():
    return pace_config.load_effective_config(env=pace_config.option_environment())[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='Open the preview in your browser')
    parser.add_argument('--output', type=Path, help='Save to this HTML file')
    args = parser.parse_args()
    if args.output:
        path = args.output.resolve()
        path.write_text(render(preview_config()), encoding='utf-8')
    else:
        fd, name = tempfile.mkstemp(prefix='human-pace-preview-', suffix='.html')
        path = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(render(preview_config()))
    print(path)
    if args.open:
        if not webbrowser.open(path.as_uri()):
            print('Open the HTML file above in a browser to view the preview.')


if __name__ == '__main__':
    main()
