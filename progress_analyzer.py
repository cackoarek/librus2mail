"""Root wrapper for `librus2mail.progress_analyzer`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.progress_analyzer import (  # noqa: F401, E402
    GRADE_THRESHOLDS,
    GRADE_VALUE_MAP,
    ProgressAnalyzer,
    _calculate_needed_grade,
    _format_needed_grade_advice,
    get_predicted_grade,
    get_predicted_grade_tuple,
    parse_grade_date,
    parse_numeric_grade,
    parse_weight,
)

__all__ = [
    "ProgressAnalyzer",
    "GRADE_VALUE_MAP",
    "GRADE_THRESHOLDS",
    "parse_numeric_grade",
    "parse_weight",
    "parse_grade_date",
    "get_predicted_grade",
    "get_predicted_grade_tuple",
    "_calculate_needed_grade",
    "_format_needed_grade_advice",
]
