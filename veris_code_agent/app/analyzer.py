"""
analyzer.py -- Static + Runtime code analysis utilities

Layer 1: AST-based static analysis (no execution needed)
Layer 2: Runtime analysis with subprocess timeout (catches actual infinite loops)
"""

import ast
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Layer 1: Static AST analysis
# ---------------------------------------------------------------------------

def _check_infinite_loops(tree: ast.AST) -> list[dict]:
    """Detect while True loops with no break or return inside."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue
        # Check if condition is True-ish
        is_infinite = (
            (isinstance(node.test, ast.Constant) and node.test.value is True)
            or (isinstance(node.test, ast.Name) and node.test.id == "True")
        )
        if not is_infinite:
            continue
        # Check if there's a break or return anywhere in the body
        has_exit = any(
            isinstance(n, (ast.Break, ast.Return))
            for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
        )
        if not has_exit:
            issues.append({
                "line":     node.lineno,
                "type":     "infinite_loop",
                "severity": "CRITICAL",
                "message":  "while True with no break or return -- execution will never terminate",
                "fix":      "Add a break condition or convert to a for-loop with a bounded range",
            })
    return issues


def _check_bare_excepts(tree: ast.AST) -> list[dict]:
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            issues.append({
                "line":     node.lineno,
                "type":     "bare_except",
                "severity": "HIGH",
                "message":  "Bare `except:` catches all exceptions including KeyboardInterrupt and SystemExit",
                "fix":      "Catch specific exceptions: `except (ValueError, TypeError):`",
            })
    return issues


def _check_mutable_defaults(tree: ast.AST) -> list[dict]:
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                issues.append({
                    "line":     node.lineno,
                    "type":     "mutable_default",
                    "severity": "MEDIUM",
                    "message":  f"Function `{node.name}` has a mutable default argument -- shared across all calls",
                    "fix":      "Use `None` as default and initialise inside the function body",
                })
    return issues


def _check_unbounded_index(tree: ast.AST) -> list[dict]:
    """Simple heuristic: range(len(x) + N) for N > 0 is almost always wrong."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "range"):
            continue
        if len(node.args) != 1:
            continue
        arg = node.args[0]
        if (
            isinstance(arg, ast.BinOp)
            and isinstance(arg.op, ast.Add)
            and isinstance(arg.left, ast.Call)
            and isinstance(arg.left.func, ast.Name)
            and arg.left.func.id == "len"
            and isinstance(arg.right, ast.Constant)
            and isinstance(arg.right.value, int)
            and arg.right.value > 0
        ):
            issues.append({
                "line":     node.lineno,
                "type":     "off_by_one",
                "severity": "HIGH",
                "message":  f"range(len(x) + {arg.right.value}) will produce out-of-bounds index access",
                "fix":      "Use range(len(x)) or range(len(x) - 1) depending on intent",
            })
    return issues


def _check_unclosed_files(tree: ast.AST) -> list[dict]:
    """Flag open() calls not used inside a `with` statement."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            continue   # with-blocks are fine
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if isinstance(call.func, ast.Name) and call.func.id == "open":
            issues.append({
                "line":     node.lineno,
                "type":     "resource_leak",
                "severity": "MEDIUM",
                "message":  "open() called without a `with` statement -- file may not be closed on error",
                "fix":      "Use `with open(...) as f:` to guarantee the file is closed",
            })
    return issues


def _check_no_base_case(tree: ast.AST) -> list[dict]:
    """Flag recursive functions with no obvious base case (no `if` + `return`)."""
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        name = node.name
        # Check if function calls itself
        calls_self = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == name
            for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
        )
        if not calls_self:
            continue
        # Check if there's at least one return inside an if-block
        has_base_case = any(
            isinstance(n, ast.If)
            for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
        )
        if not has_base_case:
            issues.append({
                "line":     node.lineno,
                "type":     "infinite_recursion",
                "severity": "CRITICAL",
                "message":  f"Recursive function `{name}` has no base case -- will hit RecursionError",
                "fix":      "Add an `if` condition that returns without recursing",
            })
    return issues


def static_analysis(code: str) -> list[dict]:
    """Run all AST checks and return a deduplicated list of issues."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [{
            "line":     e.lineno or 0,
            "type":     "syntax_error",
            "severity": "CRITICAL",
            "message":  f"Syntax error: {e.msg}",
            "fix":      "Fix the syntax before running further analysis",
        }]

    issues: list[dict] = []
    issues += _check_infinite_loops(tree)
    issues += _check_bare_excepts(tree)
    issues += _check_mutable_defaults(tree)
    issues += _check_unbounded_index(tree)
    issues += _check_unclosed_files(tree)
    issues += _check_no_base_case(tree)

    # Sort by line number
    return sorted(issues, key=lambda x: x["line"])


# ---------------------------------------------------------------------------
# Layer 2: Runtime analysis (subprocess with timeout)
# ---------------------------------------------------------------------------

def runtime_analysis(code: str, timeout_seconds: int = 5) -> dict:
    """
    Execute the code in a subprocess with a hard timeout.
    Returns {"timed_out": bool, "returncode": int, "stdout": str, "stderr": str}
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "timed_out":  False,
            "returncode": result.returncode,
            "stdout":     result.stdout[:500],
            "stderr":     result.stderr[:500],
        }
    except subprocess.TimeoutExpired:
        return {
            "timed_out":  True,
            "returncode": None,
            "stdout":     "",
            "stderr":     f"Execution timed out after {timeout_seconds}s -- likely infinite loop or infinite recursion",
        }
    except Exception as e:
        return {
            "timed_out":  False,
            "returncode": -1,
            "stdout":     "",
            "stderr":     str(e),
        }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}


def format_issues(issues: list[dict]) -> str:
    if not issues:
        return "✅ No static issues detected."
    lines = []
    for i in issues:
        emoji = SEVERITY_EMOJI.get(i["severity"], "⚪")
        lines.append(
            f"{emoji} Line {i['line']} [{i['severity']}] {i['message']}\n"
            f"   Fix: {i['fix']}"
        )
    return "\n\n".join(lines)


def format_runtime(rt: dict) -> str:
    if rt["timed_out"]:
        return f"⏱️  RUNTIME: Execution timed out -- {rt['stderr']}"
    if rt["returncode"] != 0:
        return f"💥 RUNTIME: Process exited with code {rt['returncode']}\n{rt['stderr']}"
    return f"✅ RUNTIME: Completed normally (exit 0)"
