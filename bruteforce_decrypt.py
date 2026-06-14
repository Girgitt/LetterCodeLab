#!/usr/bin/env python3
"""
bruteforce_decrypt.py

Educational cryptanalysis tool for the round-robin homophonic substitution cipher.

It does NOT need the original mapping file.  It accepts ciphertext and language,
then tries to recover a readable plaintext using randomized hill-climbing / simulated
annealing and simple built-in language statistics.

This is intentionally a teaching tool, not a guaranteed solver.  Homophonic
substitution has an enormous keyspace, so true exhaustive brute force is not
practical for normal texts.

Examples:
    python3 bruteforce_decrypt.py --lang pl --token-len 2 "8FBRDAVX..."
    cat cipher.txt | python3 bruteforce_decrypt.py --lang en --token-len 2
    python3 bruteforce_decrypt.py --lang pl --sep " " "8F BR DA VX ..."

Useful options:
    --steps 80000 --restarts 30 --homophones 3 --show-map
"""

from __future__ import annotations

import argparse
import math
import random
import re
import string
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


DEFAULT_SYMBOLS = list(string.ascii_uppercase + string.digits + " .,?!-:;'/()\"")

LANG_DATA = {
    "en": {
        "freq": {
            " ": 18.0, "E": 12.0, "T": 9.1, "A": 8.2, "O": 7.5, "I": 7.0,
            "N": 6.7, "S": 6.3, "H": 6.1, "R": 6.0, "D": 4.3, "L": 4.0,
            "C": 2.8, "U": 2.8, "M": 2.4, "W": 2.4, "F": 2.2, "G": 2.0,
            "Y": 2.0, "P": 1.9, "B": 1.5, "V": 1.0, "K": 0.8, "J": 0.15,
            "X": 0.15, "Q": 0.10, "Z": 0.07,
        },
        "common_words": {
            "THE", "AND", "YOU", "THAT", "WAS", "FOR", "ARE", "WITH", "HIS",
            "THEY", "THIS", "HAVE", "FROM", "ONE", "HAD", "WORD", "BUT", "NOT",
            "WHAT", "ALL", "WERE", "WHEN", "YOUR", "CAN", "SAID", "THERE", "USE",
            "EACH", "WHICH", "SHE", "DO", "HOW", "THEIR", "WILL", "OTHER", "ABOUT",
            "OUT", "MANY", "THEN", "THEM", "THESE", "SO", "SOME", "HER", "WOULD",
        },
        "common_ngrams": {
            "TH", "HE", "IN", "ER", "AN", "RE", "ON", "AT", "EN", "ND", "TI", "ES",
            "OR", "TE", "OF", "ED", "IS", "IT", "AL", "AR", "ST", "TO", "NT", "NG",
            "THE", "AND", "ING", "ION", "ENT", "HER", "THA", "NTH", "ATI", "FOR",
            "TIO", "ERE", "TER", "EST", "ERS", "ATI", "HAT", "ATE", "ALL",
        },
    },
    "pl": {
        # Polish without diacritics.  This matches the earlier examples like SIE/DZISIAJ.
        "freq": {
            " ": 18.0, "A": 8.9, "I": 8.2, "E": 7.7, "O": 7.5, "Z": 5.6,
            "N": 5.5, "R": 4.7, "W": 4.7, "S": 4.3, "C": 4.0, "T": 4.0,
            "Y": 3.8, "K": 3.5, "D": 3.3, "P": 3.1, "M": 2.8, "U": 2.5,
            "J": 2.3, "L": 2.1, "B": 1.5, "G": 1.4, "H": 1.1, "F": 0.3,
            "V": 0.05, "Q": 0.02, "X": 0.02,
        },
        "common_words": {
            "I", "W", "Z", "A", "O", "U", "DO", "NA", "TO", "TA", "TE", "TEN", "NIE",
            "SIE", "JEST", "JAK", "CO", "PO", "OD", "ZA", "ZE", "DLA", "ORAZ", "ALE",
            "CZY", "JUZ", "GDY", "GDZIE", "PRZEZ", "PRZY", "MOZE", "MOJA", "MOJE",
            "DZISIAJ", "JUTRO", "WCZORAJ", "GODZINIE", "LOKALIZACJI", "TAJNEJ",
            "SPOTKAJMY", "PRZYNIES", "SIEDEMNASTEJ", "TRZYNASTCE", "TRZYNASCIE",
        },
        "common_ngrams": {
            "IE", "NI", "ZI", "SZ", "CZ", "DZ", "RZ", "PR", "ST", "OW", "WA", "NA", "PO",
            "DO", "GO", "KO", "NO", "RO", "EN", "AN", "CH", "SC", "CI", "JA", "EJ",
            "NIE", "SIE", "CIE", "DZI", "PRZ", "RZE", "SZE", "CZA", "STA", "OWA",
            "ZIE", "JES", "EST", "DZI", "SIA", "AJE", "NIA", "WIE",
        },
    },
}


