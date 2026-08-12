"""Advice document classifier and filing system — Phase 1.

Local, human-in-the-loop, pre-pilot. Reads knowledge_base.json as its single
source of domain truth and proposes a client-outer / advice-event-inner filing
tree. It never writes files and never files silently.

See SYSTEM.md for the spec and docs/ARCHITECTURE.md for how the pieces fit.
"""

__version__ = "0.4.0"
