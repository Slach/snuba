from __future__ import annotations

from typing import Any

TYPE_STRING = {"type": "string"}
TYPE_STRING_ARRAY = {"type": "array", "items": TYPE_STRING}
TYPE_NULLABLE_INTEGER = {"type": ["integer", "null"]}
TYPE_NULLABLE_STRING = {"type": ["string", "null"]}

FUNCTION_CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "type": TYPE_STRING,
        "args": TYPE_STRING_ARRAY,
    },
    "additionalProperties": False,
}

STREAM_LOADER_SCHEMA = {
    "type": "object",
    "properties": {
        "processor": TYPE_STRING,
        "default_topic": TYPE_STRING,
        "commit_log_topic": TYPE_NULLABLE_STRING,
        "subscription_scheduled_topic": TYPE_NULLABLE_STRING,
        "subscription_scheduler_mode": TYPE_NULLABLE_STRING,
        "subscription_result_topic": TYPE_NULLABLE_STRING,
        "replacement_topic": TYPE_NULLABLE_STRING,
        "pre_filter": FUNCTION_CALL_SCHEMA,
        "dlq_policy": FUNCTION_CALL_SCHEMA,
    },
    "additionalProperties": False,
}

NULLABLE_DISALLOWED_AGGREGATIONS_SCHEMA = {
    "type": ["array", "null"],
    "items": TYPE_STRING,
}

######
# Column specific json schemas
def make_column_schema(
    column_type: dict[str, Any], args: dict[str, Any]
) -> dict[str, Any]:
    args["properties"]["schema_modifiers"] = TYPE_STRING_ARRAY
    return {
        "type": "object",
        "properties": {
            "name": TYPE_STRING,
            "type": column_type,
            "args": args,
        },
        "additionalProperties": False,
    }


NUMBER_SCHEMA = make_column_schema(
    column_type={"enum": ["UInt", "Float"]},
    args={
        "type": "object",
        "properties": {
            "size": {"type": "number"},
        },
        "additionalProperties": False,
    },
)


NO_ARG_SCHEMA = make_column_schema(
    column_type={"enum": ["String", "DateTime"]},
    args={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)


ARRAY_SCHEMA = make_column_schema(
    column_type={"const": "Array"},
    args={
        "type": "object",
        "properties": {
            "type": TYPE_STRING,
            "arg": {"type": "number"},
        },
        "additionalProperties": False,
    },
)

AGGREGATE_FUNCTION_SCHEMA = make_column_schema(
    column_type={"const": "AggregateFunction"},
    args={
        "type": "object",
        "properties": {
            "func": TYPE_STRING,
            "arg_types": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"enum": ["Float", "UUID", "UInt"]},
                        "arg": {"type": ["number", "null"]},
                    },
                    "additionalProperties": False,
                },
            },
        },
        "additionalProperties": False,
    },
)

COLUMN_TYPES = [
    NUMBER_SCHEMA,
    NO_ARG_SCHEMA,
    ARRAY_SCHEMA,
    AGGREGATE_FUNCTION_SCHEMA,
]

NESTED_SCHEMA = make_column_schema(
    column_type={"const": "Nested"},
    args={
        "type": "object",
        "properties": {
            "subcolumns": {"type": "array", "items": {"anyOf": COLUMN_TYPES}}
        },
        "additionalProperties": False,
    },
)

SCHEMA_COLUMNS = {"type": "array", "items": {"anyOf": [*COLUMN_TYPES, NESTED_SCHEMA]}}

SCHEMA_SCHEMA = {
    "type": "object",
    "properties": {
        "columns": SCHEMA_COLUMNS,
        "local_table_name": TYPE_STRING,
        "dist_table_name": TYPE_STRING,
    },
    "additionalProperties": False,
}
######

STORAGE_SCHEMA = {
    "type": "object",
    "properties": {"key": TYPE_STRING, "set_key": TYPE_STRING},
    "additionalProperties": False,
}

STORAGE_QUERY_PROCESSORS_SCHEMA = TYPE_STRING_ARRAY

ENTITY_QUERY_PROCESSOR = {
    "type": "object",
    "properties": {
        "processor": TYPE_STRING,
        "args": {"type": "object"},  # args are a flexible dict
    },
    "required": ["processor"],
    "additionalProperties": False,
}

