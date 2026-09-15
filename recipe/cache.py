"""Caching shim so recipe/ modules stay importable outside a Streamlit runtime.

Scripts and tests must not require a running Streamlit session, so
`cached` degrades to a no-op passthrough decorator when `streamlit` isn't
actually running (its cache decorators work fine to *apply*, but calling the
wrapped function outside a script run doesn't hit the network any
differently — this wrapper exists so call sites don't need an `if st` check
scattered through them).
"""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

import streamlit as st

F = TypeVar("F", bound=Callable)


def cached_data(ttl: int = 3600) -> Callable[[F], F]:
    """Wrap a function with st.cache_data, tolerating non-Streamlit contexts."""

    def decorator(func: F) -> F:
        try:
            return st.cache_data(ttl=ttl, show_spinner=False)(func)  # type: ignore[return-value]
        except Exception:  # noqa: BLE001 - fall back outside a Streamlit runtime

            @wraps(func)
            def passthrough(*args, **kwargs):
                return func(*args, **kwargs)

            return passthrough  # type: ignore[return-value]

    return decorator
