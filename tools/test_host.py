"""Build and run host tests without connecting to or flashing hardware."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
build = root / 'build-host'
subprocess.run(['cmake', '-S', str(root), '-B', str(build)], check=True)
subprocess.run(['cmake', '--build', str(build), '--config', 'Release'], check=True)
subprocess.run(['ctest', '--test-dir', str(build), '-C', 'Release', '--output-on-failure'], check=True)
env = os.environ.copy()
env['AHAKEY_ADPCM_ENCODER'] = str(root / 'dist' / ('adpcm_encoder.exe' if os.name == 'nt' else 'adpcm_encoder'))
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
               cwd=root, env=env, check=True)
