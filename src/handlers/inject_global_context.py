from __future__ import annotations

from datetime import datetime
from typing import Any


def inject_global_context() -> dict[str, Any]:
    """Expose common template context such as the current year."""
    return {"current_year": datetime.utcnow().year}

