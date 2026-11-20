"""Reading GitHub Actions workflows the way Actions does, for the workflow contracts."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

import yaml


class WorkflowLoader(yaml.SafeLoader):
    """YAML loader that preserves Actions' `on` key and rejects duplicates."""


for first_character, resolvers in deepcopy(WorkflowLoader.yaml_implicit_resolvers).items():
    WorkflowLoader.yaml_implicit_resolvers[first_character] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]

WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$"),
    list("tf"),
)


def _construct_mapping(
    loader: WorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                "workflow mapping keys must be strings",
                key_node.start_mark,
            )
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a workflow mapping",
                node.start_mark,
                f"duplicate key: {key}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


WorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def reads_secrets(workflow: object) -> bool:
    """Whether a parsed workflow references the secrets context anywhere.

    Searched in the parsed document rather than the file text: a comment saying
    "no secrets." in the frontend workflow failed the deploy gate on main while
    the workflow read none."""
    return "secrets." in json.dumps(workflow, default=str)