@dataclass
class Candidate:
    score: float
    text: str
    mapping: Dict[str, str]


def read_text(parts: List[str]) -> str:
    if parts:
        return " ".join(parts).strip()
    return sys.stdin.read().strip()


def tokenize(ciphertext: str, token_len: int = 2, sep: str | None = None) -> List[str]:
    ciphertext = ciphertext.strip().upper()
    if sep is not None:
        return [part.strip().upper() for part in ciphertext.split(sep) if part.strip()]

    compact = re.sub(r"\s+", "", ciphertext)
    if len(compact) % token_len != 0:
        raise ValueError(
            f"ciphertext length {len(compact)} is not divisible by token length {token_len}. "
            f"Use --sep for separated tokens or set --token-len correctly."
        )
    return [compact[i : i + token_len] for i in range(0, len(compact), token_len)]


def language_symbols(lang: str, include_digits: bool = True) -> List[str]:
    symbols = list(string.ascii_uppercase)
    if include_digits:
        symbols.extend(string.digits)
    symbols.extend([" ", ".", ",", "?", "!", "-", ":", ";", "'", '"', "/", "(", ")"])
    return symbols


def make_log_probs(lang: str) -> Dict[str, float]:
    data = LANG_DATA[lang]
    freq = {ch: 0.03 for ch in DEFAULT_SYMBOLS}
    freq.update(data["freq"])

    # Digits and punctuation are possible but normally rare in prose.
    for d in string.digits:
        freq.setdefault(d, 0.15)
    for p in ".,?!-:;'\"/()":
        freq.setdefault(p, 0.15)

    total = sum(freq.values())
    return {ch: math.log(value / total) for ch, value in freq.items()}


def decrypt_with_mapping(tokens: Sequence[str], mapping: Dict[str, str]) -> str:
    return "".join(mapping.get(token, "?") for token in tokens)


def score_plaintext(text: str, lang: str, log_probs: Dict[str, float]) -> float:
    data = LANG_DATA[lang]
    score = 0.0

    # Character likelihood.
    for ch in text:
        score += log_probs.get(ch, math.log(0.0001))

    # Make spaces useful, but punish broken spacing.
    score -= 8.0 * text.count("  ")
    if text.startswith(" ") or text.endswith(" "):
        score -= 3.0

    # Penalize too many unknowns or punctuation noise.
    score -= 25.0 * text.count("?")

    # Word-level scoring.
    words = re.findall(r"[A-Z]+", text)
    common_words = data["common_words"]
    for word in words:
        if word in common_words:
            score += 8.0 + min(len(word), 10) * 0.8
        elif len(word) == 1:
            if word in {"A", "I", "O", "U", "W", "Z"}:
                score += 1.0
            else:
                score -= 2.0
        elif len(word) > 16:
            score -= (len(word) - 16) * 2.5

    # Common n-grams.  Count on a letters-only-plus-space normalized text.
    normalized = re.sub(r"[^A-Z ]+", " ", text)
    common_ngrams = data["common_ngrams"]
    for ng in common_ngrams:
        score += normalized.count(ng) * (1.5 if len(ng) == 2 else 3.0)

    # Penalize impossible-looking consonant clusters a bit.
    bad_clusters = re.findall(r"[BCDFGHJKLMNPQRSTVWXYZ]{6,}", normalized)
    score -= sum(len(cluster) for cluster in bad_clusters) * 2.0

    return score


def initial_mapping(
    observed_tokens: List[str],
    symbols: List[str],
    lang: str,
    homophones: int,
    rng: random.Random,
) -> Dict[str, str]:
    counts = Counter(observed_tokens)
    tokens_by_freq = [token for token, _count in counts.most_common()]

    data = LANG_DATA[lang]
    letters_by_freq = sorted(
        [s for s in symbols if s in data["freq"]],
        key=lambda ch: data["freq"].get(ch, 0.01),
        reverse=True,
    )

    mapping: Dict[str, str] = {}

    # Space is normally the highest-frequency plaintext symbol, split over a few homophones.
    for token in tokens_by_freq[: max(1, homophones)]:
        mapping[token] = " "

    remaining_tokens = [token for token in observed_tokens if token not in mapping]

    # Weighted random choices biased toward likely language symbols.
    weighted_symbols: List[str] = []
    for sym in symbols:
        weight = int(max(1, data["freq"].get(sym, 0.1) * 2))
        weighted_symbols.extend([sym] * weight)

    for token in remaining_tokens:
        mapping[token] = rng.choice(weighted_symbols)

    # Add a small deterministic frequency-biased assignment for the top tokens.
    for token, sym in zip(tokens_by_freq[max(1, homophones) :], letters_by_freq):
        if rng.random() < 0.5:
            mapping[token] = sym

    return mapping


