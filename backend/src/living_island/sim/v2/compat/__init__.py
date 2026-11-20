"""Bind the compat-v1 content pack to registered v1 configuration data."""

from .config import BoundCompatPack, CompatManifest, load_compat_pack

__all__ = ["BoundCompatPack", "CompatManifest", "load_compat_pack"]
