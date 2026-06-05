"""Shared native renderer health stubs for routing tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from meshcorral.services.environment.native_renderer_health import NativeRendererHealth

_HEALTHY = NativeRendererHealth(
    available=True,
    missing_dependencies=(),
    detail="Native CPU renderer ready for STL/OBJ.",
    checked_at=0.0,
    can_render_stl_obj=True,
    fallback_backend="native",
)

_UNAVAILABLE_NUMPY = NativeRendererHealth(
    available=False,
    missing_dependencies=("numpy",),
    detail="Native CPU renderer unavailable (NumPy).",
    checked_at=0.0,
    can_render_stl_obj=False,
    fallback_backend="blender",
)


def healthy_native_health() -> NativeRendererHealth:
    """Native deps available (routing tests that expect CPU path)."""
    return _HEALTHY


def unavailable_native_health() -> NativeRendererHealth:
    """Native deps missing (degradation tests)."""
    return _UNAVAILABLE_NUMPY


@contextmanager
def patch_healthy_native_routing() -> Iterator[None]:
    """Force routing policy to treat native renderer as ready."""
    with patch(
        "meshcorral.services.thumbnails.thumbnail_routing_policy.get_native_renderer_health",
        return_value=healthy_native_health(),
    ):
        yield
