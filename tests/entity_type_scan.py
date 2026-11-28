"""What `src/stoa` writes, read from the source: entity types and their fields.

Used by the data type catalog gates (`test_data_catalog`, #587); the deletion
branch gate (#534) that shared it went with the branches (#642).

- `written_entity_types` collects every `entity_type` a row can be written
  with: the value under an `"entity_type"` key of a dict literal, an
  `entity_type=` keyword argument, and the value an update sets with
  `SET entity_type = :x`. A name or `module.NAME` is resolved to the string it
  stands for, and `a if c else b` to both. A writer whose value it cannot
  resolve (an f-string, a parameter) is returned as unresolved.
- `written_fields` collects, for each entity type, the attribute names its
  writers put next to it: the other keys of that dict literal (and of a
  `metadata` dict literal inside it, as `metadata.<key>`), the keys of a
  `**spread` of a dict the same function builds, the other keywords of the
  call, and the attributes the `SET` of that update expression sets. A spread
  it cannot follow (a parameter, a call) makes the writer opaque: its fields
  have to be read by hand.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

type Function = ast.FunctionDef | ast.AsyncFunctionDef

# `SET entity_type = :entity` (or `#entity_type`, or `if_not_exists(...)`) in an
# update expression; a condition (`... AND entity_type = :entity`) only reads it.
_SET_ENTITY = re.compile(
    r"(?:\bSET\b|,)\s*#?entity_type\s*=\s*"
    r"(?:if_not_exists\(\s*#?entity_type\s*,\s*)?(:\w+)"
)
# The attributes an update expression's SET clause sets: `SET a = :x, #b = ...`.
_SET_CLAUSE = re.compile(r"\bSET\b(.*?)(?:\bREMOVE\b|\bADD\b|\bDELETE\b|$)", re.DOTALL)
_SET_TARGET = re.compile(r"(?:^|,)\s*(#?\w+)\s*=")
# An `ADD` clause's attributes: `ADD hits :one, other :two`.
_ADD_CLAUSE = re.compile(r"\bADD\b(.*?)(?:\bREMOVE\b|\bSET\b|\bDELETE\b|$)", re.DOTALL)
_ADD_TARGET = re.compile(r"(?:^|,)\s*(#?\w+)\s+:")


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root / "src").with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class Modules:
    """The modules under `src/stoa`: their trees, string constants and imports."""

    def __init__(self, root: Path) -> None:
        self.trees: dict[str, tuple[str, ast.Module]] = {}
        self.constants: dict[str, dict[str, str]] = {}
        self.imports: dict[str, dict[str, tuple[str, str | None]]] = {}
        for path in sorted((root / "src" / "stoa").rglob("*.py")):
            name = _module_name(root, path)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.trees[name] = (path.relative_to(root).as_posix(), tree)
            constants: dict[str, str] = {}
            imports: dict[str, tuple[str, str | None]] = {}
            self.constants[name] = constants
            self.imports[name] = imports
            package = name.split(".") if path.name == "__init__.py" else name.split(".")[:-1]
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    value = node.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        for target in targets:
                            if isinstance(target, ast.Name):
                                constants[target.id] = value.value
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        stem = package[: len(package) - node.level + 1]
                        base = ".".join([*stem, *([node.module] if node.module else [])])
                    for alias in node.names:
                        imports[alias.asname or alias.name] = (base, alias.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports[alias.asname or alias.name] = (alias.name, None)

    def resolve_all(self, module: str, node: ast.expr) -> set[str] | None:
        """The strings `node` can stand for (both arms of `a if c else b`), or None."""
        if isinstance(node, ast.IfExp):
            body = self.resolve_all(module, node.body)
            orelse = self.resolve_all(module, node.orelse)
            return None if body is None or orelse is None else body | orelse
        value = self._resolve(module, node)
        return None if value is None else {value}

    def _resolve(self, module: str, node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in self.constants[module]:
                return self.constants[module][node.id]
            source = self.imports[module].get(node.id)
            if source and source[1] and source[0] in self.constants:
                return self.constants[source[0]].get(source[1])
            return None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            source = self.imports[module].get(node.value.id)
            if source:
                target = source[0] if source[1] is None else f"{source[0]}.{source[1]}"
                if target in self.constants:
                    return self.constants[target].get(node.attr)
        return None


@dataclass
class _Write:
    """One place a scope writes an `entity_type`, and what it writes beside it."""

    value: ast.expr
    fields: set[str] = field(default_factory=set)
    opaque: list[str] = field(default_factory=list)


def _local_dicts(scope: ast.AST) -> dict[str, list[ast.expr]]:
    """Every value a name in `scope` is assigned (`x = ...`, `x: T = ...`)."""
    found: dict[str, list[ast.expr]] = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                found.setdefault(node.target.id, []).append(node.value)
    return found


def _added_keys(scope: ast.AST, name: str) -> set[str]:
    """Keys `scope` adds to the dict `name` later: `name["k"] = v`, `name.update(...)`."""
    keys: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == name
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    keys.add(target.slice.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
        ):
            keys.update(keyword.arg for keyword in node.keywords if keyword.arg)
            for argument in node.args:
                if isinstance(argument, ast.Dict):
                    keys.update(
                        key.value
                        for key in argument.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    )
    return keys


def _is_key_call(node: ast.expr) -> bool:
    """A call to a key builder (`record_key(...)`, `repo.pointer_key(...)`): PK and SK only."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:
        return False
    return name.endswith(("key", "_KEY")) or name in {"key", "_key"}


