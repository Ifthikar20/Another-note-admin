"""
Forward only what the contract names (a privacy layer of the BFF's own).

prune(data, Model) walks an admin API answer alongside its contract model (contract.py)
and keeps only the fields the model declares, at every depth. Unknown keys are dropped
and named in a warning, so drift between the admin API and this app gets noticed; a
value whose shape is wrong for its field (an object where text was expected) becomes
null. Values are not otherwise checked: validation is the admin API's job. This is the
allow-list: a field nobody reviewed cannot reach a staff member's screen.
"""

from __future__ import annotations

import logging
import re
import types
from datetime import date, datetime
from typing import Any, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel

logger = logging.getLogger("bff.shape")

_JSON_SCALARS = (str, int, float, bool)


class _Dropped(list):
    def note(self, where: str) -> None:
        if where not in self:
            self.append(where)


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _union_args(annotation: Any) -> Optional[tuple[Any, ...]]:
    origin = get_origin(annotation)
    if origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        return get_args(annotation)
    return None


# Keys of free-form maps (by_method_today, an audit row's details) and the text values of
# those maps: ids, method names and field names, never prose.
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:@/+\-]{1,120}$")


def _scalar_fits(value: Any, annotation: Any) -> bool:
    if isinstance(value, bool):
        return annotation is bool
    if isinstance(value, int):
        return annotation in (int, float)
    if isinstance(value, float):
        return annotation is float
    if isinstance(value, str):
        return annotation in (str, date, datetime)
    return False


def _fits(value: Any, annotation: Any) -> bool:
    """Whether a JSON value has the right kind of shape for an annotation."""
    if annotation is type(None):
        return value is None
    if _is_model(annotation):
        return isinstance(value, dict)
    origin = get_origin(annotation)
    if origin in (list, list):
        return isinstance(value, list)
    if origin in (dict, dict):
        return isinstance(value, dict)
    if origin is Literal:
        return isinstance(value, _JSON_SCALARS) and value in get_args(annotation)
    return _scalar_fits(value, annotation)


def _prune(value: Any, annotation: Any, where: str, dropped: _Dropped) -> Any:
    if value is None:
        return None
    union = _union_args(annotation)
    if union is not None:
        for arg in union:
            if arg is not type(None) and _fits(value, arg):
                return _prune(value, arg, where, dropped)
        dropped.note(where)
        return None
    if _is_model(annotation):
        if not isinstance(value, dict):
            dropped.note(where)
            return None
        out: dict[str, Any] = {}
        declared = {}
        for name, field in annotation.model_fields.items():
            declared[field.alias or name] = field.annotation
        for key, item in value.items():
            if key in declared:
                out[key] = _prune(item, declared[key], f"{where}.{key}", dropped)
            else:
                dropped.note(f"{where}.{key}")
        return out
    origin = get_origin(annotation)
    if origin in (list, list):
        if not isinstance(value, list):
            dropped.note(where)
            return None
        (inner,) = get_args(annotation) or (Any,)
        kept = []
        for item in value:
            if item is None or _fits(item, inner) or _union_args(inner) is not None:
                pruned = _prune(item, inner, f"{where}[]", dropped)
                if pruned is not None or item is None:
                    kept.append(pruned)
            else:
                dropped.note(f"{where}[]")
        return kept
    if origin in (dict, dict):
        if not isinstance(value, dict):
            dropped.note(where)
            return None
        _, inner = get_args(annotation) or (str, Any)
        out_map: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str) or not _IDENTIFIER.match(k):
                dropped.note(f"{where}{{}}")
                continue
            item = _prune(v, inner, f"{where}.{k}", dropped)
            out_map[k] = _identifiers_only(item, f"{where}.{k}", dropped)
        return out_map
    # A scalar: str, int, float, bool, date, datetime or one of a Literal's values.
    if _fits(value, annotation):
        return value
    dropped.note(where)
    return None


def _identifiers_only(value: Any, where: str, dropped: _Dropped) -> Any:
    """Text inside a free-form map must be an identifier; lists of them are kept."""
    if isinstance(value, str) and not _IDENTIFIER.match(value):
        dropped.note(where)
        return None
    if isinstance(value, list):
        kept = [v for v in value if not isinstance(v, str) or _IDENTIFIER.match(v)]
        if len(kept) != len(value):
            dropped.note(where)
        return kept
    return value


def prune(data: Any, model: type[BaseModel], label: str = "") -> Any:
    """`data` with only the fields `model` declares."""
    dropped = _Dropped()
    out = _prune(data, model, "$", dropped)
    if dropped:
        logger.warning(
            "dropped fields the contract does not name (%s): %s",
            label or model.__name__,
            ", ".join(dropped[:20]) + (" ..." if len(dropped) > 20 else ""),
        )
    return out
