"""Wrapper: sets BRIDGE_ALLOW_NETWORK=1 then delegates to cclog.main()."""
import os, sys
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cclog import main
raise SystemExit(main(sys.argv[1:]))