def _dict_fields(
    node: ast.Dict, scope: ast.AST, locals_: dict[str, list[ast.expr]], depth: int = 0
) -> tuple[set[str], list[str]]:
    fields: set[str] = set()
    opaque: list[str] = []
    for key, value in zip(node.keys, node.values, strict=True):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            fields.add(key.value)
            if key.value == "metadata" and isinstance(value, ast.Dict):
                inner, _ = _dict_fields(value, scope, locals_, depth + 1)
                fields.update(f"metadata.{name}" for name in inner)
        elif key is None:
            more, hidden = _spread_fields(value, scope, locals_, depth)
            fields |= more
            opaque += hidden
        else:
            opaque.append(ast.unparse(key))
    return fields, opaque


def _spread_fields(
    value: ast.expr, scope: ast.AST, locals_: dict[str, list[ast.expr]], depth: int
) -> tuple[set[str], list[str]]:
    """The keys a `**value` spread adds, as far as the scope shows them."""
    if depth > 3:
        return set(), [ast.unparse(value)]
    if _is_key_call(value) or (isinstance(value, ast.Name) and value.id.upper() == value.id):
        return set(), []  # a key, or a module-level key constant
    if isinstance(value, ast.Dict):
        return _dict_fields(value, scope, locals_, depth + 1)
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "dict"
        and len(value.args) <= 1
    ):
        named = {keyword.arg for keyword in value.keywords if keyword.arg}
        if not value.args:
            return named, []
        copied, copied_hidden = _spread_fields(value.args[0], scope, locals_, depth + 1)
        return named | copied, copied_hidden
    if isinstance(value, ast.IfExp):
        body, body_hidden = _spread_fields(value.body, scope, locals_, depth + 1)
        orelse, else_hidden = _spread_fields(value.orelse, scope, locals_, depth + 1)
        return body | orelse, body_hidden + else_hidden
    if isinstance(value, ast.Name) and value.id in locals_:
        fields: set[str] = set(_added_keys(scope, value.id))
        hidden: list[str] = []
        for assigned in locals_[value.id]:
            more, opaque = _spread_fields(assigned, scope, locals_, depth + 1)
            fields |= more
            hidden += opaque
        return fields, hidden
    return set(), [ast.unparse(value)]


def _update_fields(text: str, names: dict[str, str]) -> set[str]:
    fields: set[str] = set()
    for clause, target in ((_SET_CLAUSE, _SET_TARGET), (_ADD_CLAUSE, _ADD_TARGET)):
        for body in clause.findall(text):
            for name in target.findall(body):
                fields.add(names.get(name, name.lstrip("#")))
    return fields


def _writes(scope: ast.AST) -> Iterator[_Write]:
    """Every place `scope` writes an `entity_type`, with what it writes beside it."""
    locals_ = _local_dicts(scope)
    # A dict literal assigned to a name can be added to later (`item.update(...)`).
    assigned = {
        id(value): name for name, values in locals_.items() for value in values
    }
    placeholders: dict[str, str] = {}
    for node in ast.walk(scope):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "entity_type":
                    fields, opaque = _dict_fields(node, scope, locals_)
                    if id(node) in assigned:
                        fields |= _added_keys(scope, assigned[id(node)])
                    yield _Write(value, fields - {"entity_type"}, opaque)
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "entity_type":
                    fields = {other.arg for other in node.keywords if other.arg}
                    hidden = [ast.unparse(other.value) for other in node.keywords if not other.arg]
                    yield _Write(keyword.value, fields - {"entity_type"}, hidden)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for placeholder in _SET_ENTITY.findall(node.value):
                placeholders[placeholder] = node.value
    if placeholders:
        names: dict[str, str] = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value.startswith("#")
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        names[key.value] = value.value
        for node in ast.walk(scope):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in placeholders:
                        text = placeholders[key.value]
                        yield _Write(value, _update_fields(text, names) - {"entity_type"})


def _scopes(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    functions: list[Function] = [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    # A function nested in another is read as part of the outer one.
    nested = {
        id(inner)
        for function in functions
        for inner in ast.walk(function)
        if inner is not function and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Module level too (a counter kind declared as a constant).
    top = ast.Module(
        body=[
            node
            for node in tree.body
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ],
        type_ignores=[],
    )
    scopes: list[tuple[str, ast.AST]] = [("<module>", top)]
    scopes.extend((f.name, f) for f in functions if id(f) not in nested)
    return scopes


@dataclass
class WrittenFields:
    """What the writers of one entity type put beside it."""

    fields: set[str] = field(default_factory=set)
    # `file::function` -> the spreads it could not follow.
    opaque: dict[str, list[str]] = field(default_factory=dict)


def _scan(root: Path) -> tuple[dict[str, set[str]], set[str], dict[str, WrittenFields]]:
    modules = Modules(root)
    found: dict[str, set[str]] = {}
    unresolved: set[str] = set()
    fields: dict[str, WrittenFields] = {}
    for module, (relative, tree) in modules.trees.items():
        for name, scope in _scopes(tree):
            writer = f"{relative}::{name}"
            for write in _writes(scope):
                resolved = modules.resolve_all(module, write.value)
                if resolved is None:
                    unresolved.add(writer)
                for entity_type in resolved or ():
                    found.setdefault(entity_type, set()).add(writer)
                    entry = fields.setdefault(entity_type, WrittenFields())
                    entry.fields |= write.fields
                    if write.opaque:
                        entry.opaque.setdefault(writer, []).extend(write.opaque)
    return found, unresolved, fields


def written_entity_types(root: Path = ROOT) -> tuple[dict[str, set[str]], set[str]]:
    """`entity_type` -> its writers (`file::function`); and the unresolved writers."""
    found, unresolved, _ = _scan(root)
    return found, unresolved


def written_fields(root: Path = ROOT) -> dict[str, WrittenFields]:
    """`entity_type` -> the attributes its writers put beside it, and what they hide."""
    return _scan(root)[2]
