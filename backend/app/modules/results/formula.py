"""Formulas de analitos calculados (misma gramatica que Vladimir, sin `eval`).

expr    := term (("+" | "-") term)*
term    := unary (("*" | "/") unary)*
unary   := ("+" | "-") unary | primary
primary := NUMBER | CODE | "(" expr ")"
CODE    := [A-Za-z_][A-Za-z0-9_]* | "{" cualquier caracter salvo llaves "}"
"""

import re

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<number>\d+(?:\.\d+)?)
      | (?P<code>[A-Za-z_][A-Za-z0-9_]*)
      | \{(?P<braced>[^{}]*)\}
      | (?P<op>[-+*/()])
    )
    """,
    re.VERBOSE,
)


class FormulaError(ValueError):
    """La formula no cumple la gramatica."""


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None or match.end() == pos:
            raise FormulaError(f"Caracter no valido en la posicion {pos}.")
        kind = match.lastgroup or ""
        value = match.group(kind)
        tokens.append(("code" if kind == "braced" else kind, value))
        pos = match.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise FormulaError("La formula termina de forma inesperada.")
        self.pos += 1
        return token

    def parse(self):
        node = self.expr()
        if self.peek() is not None:
            raise FormulaError("Sobran elementos al final de la formula.")
        return node

    def expr(self):
        node = self.term()
        while (t := self.peek()) and t[0] == "op" and t[1] in "+-":
            self.take()
            node = ("bin", t[1], node, self.term())
        return node

    def term(self):
        node = self.unary()
        while (t := self.peek()) and t[0] == "op" and t[1] in "*/":
            self.take()
            node = ("bin", t[1], node, self.unary())
        return node

    def unary(self):
        t = self.peek()
        if t and t[0] == "op" and t[1] in "+-":
            self.take()
            return ("neg", self.unary()) if t[1] == "-" else self.unary()
        return self.primary()

    def primary(self):
        kind, value = self.take()
        if kind == "number":
            return ("num", float(value))
        if kind == "code":
            if (nxt := self.peek()) and nxt == ("op", "("):
                raise FormulaError("No se admiten funciones.")
            return ("code", value)
        if kind == "op" and value == "(":
            node = self.expr()
            if self.take() != ("op", ")"):
                raise FormulaError("Falta cerrar un parentesis.")
            return node
        raise FormulaError(f"Elemento inesperado: {value!r}.")


def _parse(formula: str):
    return _Parser(_tokenize(formula)).parse()


def _codes(node, out: list[str]) -> None:
    if node[0] == "code":
        if node[1] not in out:
            out.append(node[1])
    elif node[0] == "neg":
        _codes(node[1], out)
    elif node[0] == "bin":
        _codes(node[2], out)
        _codes(node[3], out)


def formula_codes(formula: str) -> list[str]:
    """Codigos de analito referenciados, en orden de aparicion y sin repetir."""
    out: list[str] = []
    _codes(_parse(formula), out)
    return out


def _eval(node, values: dict[str, float]) -> float | None:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "code":
        return values.get(node[1])
    if kind == "neg":
        inner = _eval(node[1], values)
        return None if inner is None else -inner
    left, right = _eval(node[2], values), _eval(node[3], values)
    if left is None or right is None:
        return None
    op = node[1]
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    return None if right == 0 else left / right


def evaluate_formula(formula: str, values: dict[str, float]) -> float | None:
    """Valor de la formula, o `None` si falta un analito o hay division por cero."""
    return _eval(_parse(formula), values)
