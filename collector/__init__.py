"""Private collector; configure a TLS reverse proxy before external use."""
import sys
from pathlib import Path
scripts=str(Path(__file__).resolve().parents[1]/'scripts')
if scripts not in sys.path:sys.path.insert(0,scripts)
