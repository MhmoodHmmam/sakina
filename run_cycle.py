"""Headless agent cycle. Use this for the demo's log panel.

    python run_cycle.py jamarat-bridge
"""
import sys
from dotenv import load_dotenv
load_dotenv()

from sakina.agent import Sakina
from sakina.camara import CamaraTools

zone = sys.argv[1] if len(sys.argv) > 1 else "jamarat-bridge"
agent = Sakina(CamaraTools())
state, trace = agent.cycle(zone)
print(trace.render_console())
print("\n" + "=" * 70)
live, total = trace.live_ratio()
print(f"{total} CAMARA calls ({live} live) across {len(trace.apis_touched())} APIs")
print("APIs:", ", ".join(trace.apis_touched()))
