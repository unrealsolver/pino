from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pino_core.models import Record, Refinement


@dataclass(frozen=True)
class QCFlag:
    level: Literal["warning", "error"]
    message: str | None = None


@dataclass(frozen=True)
class QCReport:
    schedule: QCFlag | None = None

    @property
    def has_errors(self) -> bool:
        return self.schedule is not None and self.schedule.level == "error"


RefinementQC: TypeAlias = Callable[[Record, Refinement], QCReport]


def no_refinement_qc(record: Record, refinement: Refinement) -> QCReport:
    return QCReport()