def mutate_mapping(
    mapping: Dict[str, str],
    tokens: List[str],
    symbols: List[str],
    rng: random.Random,
) -> Dict[str, str]:
    new_mapping = dict(mapping)

    # Most moves: change one token's plaintext symbol.
    if rng.random() < 0.75 or len(tokens) < 2:
        token = rng.choice(tokens)
        new_mapping[token] = rng.choice(symbols)
        return new_mapping

    # Sometimes swap two token assignments.
    a, b = rng.sample(tokens, 2)
    new_mapping[a], new_mapping[b] = new_mapping[b], new_mapping[a]
    return new_mapping


def solve(
    observed_tokens: List[str],
    lang: str,
    restarts: int,
    steps: int,
    homophones: int,
    seed: int,
    include_digits: bool,
    top: int,
) -> List[Candidate]:
    unique_tokens = sorted(set(observed_tokens))
    symbols = language_symbols(lang, include_digits=include_digits)
    log_probs = make_log_probs(lang)

    best: List[Candidate] = []
    rng_master = random.Random(seed)

    for restart in range(restarts):
        rng = random.Random(rng_master.randrange(1 << 30))
        mapping = initial_mapping(unique_tokens, symbols, lang, homophones, rng)
        text = decrypt_with_mapping(observed_tokens, mapping)
        score = score_plaintext(text, lang, log_probs)

        best_local = Candidate(score=score, text=text, mapping=dict(mapping))

        # Temperature schedule.  Big enough to escape early bad guesses.
        start_temp = 15.0
        end_temp = 0.25

        for step in range(steps):
            t = step / max(1, steps - 1)
            temp = start_temp * ((end_temp / start_temp) ** t)

            candidate_mapping = mutate_mapping(mapping, unique_tokens, symbols, rng)
            candidate_text = decrypt_with_mapping(observed_tokens, candidate_mapping)
            candidate_score = score_plaintext(candidate_text, lang, log_probs)
            delta = candidate_score - score

            if delta >= 0 or rng.random() < math.exp(delta / max(temp, 1e-9)):
                mapping = candidate_mapping
                text = candidate_text
                score = candidate_score

                if score > best_local.score:
                    best_local = Candidate(score=score, text=text, mapping=dict(mapping))

        best.append(best_local)
        best = sorted(best, key=lambda c: c.score, reverse=True)[:top]

        print(
            f"restart {restart + 1:>3}/{restarts}: best={best_local.score:10.2f} global={best[0].score:10.2f}",
            file=sys.stderr,
        )

    return best


def format_mapping(mapping: Dict[str, str]) -> str:
    lines = []
    for token in sorted(mapping):
        value = mapping[token]
        if value == " ":
            value = "SPACE"
        lines.append(f"{token} -> {value}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Randomized brute-force/hill-climb decryptor for homophonic substitution"
    )
    parser.add_argument("text", nargs="*", help="ciphertext; stdin is used when omitted")
    parser.add_argument("--lang", choices=sorted(LANG_DATA), required=True)
    parser.add_argument("--token-len", type=int, default=2)
    parser.add_argument("--sep", default=None, help="token separator, e.g. --sep ' '")
    parser.add_argument("--restarts", type=int, default=25)
    parser.add_argument("--steps", type=int, default=60000)
    parser.add_argument("--homophones", type=int, default=3, help="expected homophones per frequent symbol")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--no-digits", action="store_true")
    parser.add_argument("--show-map", action="store_true")
    args = parser.parse_args()

    ciphertext = read_text(args.text)
    observed_tokens = tokenize(ciphertext, token_len=args.token_len, sep=args.sep)

    if len(set(observed_tokens)) < 5:
        raise SystemExit("too few distinct ciphertext tokens for statistical solving")

    print(
        f"tokens={len(observed_tokens)} unique={len(set(observed_tokens))} lang={args.lang}",
        file=sys.stderr,
    )

    candidates = solve(
        observed_tokens=observed_tokens,
        lang=args.lang,
        restarts=args.restarts,
        steps=args.steps,
        homophones=args.homophones,
        seed=args.seed,
        include_digits=not args.no_digits,
        top=args.top,
    )

    print("\n=== BEST CANDIDATES ===")
    for idx, cand in enumerate(candidates, 1):
        print(f"\n--- candidate {idx}, score={cand.score:.2f} ---")
        print(cand.text)
        if args.show_map:
            print("\nMapping guess:")
            print(format_mapping(cand.mapping))


if __name__ == "__main__":
    main()
