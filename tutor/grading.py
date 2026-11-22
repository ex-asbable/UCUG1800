import re
import unicodedata

from sympy import Poly, Rational, Symbol


TOKEN = re.compile(r"\\(?:frac|dfrac|tfrac)|(?:\d+(?:\.\d+)?|\.\d+)|[a-zA-Z+*/^=(){}-]")
SYMBOLS = {name: Symbol(name) for name in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"}
GROUPS = {"(": ")", "{": "}"}
MAX_DEGREE = 6


class UnsupportedMath(ValueError):
    pass


class TexParser:
    def __init__(self, source: str):
        if len(source) > 160:
            raise UnsupportedMath()
        cleaned = re.sub(r"\s+|\\(?:left|right|[,;!])", "", source.strip().strip("$"))
        cleaned = cleaned.replace(r"\cdot", "*").replace(r"\times", "*").replace("−", "-")
        self.tokens = TOKEN.findall(cleaned)
        variables = set(self.tokens).intersection(SYMBOLS)
        if "".join(self.tokens) != cleaned or not self.tokens or len(self.tokens) > 72 or len(variables) > 3:
            raise UnsupportedMath()
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else ""

    def take(self):
        token = self.peek()
        if not token:
            raise UnsupportedMath()
        self.index += 1
        return token

    def parse(self):
        left = self.sum()
        if self.peek() == "=":
            self.take()
            right = self.sum()
            left = ("equation", left - right)
        else:
            left = ("expression", left)
        if self.peek():
            raise UnsupportedMath()
        return left

    def sum(self):
        value = self.product()
        while self.peek() in {"+", "-"}:
            operator = self.take()
            term = self.product()
            value = value + term if operator == "+" else value - term
            self.check_size(value)
        return value

    def product(self):
        value = self.unary()
        while (token := self.peek()) and (token in {"*", "/"} or self.is_atom(token)):
            if token == "/":
                self.take()
                value = self.divide(value, self.unary())
                continue
            if token == "*":
                self.take()
            value *= self.unary()
            if value.total_degree() > MAX_DEGREE:
                raise UnsupportedMath()
            self.check_size(value)
        return value

    def unary(self):
        if self.peek() in {"+", "-"}:
            return self.unary() if self.take() == "+" else -self.unary()
        value = self.atom()
        if self.peek() == "^":
            self.take()
            exponent = self.atom()
            if not exponent.is_ground:
                raise UnsupportedMath()
            power = exponent.LC()
            if not power.is_Integer or not 0 <= power <= MAX_DEGREE or value.total_degree() * power > MAX_DEGREE:
                raise UnsupportedMath()
            value **= int(power)
            self.check_size(value)
        return value

    def group(self, start):
        if start not in GROUPS:
            raise UnsupportedMath()
        value = self.sum()
        if self.take() != GROUPS[start]:
            raise UnsupportedMath()
        return value

    def atom(self):
        token = self.take()
        if token in GROUPS:
            return self.group(token)
        if token.startswith("\\"):
            top = self.group(self.take())
            bottom = self.group(self.take())
            return self.divide(top, bottom)
        if token in SYMBOLS:
            return Poly(SYMBOLS[token], *SYMBOLS.values(), domain="QQ")
        if token[0].isdigit() or token[0] == ".":
            if len(token) > 12:
                raise UnsupportedMath()
            return Poly(Rational(token), *SYMBOLS.values(), domain="QQ")
        raise UnsupportedMath()

    @staticmethod
    def is_atom(token):
        return token in GROUPS or token in SYMBOLS or token[0].isdigit() or token[0] in ".\\"

    @staticmethod
    def divide(top, bottom):
        if not bottom.is_ground or bottom.is_zero:
            raise UnsupportedMath()
        result = top.quo_ground(bottom.LC())
        TexParser.check_size(result)
        return result

    @staticmethod
    def check_size(value):
        if any(max(int(coeff.p).bit_length(), int(coeff.q).bit_length()) > 512 for coeff in value.coeffs()):
            raise UnsupportedMath()


def tex_value(text: str):
    kind, polynomial = TexParser(text).parse()
    if kind == "equation":
        symbols = {index for term in polynomial.monoms() for index, degree in enumerate(term) if degree}
        if polynomial.total_degree() != 1 or len(symbols) != 1:
            raise UnsupportedMath()
        polynomial = polynomial.monic()
    return kind, polynomial


def normalize_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text).strip().casefold()
    return " ".join(cleaned.strip(".!?。！？").split())


def match_tex(value: str, accepted: list[str]) -> bool | None:
    try:
        result = tex_value(value)
    except (UnsupportedMath, ValueError, ZeroDivisionError):
        return None
    return any(result == tex_value(answer) for answer in accepted)
