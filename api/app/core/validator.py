import json
from jsonschema import Draft202012Validator, ValidationError
from typing import Any, Dict

class SchemaValidator:
    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema
        self.validator = Draft202012Validator(schema)

    def validate(self, data: Dict[str, Any]):
        errors = sorted(self.validator.iter_errors(data), key=lambda e: e.path)
        return [
            {
                "path": list(e.path),
                "message": e.message,
                "validator": e.validator
            }
            for e in errors
        ]

    def get_schema(self) -> Dict[str, Any]:
        return self.schema
