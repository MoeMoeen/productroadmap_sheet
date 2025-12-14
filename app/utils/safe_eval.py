# productroadmap_sheet_project/app/utils/safe_eval.py

from __future__ import annotations

import ast
import time
from typing import Dict, List, Set


class SafeEvalError(Exception):
	"""Raised when a formula is invalid, unsafe, or fails during evaluation."""


SAFE_FUNCS = {"min": min, "max": max}


class _SafeExprValidator(ast.NodeVisitor):
	"""Validate that an expression contains only safe nodes."""

	allowed_bin_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
	allowed_unary_ops = (ast.UAdd, ast.USub)

	def visit_Call(self, node: ast.Call) -> None:
		if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCS:
			raise SafeEvalError("Disallowed function call")
		if node.keywords:
			raise SafeEvalError("Keyword arguments are not allowed")
		for arg in node.args:
			self.visit(arg)

	def visit_BinOp(self, node: ast.BinOp) -> None:
		if not isinstance(node.op, self.allowed_bin_ops):
			raise SafeEvalError("Disallowed binary operator")
		self.visit(node.left)
		self.visit(node.right)

	def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
		if not isinstance(node.op, self.allowed_unary_ops):
			raise SafeEvalError("Disallowed unary operator")
		self.visit(node.operand)

	def visit_Name(self, node: ast.Name) -> None:
		if not isinstance(node.ctx, ast.Load):
			return
		# Names are validated at runtime (env lookup); allow here.
		return

	def visit_Constant(self, node: ast.Constant) -> None:
		if not isinstance(node.value, (int, float)):
			raise SafeEvalError("Only numeric constants are allowed")

	# Block everything else
	def generic_visit(self, node: ast.AST) -> None:
		allowed = (ast.Expression,)
		if isinstance(node, allowed):
			super().generic_visit(node)
			return
		raise SafeEvalError(f"Disallowed syntax: {type(node).__name__}")


def extract_identifiers(formula_text: str) -> List[str]:
	"""Return input variable names (identifiers used on RHS) from a script."""

	tree = ast.parse(formula_text or "")
	assigned: Set[str] = set()
	used: List[str] = []

	# Collect assigned targets
	for stmt in tree.body:
		if isinstance(stmt, ast.Assign):
			for tgt in stmt.targets:
				if isinstance(tgt, ast.Name):
					assigned.add(tgt.id)

	# Collect RHS names (Load) that are not assigned and not safe funcs
	class _RhsVisitor(ast.NodeVisitor):
		def visit_Assign(self, node: ast.Assign) -> None:
			self.visit(node.value)

		def visit_Name(self, node: ast.Name) -> None:
			if isinstance(node.ctx, ast.Load):
				if node.id not in assigned and node.id not in SAFE_FUNCS:
					if node.id not in used:
						used.append(node.id)

		def generic_visit(self, node: ast.AST) -> None:
			super().generic_visit(node)

	_RhsVisitor().visit(tree)
	return used


def _validate_and_compile_expr(expr_src: str) -> ast.Expression:
	try:
		expr = ast.parse(expr_src, mode="eval")
	except SyntaxError as exc:
		raise SafeEvalError(f"Syntax error: {exc.msg}") from exc
	_SafeExprValidator().visit(expr)
	return expr


def evaluate_script(script: str, initial_env: Dict[str, float], timeout_secs: float = 5.0) -> Dict[str, float]:
	"""Safely evaluate a multi-line math model script.

	Each non-comment line must be `name = expression`. Returns the final env.
	Raises SafeEvalError on any unsafe construct, syntax error, or timeout.
	"""

	env: Dict[str, float] = dict(initial_env or {})
	start = time.time()
	lines = script.splitlines()
	safe_globals = {"__builtins__": {}, **SAFE_FUNCS}

	for raw in lines:
		if time.time() - start > timeout_secs:
			raise SafeEvalError("Evaluation timeout")
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		if "=" not in line:
			raise SafeEvalError("Each line must be an assignment")

		name_part, expr_part = line.split("=", 1)
		target = name_part.strip()
		expr_src = expr_part.strip()
		if not target:
			raise SafeEvalError("Missing assignment target")
		if not target.isidentifier():
			raise SafeEvalError("Invalid assignment target")

		expr_ast = _validate_and_compile_expr(expr_src)
		try:
			compiled = compile(expr_ast, filename="<formula>", mode="eval")
			result = eval(compiled, safe_globals, env)
		except Exception as exc:  # noqa: BLE001
			raise SafeEvalError(f"Evaluation error: {exc}") from exc

		env[target] = result

	return env


def validate_formula(script: str, max_lines: int = 10) -> List[str]:
	"""Validate script for length, syntax, and required `value` assignment."""

	errors: List[str] = []
	real_lines = [ln for ln in script.splitlines() if ln.strip() and not ln.strip().startswith("#")]
	if len(real_lines) > max_lines:
		errors.append(f"Formula exceeds {max_lines} lines ({len(real_lines)} lines found)")

	try:
		tree = ast.parse(script or "")
	except SyntaxError as exc:
		errors.append(f"Syntax error: {exc.msg}")
		return errors

	# Ensure only Assign statements are present and expressions are safe
	assigned: Set[str] = set()
	for stmt in tree.body:
		if not isinstance(stmt, ast.Assign):
			errors.append("Only assignment statements are allowed")
			continue
		if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
			errors.append("Assignment target must be a single name")
			continue
		assigned.add(stmt.targets[0].id)
		_SafeExprValidator().visit(ast.Expression(stmt.value))

	if "value" not in assigned:
		errors.append("Formula must assign 'value'")

	return errors
