"""Dice expression engine: parse -> roll -> explain.

Grammar
-------
    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/') unary)*
    unary   := ('+' | '-')? atom
    atom    := NUMBER | dice | '(' expr ')'
    dice    := NUMBER? 'd' (NUMBER | '%') per_die?
    per_die := '(' ('+' | '-') NUMBER (('+' | '-') NUMBER)* ')'

Bonus rules (the whole point of this bot)
-----------------------------------------
    3d6+1       -> roll 3d6, sum, then +1 once (bonus to the final result)
    3d6(+1)     -> +1 to every die, then sum
    (3d6+1)     -> same as 3d6(+1): a +/- inside brackets belongs to each die

A bracket group folds into a per-die bonus only when it holds exactly one dice
term plus plain numbers; otherwise brackets are ordinary math grouping:

    (2d6+1d4)*2 -> normal grouping, nothing folded
    2d6(+1)-3   -> +1 per die, then -3 off the total

A per-die debuff never takes a die below 0: 2d4(-5) contributes 0, not -7.
Maths outside the dice is untouched, so a final -10 can still go negative.

Cyrillic dice notation is accepted too: 3k6 / 3d6 written with Russian letters.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from fractions import Fraction

MAX_EXPR_LEN = 200
MAX_DICE_PER_TERM = 200
MAX_TOTAL_DICE = 500
MAX_SIDES = 10_000
MAX_DEPTH = 16


class DiceError(ValueError):
    """Anything the user can fix: bad syntax, silly numbers, division by zero."""


# --- AST ---------------------------------------------------------------------


@dataclass
class Num:
    value: int


@dataclass
class Dice:
    count: int
    sides: int
    per_die: int = 0
    src: str = ""


@dataclass
class BinOp:
    op: str
    left: object
    right: object


@dataclass
class Neg:
    operand: object


# --- tokenizer ---------------------------------------------------------------

# Russian players often type the die with a Cyrillic letter: 3k6 / 3d6.
_CYRILLIC_D = str.maketrans({"к": "d", "К": "d", "д": "d", "Д": "d"})
_TOKEN_RE = re.compile(r"\d+|[dD]|%|[-+*/()]|\s+")


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise DiceError("I do not understand %r (position %d)" % (text[pos], pos + 1))
        raw = match.group()
        pos = match.end()
        if raw.isspace():
            continue
        if raw.isdigit():
            tokens.append(("num", raw))
        elif raw in "dD":
            tokens.append(("d", raw))
        elif raw == "%":
            tokens.append(("%", raw))
        else:
            tokens.append((raw, raw))
    return tokens


# --- parser ------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.total_dice = 0

    # -- token helpers
    def peek(self, offset: int = 0) -> tuple[str, str]:
        index = self.pos + offset
        return self.tokens[index] if index < len(self.tokens) else ("end", "")

    def take(self) -> tuple[str, str]:
        token = self.peek()
        self.pos += 1
        return token

    def accept(self, kind: str) -> bool:
        if self.peek()[0] == kind:
            self.pos += 1
            return True
        return False

    def expect(self, kind: str) -> tuple[str, str]:
        if self.peek()[0] != kind:
            found = self.peek()[1] or "end of expression"
            raise DiceError("expected %r but found %r" % (kind, found))
        return self.take()

    # -- grammar
    def parse(self) -> object:
        node = self.expr(depth=0)
        if self.peek()[0] != "end":
            raise DiceError("unexpected %r after a complete expression" % self.peek()[1])
        return node

    def expr(self, depth: int) -> object:
        node = self.term(depth)
        while self.peek()[0] in ("+", "-"):
            op = self.take()[0]
            node = BinOp(op, node, self.term(depth))
        return node

    def term(self, depth: int) -> object:
        node = self.unary(depth)
        while self.peek()[0] in ("*", "/"):
            op = self.take()[0]
            node = BinOp(op, node, self.unary(depth))
        return node

    def unary(self, depth: int) -> object:
        if self.accept("+"):
            return self.unary(depth)
        if self.accept("-"):
            return Neg(self.unary(depth))
        return self.atom(depth)

    def atom(self, depth: int) -> object:
        kind, raw = self.peek()
        if kind == "(":
            if depth >= MAX_DEPTH:
                raise DiceError("too many nested brackets")
            self.take()
            node = self.expr(depth + 1)
            self.expect(")")
            return _fold_per_die(node)
        if kind == "num":
            if self.peek(1)[0] == "d":
                self.take()
                self.take()
                return self.dice(count_text=raw)
            self.take()
            return Num(int(raw))
        if kind == "d":
            self.take()
            return self.dice(count_text="")
        raise DiceError("unexpected %r" % (raw or "end of expression"))

    def dice(self, count_text: str) -> Dice:
        kind, raw = self.peek()
        if kind == "num":
            self.take()
            sides_text, sides = raw, int(raw)
        elif kind == "%":
            self.take()
            sides_text, sides = "%", 100
        else:
            raise DiceError("a die needs a number of sides, like d20 or 3d6")

        count = int(count_text) if count_text else 1
        if count < 1:
            raise DiceError("roll at least one die")
        if count > MAX_DICE_PER_TERM:
            raise DiceError("at most %d dice in one term" % MAX_DICE_PER_TERM)
        if sides < 2:
            raise DiceError("a die needs at least 2 sides")
        if sides > MAX_SIDES:
            raise DiceError("at most %d sides per die" % MAX_SIDES)
        self.total_dice += count
        if self.total_dice > MAX_TOTAL_DICE:
            raise DiceError("at most %d dice per roll" % MAX_TOTAL_DICE)

        per_die = self.per_die_group()
        src = "%sd%s" % (count_text, sides_text)
        if per_die:
            src += "(%+d)" % per_die
        return Dice(count=count, sides=sides, per_die=per_die, src=src)

    def per_die_group(self) -> int:
        """Parse an attached (+1) / (-2+1) modifier, if there is one."""
        if self.peek()[0] != "(" or self.peek(1)[0] not in ("+", "-"):
            return 0
        self.take()
        total = 0
        while self.peek()[0] in ("+", "-"):
            sign = 1 if self.take()[0] == "+" else -1
            total += sign * int(self.expect("num")[1])
        self.expect(")")
        return total


def _flatten_sum(node: object, sign: int = 1) -> list[tuple[int, object]]:
    if isinstance(node, BinOp) and node.op in ("+", "-"):
        left = _flatten_sum(node.left, sign)
        right = _flatten_sum(node.right, sign if node.op == "+" else -sign)
        return left + right
    if isinstance(node, Neg):
        return _flatten_sum(node.operand, -sign)
    return [(sign, node)]


def _fold_per_die(node: object) -> object:
    """Turn (3d6+1) into 3d6(+1): a +/- in brackets modifies each die."""
    parts = _flatten_sum(node)
    dice = [(sign, item) for sign, item in parts if isinstance(item, Dice)]
    nums = [(sign, item) for sign, item in parts if isinstance(item, Num)]
    if len(dice) != 1 or len(dice) + len(nums) != len(parts):
        return node
    sign, die = dice[0]
    if sign != 1:
        return node
    bonus = sum(s * item.value for s, item in nums)
    if bonus == 0:
        return node
    per_die = die.per_die + bonus
    src = re.sub(r"\([-+][^()]*\)$", "", die.src)
    if per_die:
        src += "(%+d)" % per_die
    return Dice(count=die.count, sides=die.sides, per_die=per_die, src=src)


def parse(text: str) -> object:
    if len(text) > MAX_EXPR_LEN:
        raise DiceError("expression is longer than %d characters" % MAX_EXPR_LEN)
    tokens = _tokenize(text.translate(_CYRILLIC_D))
    if not tokens:
        raise DiceError("nothing to roll")
    return _Parser(tokens).parse()


# --- evaluation --------------------------------------------------------------


@dataclass
class DieTerm:
    """One dice term, as rolled."""

    src: str
    sides: int
    per_die: int
    faces: list[int]

    @property
    def modified(self) -> list[int]:
        """Each die after its own bonus/debuff. A die never falls below 0."""
        return [max(0, face + self.per_die) for face in self.faces]

    @property
    def floored(self) -> bool:
        """True when a debuff pushed at least one die below 0."""
        return any(face + self.per_die < 0 for face in self.faces)

    @property
    def total(self) -> int:
        return sum(self.modified)


@dataclass
class _Ev:
    value: Fraction
    text: str
    prec: int  # 0 = atom, 1 = +/-, 2 = */


def fmt_value(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return ("%.4f" % float(value)).rstrip("0").rstrip(".")


def _wrap(child: _Ev, needed: int, strict: bool = False) -> str:
    too_loose = child.prec < needed or (strict and child.prec == needed)
    return "(%s)" % child.text if child.prec and too_loose else child.text


def _eval(node: object, rng: random.Random, terms: list[DieTerm]) -> _Ev:
    if isinstance(node, Num):
        return _Ev(Fraction(node.value), str(node.value), 0)

    if isinstance(node, Dice):
        faces = [rng.randint(1, node.sides) for _ in range(node.count)]
        term = DieTerm(src=node.src, sides=node.sides, per_die=node.per_die, faces=faces)
        terms.append(term)
        return _Ev(Fraction(term.total), str(term.total), 0)

    if isinstance(node, Neg):
        inner = _eval(node.operand, rng, terms)
        return _Ev(-inner.value, "-%s" % _wrap(inner, 2), 2)

    if isinstance(node, BinOp):
        left = _eval(node.left, rng, terms)
        right = _eval(node.right, rng, terms)
        prec = 1 if node.op in ("+", "-") else 2
        if node.op == "+":
            value = left.value + right.value
        elif node.op == "-":
            value = left.value - right.value
        elif node.op == "*":
            value = left.value * right.value
        else:
            if right.value == 0:
                raise DiceError("division by zero")
            value = left.value / right.value
        text = "%s %s %s" % (
            _wrap(left, prec),
            node.op,
            _wrap(right, prec, strict=node.op in ("-", "/")),
        )
        return _Ev(value, text, prec)

    raise AssertionError("unknown node %r" % (node,))


@dataclass
class RollResult:
    source: str
    total: Fraction
    calc: str
    terms: list[DieTerm] = field(default_factory=list)

    @property
    def total_text(self) -> str:
        return fmt_value(self.total)

    def detail_lines(self) -> list[str]:
        """The full calculation path, one step per line."""
        lines = []
        for term in self.terms:
            rolled = ", ".join(str(face) for face in term.faces)
            if term.per_die:
                summed = " + ".join(str(value) for value in term.modified)
                note = "%+d each" % term.per_die
                if term.floored:
                    note += ", min 0"
                lines.append(
                    "%s: %s  (%s)  ->  %s = %d"
                    % (term.src, rolled, note, summed, term.total)
                )
            elif len(term.faces) == 1:
                lines.append("%s: %s" % (term.src, rolled))
            else:
                lines.append("%s: %s  ->  sum = %d" % (term.src, rolled, term.total))
        if self.calc != self.total_text:
            lines.append("%s = %s" % (self.calc, self.total_text))
        return lines


def roll(text: str, rng: random.Random | None = None) -> RollResult:
    """Parse and roll `text`. Raises DiceError on anything unusable."""
    node = parse(text)
    terms: list[DieTerm] = []
    evaluated = _eval(node, rng or random.SystemRandom(), terms)
    return RollResult(
        source=text.strip(),
        total=evaluated.value,
        calc=evaluated.text,
        terms=terms,
    )


def has_dice(text: str) -> bool:
    """Cheap gate: does this text hold something that looks like a die?"""
    return re.search(r"[dD]\s*(\d+|%)", text.translate(_CYRILLIC_D)) is not None


if __name__ == "__main__":
    # Try the engine without a bot token:  python dice.py "3d6(+1)+2"
    import sys

    try:
        outcome = roll(" ".join(sys.argv[1:]))
    except DiceError as error:
        sys.exit("error: %s" % error)
    print(outcome.total_text)
    for detail in outcome.detail_lines():
        print("  " + detail)
