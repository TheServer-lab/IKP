#!/usr/bin/env python3
"""
ikp_core.py — shared utilities for IKP tools (fixed AST compatibility)

Provides:
- load_yaml_text / dump_yaml
- validate_ikp
- interpolate
- resolve_path (image resolution)
- safe_eval (AST-based evaluator for simple numeric & comparison expressions)
- execute_action(action, context)
"""

import yaml, re, os, ast

# -------------------------
# YAML helpers
# -------------------------
def load_yaml_text(text):
    try:
        return yaml.safe_load(text)
    except Exception as e:
        raise RuntimeError(f"YAML parse error: {e}")

def dump_yaml(data):
    return yaml.dump(data, sort_keys=False, allow_unicode=True)

# -------------------------
# Validation
# -------------------------
def validate_ikp(data):
    errors = []
    warnings = []
    if not isinstance(data, dict):
        errors.append("Root must be a mapping (YAML dictionary).")
        return errors, warnings
    if "scenes" not in data or not isinstance(data["scenes"], dict):
        errors.append("`scenes` must be a mapping with at least one scene.")
        return errors, warnings
    for sname, scene in data["scenes"].items():
        if not isinstance(scene, dict):
            errors.append(f"Scene '{sname}' must be a mapping/object.")
            continue
        ui = scene.get("ui")
        if ui is None:
            warnings.append(f"Scene '{sname}' has no `ui` list.")
            continue
        if not isinstance(ui, list):
            errors.append(f"Scene '{sname}': `ui` must be a list.")
            continue
        for i, item in enumerate(ui):
            if not isinstance(item, dict):
                errors.append(f"Scene '{sname}' ui[{i}] must be a mapping.")
                continue
            if "type" not in item:
                errors.append(f"Scene '{sname}' ui[{i}] missing required field 'type'.")
    return errors, warnings

# -------------------------
# Interpolation
# -------------------------
_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")

def _extract_var_value(v):
    try:
        if callable(v):
            try:
                return v()
            except TypeError:
                pass
        get = getattr(v, "get", None)
        if callable(get):
            try:
                return get()
            except TypeError:
                try:
                    return v.get("1.0", "end-1c")
                except Exception:
                    pass
        return v
    except Exception:
        try:
            return str(v)
        except Exception:
            return ""

def interpolate(text, vars_map):
    if not isinstance(text, str):
        return text
    def repl(m):
        key = m.group(1)
        v = vars_map.get(key)
        val = _extract_var_value(v)
        if val is None:
            return ""
        return str(val)
    return _VAR_PATTERN.sub(repl, text)

# -------------------------
# Path resolver
# -------------------------
def resolve_path(src, base_path):
    if not src:
        return None
    if os.path.isabs(src):
        return src
    return os.path.normpath(os.path.join(base_path or os.getcwd(), src))

# -------------------------
# Safe expression evaluator (AST-based)
# Supports numbers, booleans, comparisons, arithmetic, and simple boolean ops.
# Variables (names) are looked up in vars_map.
# -------------------------
# Build allowed node classes dynamically for compatibility across Python versions
_allowed_node_classes = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
    ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.List, ast.Tuple
}

# older Python versions have ast.Num / ast.Str nodes; include them if present
if hasattr(ast, "Num"):
    _allowed_node_classes.add(ast.Num)
if hasattr(ast, "Str"):
    _allowed_node_classes.add(ast.Str)
if hasattr(ast, "Bytes"):
    _allowed_node_classes.add(ast.Bytes)
if hasattr(ast, "NameConstant"):
    _allowed_node_classes.add(ast.NameConstant)

_ALLOWED_NODES = tuple(_allowed_node_classes)

def _check_node(node):
    if not isinstance(node, _ALLOWED_NODES):
        raise ValueError(f"Disallowed expression element: {type(node).__name__}")
    for child in ast.iter_child_nodes(node):
        _check_node(child)

def safe_eval(expr, vars_map):
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    expr = expr.strip()
    if expr == "":
        return False
    try:
        node = ast.parse(expr, mode='eval')
    except Exception as e:
        raise ValueError(f"Parse error: {e}")
    _check_node(node)
    safe_locals = {}
    for k, v in (vars_map or {}).items():
        try:
            if callable(v):
                val = v()
            else:
                val = v
        except Exception:
            val = v
        try:
            if isinstance(val, str):
                low = val.strip().lower()
                if low in ("true", "false"):
                    safe_locals[k] = low == "true"
                    continue
                try:
                    if '.' in val:
                        safe_locals[k] = float(val); continue
                    else:
                        safe_locals[k] = int(val); continue
                except Exception:
                    pass
            safe_locals[k] = val
        except Exception:
            safe_locals[k] = val
    try:
        code = compile(node, "<safe_eval>", "eval")
        return eval(code, {"__builtins__": None}, safe_locals)
    except Exception as e:
        raise ValueError(f"Evaluation error: {e}")

# -------------------------
# Action execution
# -------------------------
_LEGACY_SET_RE = re.compile(r'\s*set\(\s*([^,]+)\s*,\s*(.+)\s*\)\s*', re.I)
_LEGACY_PROGRESS_RE = re.compile(r'\s*progress\(\s*([^,]+)\s*,\s*([0-9\.\-]+)\s*\)\s*', re.I)
_LEGACY_GOTO_RE = re.compile(r'\s*goto\(\s*(.+)\s*\)\s*', re.I)

def execute_action(action, context):
    if not action:
        return
    if isinstance(action, str):
        m = _LEGACY_SET_RE.match(action)
        if m:
            k = m.group(1).strip()
            v = m.group(2).strip().strip('"').strip("'")
            setter = context.get("set_var")
            if setter:
                setter(k, v)
            return
        m = _LEGACY_PROGRESS_RE.match(action)
        if m:
            name = m.group(1).strip()
            val = float(m.group(2))
            setter = context.get("set_progress")
            if setter:
                setter(name, val)
            return
        m = _LEGACY_GOTO_RE.match(action)
        if m:
            target = m.group(1).strip()
            sh = context.get("show_scene")
            if sh:
                sh(target)
            return
        return
    if not isinstance(action, dict):
        return
    typ = action.get("type")
    if typ == "goto":
        target = action.get("target")
        if target and context.get("show_scene"):
            context["show_scene"](target)
    elif typ == "set":
        var = action.get("var")
        val = action.get("value")
        if isinstance(val, str):
            get_vars = context.get("get_vars")
            if get_vars:
                try:
                    val = interpolate(val, get_vars())
                except Exception:
                    pass
        setter = context.get("set_var")
        if setter and var is not None:
            setter(var, val)
    elif typ == "progress":
        target = action.get("target") or action.get("var")
        val = action.get("value", 0)
        if isinstance(val, str):
            get_vars = context.get("get_vars")
            if get_vars:
                try:
                    val = interpolate(val, get_vars())
                except Exception:
                    pass
        setter = context.get("set_progress")
        if setter and target:
            try:
                setter(target, float(val))
            except Exception:
                setter(target, val)
    elif typ == "if":
        cond = action.get("condition", "")
        get_vars = context.get("get_vars", lambda: {})
        vars_map = get_vars()
        try:
            cond_interp = interpolate(cond, vars_map)
        except Exception:
            cond_interp = cond
        try:
            ok = safe_eval(cond_interp, vars_map)
        except Exception:
            ok = False
        branch = action.get("then") if ok else action.get("else")
        if isinstance(branch, dict):
            execute_action(branch, context)
        elif isinstance(branch, list):
            for a in branch:
                execute_action(a, context)
    else:
        handler = context.get("handle_action")
        if callable(handler):
            handler(action)
