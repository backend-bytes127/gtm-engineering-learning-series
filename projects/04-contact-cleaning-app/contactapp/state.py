"""The last result and CRM plan of one visitor. Replaced (never edited) on each run."""
from __future__ import annotations

import threading

from . import crm_plan, service
from .crm_plan import CrmPlan


class Session:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: service.RunResult | None = None
        self._plan: CrmPlan | None = None

    def set(self, result: service.RunResult) -> None:
        with self._lock:
            self._result, self._plan = result, crm_plan.build_plan(result.rows)

    @property
    def result(self) -> service.RunResult | None:
        return self._result

    @property
    def plan(self) -> CrmPlan | None:
        return self._plan
