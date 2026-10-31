#!/usr/bin/env python3
"""Serve the four-R9700 DeepSeek V4.1 GSQ-RCO profile through Strata's HTTP API."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--context', type=int, default=8192)
    parser.add_argument('--decoding', choices=['baseline', 'dspark'], default='baseline')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=18920)
    args = parser.parse_args()
    if not 2048 <= args.context <= 68608 or not 1 <= args.port <= 65535:
        parser.error('Context must be 2048–68608 and the API port 1–65535.')
    pack = args.pack.resolve()
    for file in ['ds4.txt', 'expert-profile.bin', 'tokenizer/vocab.json', 'tokenizer/chat_template.jinja']:
        if not (pack / file).is_file():
            parser.error('Prepare the complete native DeepSeek V4.1 pack first: missing ' + file)
    with tempfile.TemporaryDirectory(prefix='strata-v41-') as temporary:
        work = Path(temporary)
        shutil.copyfile(pack / 'expert-profile.bin', work / 'expert-profile.bin')
        engine_args = ['--pack', str(pack), '--gpus', '0,1,2,3', '--max-context', str(args.context),
                       '--tp', '1', '--experts', '6', '--vision', 'off',
                       '--dspark', 'on' if args.decoding == 'dspark' else 'none',
                       '--dspark-conf', '0.65', '--expert-profile', str(work / 'expert-profile.bin'),
                       '--mmap-experts', 'auto']
        config = {'exe': '/usr/local/bin/strata-dsv41', 'args': engine_args, 'cwd': '/opt/strata',
                  'tokenizer': str(pack / 'tokenizer'), 'model_name': 'DeepSeek-V4.1-Flash-1017',
                  'arch': 'deepseek41', 'backend': 'hip', 'gpu': [0, 1, 2, 3], 'gpus_asked': True,
                  'engine_ready_s': 3600, 'parallel': 1, 'host': args.host, 'port': args.port,
                  'log': str(work / 'engine.log'), 'prevent_sleep': False, 'open_browser': False}
        configuration = work / 'config.json'
        configuration.write_text(json.dumps(config))
        command = [sys.executable, '/opt/strata/serve/server.py', '--engine', 'strata', '--config',
                   str(configuration), '--host', args.host, '--port', str(args.port), '--offline']
        raise SystemExit(subprocess.call(command, env={**os.environ, 'STRATA_DS4_SLOT_KEEP': '0'}))


if __name__ == '__main__':
    main()
