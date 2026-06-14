#!/usr/bin/env python3
"""
main_fixed.py

Educational round-robin homophonic substitution cipher.

Fixed version:
- generated mappings do NOT contain the plaintext letter as a visible prefix
- encryption is strict by default: unmapped cleartext characters are not copied
  to output accidentally
- mapping files remain simple text files:

    A -> 72, 5K, Q4
    B -> 8Z, HC, 3N
    SPACE -> 4R, 9M, TD
    DOT -> 2G, NV, W8

Run:
    python3 main_fixed.py gen-map 1.map --variants 3
    python3 main_fixed.py encrypt -m 1.map "spotkajmy sie dzisiaj"
    python3 main_fixed.py decrypt -m 1.map "...ciphertext..."
"""

from __future__ import annotations

import argparse
import itertools
import random
import string
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List


# Avoid 0/O and 1/I for child-friendly reading.
DEFAULT_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
DEFAULT_SEED = "letter-code-lab-v2"

SPECIAL_KEYS = {
    "SPACE": " ",
    "DOT": ".",
    "COMMA": ",",
    "QUESTION": "?",
    "EXCLAMATION": "!",
    "DASH": "-",
    "COLON": ":",
    "SEMICOLON": ";",
    "APOSTROPHE": "'",
    "QUOTE": '"',
    "SLASH": "/",
    "LPAREN": "(",
    "RPAREN": ")",
}

REVERSE_SPECIAL_KEYS = {value: key for key, value in SPECIAL_KEYS.items()}

# Characters not handled well by plain NFKD accent stripping.
# Polish letters are included explicitly.
ASCII_TRANSLATION = str.maketrans({
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ż": "z", "ź": "z",
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O", "Ś": "S", "Ż": "Z", "Ź": "Z",
    "ß": "ss", "ẞ": "SS",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ð": "d", "Ð": "D",
    "þ": "th", "Þ": "TH",
    "\n": " ",
    "[": "(","]": ")",
})


