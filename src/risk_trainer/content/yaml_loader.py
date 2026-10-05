"""Safe YAML loading that also rejects duplicate keys (PyYAML silently keeps the last one)."""

from collections.abc import Hashable

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.resolver import BaseResolver


class _StrictSafeLoader(yaml.SafeLoader):
    """SafeLoader that raises on duplicate mapping keys. Only safe constructors are registered."""


def _construct_mapping(
    loader: _StrictSafeLoader, node: MappingNode, deep: bool = False
) -> dict[Hashable, object]:
    loader.flatten_mapping(node)
    seen: set[Hashable] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            raise ConstructorError(None, None, "found an unhashable key", key_node.start_mark)
        if key in seen:
            raise ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_StrictSafeLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml(text: str) -> object:
    """Parse one YAML document with safe constructors only. Raises yaml.YAMLError."""
    loader = _StrictSafeLoader(text)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()
