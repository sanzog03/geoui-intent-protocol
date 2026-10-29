"""geouibench: a benchmark utility for agents that drive a geospatial UI, whatever the mechanism.

The agent under test is a black box: user text in, an assistant turn plus a
trace out. The utility knows pydantic-ai (to run the agent), deepeval (to
simulate the user, generate synthetic goldens and score the conversation)
and the GeoIntent schema (as the vocabulary for "what the UI shows"), and
nothing about any particular application or about *how* an agent acts. An
application plugs in through an app directory whose ``app.py`` exposes a
:class:`geouibench.app.BenchmarkApp`; ``python -m geouibench run <app dir>``
does the rest.
"""

from geouibench.app import BenchmarkApp
from geouibench.apps import AppDir, load_app_dir
from geouibench.datasets import Budgets
from geouibench.synthetic import SyntheticStyle

__all__ = ["AppDir", "BenchmarkApp", "Budgets", "SyntheticStyle", "load_app_dir"]
