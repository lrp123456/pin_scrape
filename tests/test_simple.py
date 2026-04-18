import sys
import subprocess

sys.path.insert(0, '..')

result = subprocess.run(
    [sys.executable, '-c', 'import scraper'],
    capture_output=True,
    text=True,
    cwd='..'
)
print('Return code:', result.returncode)
print('Stdout:', result.stdout)
print('Stderr:', result.stderr)