def normalize_to_ascii(text: str) -> str:
    """Convert national letters and accents to plain ASCII equivalents."""
    text = (text or "").translate(ASCII_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


# ---------------------------------------------------------------------------
# Mapping parsing and validation
# ---------------------------------------------------------------------------


def read_stdin_or_args(parts: List[str]) -> str:
    if parts:
        return " ".join(parts)
    return sys.stdin.read()


def key_to_plain_char(key: str) -> str:
    key = (key or "").strip()
    upper = key.upper()

    if upper in SPECIAL_KEYS:
        return SPECIAL_KEYS[upper]

    plain_char = upper
    if len(plain_char) != 1:
        raise ValueError(f"mapping key must be one character or special key, got {key!r}")
    return plain_char


def plain_char_to_key(ch: str) -> str:
    return REVERSE_SPECIAL_KEYS.get(ch, ch.upper())


def parse_mapping(path: str | Path) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    path = Path(path)

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if "#" in line:
            line = line.split("#", 1)[0].strip()

        if "->" in line:
            left, right = line.split("->", 1)
        elif "=" in line:
            left, right = line.split("=", 1)
        else:
            raise ValueError(f"{path}:{line_no}: expected 'A -> XX, YY'")

        plain_char = key_to_plain_char(left)
        tokens = [token.strip().upper() for token in right.split(",") if token.strip()]

        if not tokens:
            raise ValueError(f"{path}:{line_no}: no output tokens for {left.strip()!r}")

        mapping[plain_char] = tokens

    if not mapping:
        raise ValueError(f"{path}: empty mapping")

    validate_unique_tokens(mapping)
    return mapping


def validate_unique_tokens(mapping: Dict[str, List[str]]) -> None:
    owner: Dict[str, str] = {}
    for plain_char, tokens in mapping.items():
        for token in tokens:
            if token in owner and owner[token] != plain_char:
                raise ValueError(
                    f"token {token!r} is assigned to both "
                    f"{plain_char_to_key(owner[token])} and {plain_char_to_key(plain_char)}"
                )
            owner[token] = plain_char


def validate_prefix_free(mapping: Dict[str, List[str]]) -> None:
    tokens = [token for token_list in mapping.values() for token in token_list]

    for a in tokens:
        for b in tokens:
            if a != b and b.startswith(a):
                raise ValueError(
                    f"ambiguous mapping without separator: token {a!r} is a prefix of {b!r}. "
                    f"Use --sep or generate fixed-length tokens."
                )


# ---------------------------------------------------------------------------
# Cipher operations
# ---------------------------------------------------------------------------


def encrypt(text: str, mapping: Dict[str, List[str]], sep: str = "", strict: bool = True) -> str:
    counters = {plain_char: 0 for plain_char in mapping}
    out: List[str] = []

    for pos, ch in enumerate(text):
        key = ch.upper()

        if key in mapping:
            choices = mapping[key]
            idx = counters[key] % len(choices)
            out.append(choices[idx])
            counters[key] += 1
        elif strict:
            raise ValueError(
                f"unmapped plaintext character at position {pos}: {ch!r}. "
                f"Add it to the mapping or use --pass-unknown."
            )
        else:
            out.append(ch)

    return sep.join(out) if sep else "".join(out)


def build_reverse_mapping(mapping: Dict[str, List[str]]) -> Dict[str, str]:
    reverse: Dict[str, str] = {}
    for plain_char, tokens in mapping.items():
        for token in tokens:
            reverse[token] = plain_char
    return reverse


def decrypt(text: str, mapping: Dict[str, List[str]], sep: str = "", strict: bool = True) -> str:
    reverse = build_reverse_mapping(mapping)

    if sep:
        out: List[str] = []
        parts = text.split(sep)
        for idx, part in enumerate(parts):
            part = part.upper()
            if part in reverse:
                out.append(reverse[part])
            elif strict:
                raise ValueError(f"unknown ciphertext token #{idx + 1}: {part!r}")
            else:
                out.append(part)
        return "".join(out)

    validate_prefix_free(mapping)
    tokens_by_length = sorted(reverse, key=len, reverse=True)

    out: List[str] = []
    i = 0

    while i < len(text):
        matched = False
        for token in tokens_by_length:
            if text.upper().startswith(token, i):
                out.append(reverse[token])
                i += len(token)
                matched = True
                break

        if not matched:
            if strict:
                fragment = text[i : i + 12]
                raise ValueError(f"cannot parse ciphertext at offset {i}: {fragment!r}")
            out.append(text[i])
            i += 1

    return "".join(out)


# ---------------------------------------------------------------------------
# Safe mapping generation
# ---------------------------------------------------------------------------


def default_plain_symbols(include_punctuation: bool = True) -> List[str]:
    symbols = list(string.ascii_uppercase) + [" "]
    if include_punctuation:
        symbols.extend([".", ",", "?", "!", "-", ":", ";", "'", '"', "/", "(", ")"])
    return symbols


def make_code_pool(alphabet: str, token_len: int, seed: str) -> List[str]:
    alphabet = "".join(dict.fromkeys(alphabet.upper()))
    if len(alphabet) < 2:
        raise ValueError("code alphabet must contain at least two unique characters")
    if token_len < 1:
        raise ValueError("token length must be >= 1")

    pool = ["".join(chars) for chars in itertools.product(alphabet, repeat=token_len)]
    random.Random(seed).shuffle(pool)
    return pool


def pick_tokens_for_symbol(
    symbol: str,
    pool: List[str],
    used: set[str],
    variants: int,
) -> List[str]:
    chosen: List[str] = []
    plain_symbol = symbol.upper()

    for token in pool:
        if token in used:
            continue

        # Extra safety: for plaintext symbols that can also appear in the
        # ciphertext alphabet, do not put that same symbol inside its own token.
        # This avoids accidental visual leaks for both letters and digits.
        if plain_symbol and plain_symbol in token:
            continue

        chosen.append(token)
        used.add(token)

        if len(chosen) == variants:
            return chosen

    raise ValueError(
        f"not enough safe tokens for {plain_char_to_key(symbol)}. "
        f"Increase --token-len or use a larger --alphabet."
    )


def generate_mapping_text(
    variants: int = 3,
    alphabet: str = DEFAULT_CODE_ALPHABET,
    token_len: int = 2,
    seed: str = DEFAULT_SEED,
    include_punctuation: bool = True,
) -> str:
    symbols = default_plain_symbols(include_punctuation=include_punctuation)
    needed = len(symbols) * variants
    capacity = len(set(alphabet.upper())) ** token_len

    if capacity < needed:
        raise ValueError(
            f"not enough code tokens: need {needed}, capacity is {capacity}. "
            f"Increase --token-len or use a larger --alphabet."
        )

    pool = make_code_pool(alphabet=alphabet, token_len=token_len, seed=seed)
    used: set[str] = set()

    lines = [
        "# Safe generated mapping for main_fixed.py",
        "# No generated token intentionally contains its own plaintext letter.",
        "# Format: A -> XX, YY, ZZ",
        "",
    ]

    for symbol in symbols:
        tokens = pick_tokens_for_symbol(symbol, pool, used, variants)
        lines.append(f"{plain_char_to_key(symbol)} -> {', '.join(tokens)}")

    return "\n".join(lines) + "\n"


def generate_mapping_file(
    path: str | Path,
    variants: int = 3,
    alphabet: str = DEFAULT_CODE_ALPHABET,
    token_len: int = 2,
    seed: str = DEFAULT_SEED,
    include_punctuation: bool = True,
) -> None:
    text = generate_mapping_text(
        variants=variants,
        alphabet=alphabet,
        token_len=token_len,
        seed=seed,
        include_punctuation=include_punctuation,
    )
    Path(path).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe educational homophonic substitution cipher")
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("gen-map", help="generate a safe sample mapping file")
    gen.add_argument("mapping_file")
    gen.add_argument("--variants", type=int, default=3)
    gen.add_argument("--alphabet", default=DEFAULT_CODE_ALPHABET)
    gen.add_argument("--token-len", type=int, default=2)
    gen.add_argument("--seed", default=DEFAULT_SEED)
    gen.add_argument("--no-punctuation", action="store_true")

    enc = sub.add_parser("encrypt", help="encrypt text")
    enc.add_argument("-m", "--mapping", required=True)
    enc.add_argument("--sep", default="", help="separator between output tokens, default: none")
    enc.add_argument("--pass-unknown", action="store_true", help="copy unmapped characters instead of failing")
    enc.add_argument("text", nargs="*")

    dec = sub.add_parser("decrypt", help="decrypt text")
    dec.add_argument("-m", "--mapping", required=True)
    dec.add_argument("--sep", default="", help="separator between input tokens, default: none")
    dec.add_argument("--pass-unknown", action="store_true", help="copy unknown ciphertext instead of failing")
    dec.add_argument("text", nargs="*")

    args = parser.parse_args()

    try:
        if args.cmd == "gen-map":
            generate_mapping_file(
                args.mapping_file,
                variants=args.variants,
                alphabet=args.alphabet,
                token_len=args.token_len,
                seed=args.seed,
                include_punctuation=not args.no_punctuation,
            )
            return

        mapping = parse_mapping(args.mapping)
        text = read_stdin_or_args(args.text)
        strict = not args.pass_unknown

        if args.cmd == "encrypt":
            if not args.no_ascii_normalize:
                text = normalize_to_ascii(text)
            print(encrypt(text, mapping, sep=args.sep, strict=strict))
        elif args.cmd == "decrypt":
            print(decrypt(text, mapping, sep=args.sep, strict=strict))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
