"""geobench: a mechanism-neutral benchmark harness for agents that drive a geospatial UI.

The harness treats the agent under test as a black box: user text in, an
assistant turn plus a trace out. It knows pydantic-ai (to run the agent),
deepeval (to simulate the user and score the conversation) and the GeoIntent
schema (as the vocabulary for "what the UI shows"), and nothing about any
particular application or about *how* an agent acts. An application plugs
in through :class:`geobench.app.BenchmarkApp`.
"""

from geobench.app import BenchmarkApp

__all__ = ["BenchmarkApp"]
