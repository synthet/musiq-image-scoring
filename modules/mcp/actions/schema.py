"""JSON Schema validation for dispatch arguments."""

from __future__ import annotations

from typing import Any

from modules.mcp.actions.errors import ValidationError

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def validate_arguments(schema: dict[str, Any] | None, arguments: dict[str, Any]) -> dict[str, Any]:
    args = dict(arguments or {})
    if not schema:
        return args

    schema_type = schema.get("type")
    if schema_type == "object" and schema.get("additionalProperties") is False:
        allowed = set((schema.get("properties") or {}).keys())
        extra = set(args.keys()) - allowed
        if extra:
            raise ValidationError(
                f"Unexpected arguments: {', '.join(sorted(extra))}",
                details={"extra_keys": sorted(extra)},
            )

    required = schema.get("required") or []
    for key in required:
        if key not in args:
            raise ValidationError(f"Missing required argument: {key}", details={"missing": [key]})

    if _HAS_JSONSCHEMA:
        try:
            jsonschema.validate(instance=args, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValidationError(str(exc.message), details={"path": list(exc.path)}) from exc
        return args

    if schema_type == "object":
        props = schema.get("properties") or {}
        for key, spec in props.items():
            if key not in args:
                continue
            val = args[key]
            expected = spec.get("type")
            if expected == "boolean" and not isinstance(val, bool):
                raise ValidationError(f"{key} must be boolean")
            if expected == "integer" and not isinstance(val, int):
                raise ValidationError(f"{key} must be integer")
            if expected == "string" and not isinstance(val, str):
                raise ValidationError(f"{key} must be string")
            if "enum" in spec and val not in spec["enum"]:
                raise ValidationError(f"{key} must be one of {spec['enum']}")
            if expected == "integer":
                if "minimum" in spec and val < spec["minimum"]:
                    raise ValidationError(f"{key} below minimum")
                if "maximum" in spec and val > spec["maximum"]:
                    raise ValidationError(f"{key} above maximum")
    return args


def schema_arg_lists(schema: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    if not schema or schema.get("type") != "object":
        return [], []
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    all_keys = list(props.keys())
    req = [k for k in all_keys if k in required]
    opt = [k for k in all_keys if k not in required]
    return req, opt
