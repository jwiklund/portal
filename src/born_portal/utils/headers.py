"""Admin header links and attention badges, configured by registration.

Each page module registers its own header link (path, name, section and an
optional attention callable) through the shared :class:`HeaderProvider` created
in ``main``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Attention styles; also used as the CSS class suffix (nav-badge-*).
NOTIFICATION = "notification"
ERROR = "error"

_SECTIONS = ("main", "menu")


@dataclass(frozen=True)
class Attention:
    """A badge to show next to a header link.

    ``kind`` is the attention style (also the CSS class suffix) and ``label``
    is the accessible text announced to screen readers.
    """

    kind: str
    label: str = ""


AttentionReader = Callable[[], Awaitable[Attention | None]]
ErrorReporter = Callable[[object | None, BaseException, str], Awaitable[None]]


@dataclass(frozen=True)
class HeaderLink:
    """One resolved header link, ready for the template."""

    path: str
    name: str
    attention: Attention | None = None
    active: bool = False


@dataclass(frozen=True)
class _Registration:
    path: str
    name: str
    section: str
    attention: AttentionReader | None
    admin_only: bool
    viewer_path: str | None
    order: int


class HeaderProvider:
    """Collects header links and builds their context per request."""

    def __init__(self, report_error: ErrorReporter | None = None) -> None:
        self._links: list[_Registration] = []
        self._report_error = report_error

    def register(
        self,
        path: str,
        name: str,
        *,
        section: str = "main",
        attention: AttentionReader | None = None,
        admin_only: bool = False,
        viewer_path: str | None = None,
        order: int = 0,
    ) -> None:
        """Register a header link.

        ``section`` is ``"main"`` (always visible) or ``"menu"`` (collapsible
        menu). ``viewer_path`` replaces ``path`` for non-admins, and
        ``admin_only`` hides the link from them entirely. ``attention`` is an
        optional async callable returning an :class:`Attention` for the current
        request, or ``None`` for no badge.
        """
        if section not in _SECTIONS:
            raise ValueError(f"Unknown header section: {section}")
        self._links.append(
            _Registration(
                path=path,
                name=name,
                section=section,
                attention=attention,
                admin_only=admin_only,
                viewer_path=viewer_path,
                order=order,
            )
        )

    async def _attention(
        self, link: _Registration, request: object | None
    ) -> Attention | None:
        """Await a link's attention callable, if any."""
        if link.attention is None:
            return None
        try:
            return await link.attention()
        except Exception as exc:
            logger.exception("Failed to read header attention for %r", link.path)
            if self._report_error is not None:
                try:
                    await self._report_error(request, exc, link.path)
                except Exception:
                    logger.exception("Failed to report header attention error")
            return None

    async def context(
        self,
        *,
        is_admin: bool,
        current_path: str,
        request: object | None = None,
    ) -> dict[str, list[HeaderLink]]:
        """Resolve visible links and their attention badges for one request."""
        visible = sorted(
            (link for link in self._links if is_admin or not link.admin_only),
            key=lambda item: item.order,
        )
        attentions = await asyncio.gather(
            *(self._attention(link, request) for link in visible)
        )

        result: dict[str, list[HeaderLink]] = {"header_main": [], "header_menu": []}
        for link, attention in zip(visible, attentions, strict=True):
            path = link.viewer_path if link.viewer_path and not is_admin else link.path
            result[f"header_{link.section}"].append(
                HeaderLink(
                    path=path,
                    name=link.name,
                    attention=attention,
                    active=current_path.startswith(path),
                )
            )
        return result
