"""OKKI automation package (recon skeleton + spine service layer)."""

from .core_models import ActionIntent, ObservationBundle, PreparedActionPlan, ReadModel
from .core_service import (
    build_okki_audit_event,
    detect_okki_page_mode,
    observe_alibaba_inquiry,
    observe_okki_customer,
    prepare_alibaba_action,
    prepare_okki_action,
    verify_okki_action,
)
from .page_model import ActionPlan, PageMode, ReadResult, StructuredError

__all__ = [
    "ActionIntent",
    "ActionPlan",
    "ObservationBundle",
    "PageMode",
    "PreparedActionPlan",
    "ReadModel",
    "ReadResult",
    "StructuredError",
    "build_okki_audit_event",
    "detect_okki_page_mode",
    "observe_alibaba_inquiry",
    "observe_okki_customer",
    "prepare_alibaba_action",
    "prepare_okki_action",
    "verify_okki_action",
]