ENTITY_VALIDATOR = {
    "type": "object",
    "properties": {
        "validator": TYPE_STRING,
        "args": {"type": "object"},  # args are a flexible dict
    },
    "required": ["validator"],
    "additionalProperties": False,
}

ENTITY_TRANSLATION_MAPPER_SUB_LIST = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "mapper": TYPE_STRING,
            "args": {"type": "object"},
        },
        "required": ["mapper"],
        "additionalProperties": False,
    },
}

ENTITY_TRANSLATION_MAPPERS = {
    "type": "object",
    "properties": {
        "functions": ENTITY_TRANSLATION_MAPPER_SUB_LIST,
        "curried_functions": ENTITY_TRANSLATION_MAPPER_SUB_LIST,
        "subscriptables": ENTITY_TRANSLATION_MAPPER_SUB_LIST,
    },
    "additionalProperties": False,
}

# Full schemas:

V1_WRITABLE_STORAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "writable_storage"},
        "name": TYPE_STRING,
        "storage": STORAGE_SCHEMA,
        "schema": SCHEMA_SCHEMA,
        "query_processors": STORAGE_QUERY_PROCESSORS_SCHEMA,
        "stream_loader": STREAM_LOADER_SCHEMA,
    },
    "required": [
        "version",
        "kind",
        "name",
        "storage",
        "schema",
        "stream_loader",
    ],
    "additionalProperties": False,
}


V1_READABLE_STORAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "readable_storage"},
        "name": TYPE_STRING,
        "storage": STORAGE_SCHEMA,
        "schema": SCHEMA_SCHEMA,
        "query_processors": STORAGE_QUERY_PROCESSORS_SCHEMA,
    },
    "required": [
        "version",
        "kind",
        "name",
        "storage",
        "schema",
    ],
    "additionalProperties": False,
}

V1_ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "entity"},
        "schema": SCHEMA_COLUMNS,
        "name": TYPE_STRING,
        "readable_storage": TYPE_STRING,
        "writable_storage": TYPE_NULLABLE_STRING,
        "query_processors": {"type": "array", "items": ENTITY_QUERY_PROCESSOR},
        "translation_mappers": ENTITY_TRANSLATION_MAPPERS,
        "validators": {"type": "array", "items": ENTITY_VALIDATOR},
        "required_time_column": TYPE_STRING,
    },
    "required": [
        "version",
        "kind",
        "schema",
        "name",
        "readable_storage",
        "query_processors",
        "validators",
        "required_time_column",
    ],
    "additionalProperties": False,
}

V1_DATASET_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "dataset"},
        "name": TYPE_STRING,
        "is_experimental": {"type": "boolean"},
        "entities": {
            "type": "object",
            "properties": {"default": TYPE_STRING, "all": TYPE_STRING_ARRAY},
            "additionalProperties": False,
        },
    },
    "required": [
        "version",
        "kind",
        "name",
        "entities",
    ],
    "additionalProperties": False,
}

V1_ENTITY_SUBSCIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "entity_subscription"},
        "name": TYPE_STRING,
        "max_allowed_aggregations": TYPE_NULLABLE_INTEGER,
        "disallowed_aggregations": NULLABLE_DISALLOWED_AGGREGATIONS_SCHEMA,
    },
    "required": [
        "version",
        "kind",
        "name",
    ],
    "additionalProperties": False,
}


V1_MIGRATION_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"const": "v1"},
        "kind": {"const": "migration_group"},
        "name": TYPE_STRING,
        "optional": {"type": "boolean"},
        "migrations": {
            "type": "array",
            "items": TYPE_STRING,
        },
    },
    "required": ["name", "migrations"],
    "additionalProperties": False,
}

V1_ALL_SCHEMAS = {
    "dataset": V1_DATASET_SCHEMA,
    "entity": V1_ENTITY_SCHEMA,
    "entity_subscription": V1_ENTITY_SUBSCIPTION_SCHEMA,
    "readable_storage": V1_READABLE_STORAGE_SCHEMA,
    "writable_storage": V1_WRITABLE_STORAGE_SCHEMA,
    "migration_group": V1_MIGRATION_GROUP_SCHEMA,
}
