"""Reuse the existing engine fixtures and exact packet scenarios."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ENGINE_TESTS = Path(__file__).resolve().parent.parent / "engine"


def _load(name, path):
    spec = spec_from_file_location(name, ENGINE_TESTS / path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = _load("persistence_engine_fixtures", "conftest.py")
perception = _load("persistence_perception_fixtures", "perception/conftest.py")
vectors = _load("persistence_packet_vectors", "perception/test_packets.py")
pack = engine.pack
setup = engine.setup
make_world = perception.make_world
