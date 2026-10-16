"""Contracts shared between modules (CLAUDE.md §5.3).

Modules never import each other; they depend only on these interfaces and on
the event bus. Implementations are wired together in ``ev_core.app``.
"""
