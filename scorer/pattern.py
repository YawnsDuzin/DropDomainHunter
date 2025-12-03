"""
Domain Sniper - 패턴 기반 스코어러
도메인의 음운 구조 및 발음 용이성 평가
"""

import re
from typing import Tuple


class PatternScorer:
    """
    패턴 기반 점수 계산

    발음하기 쉽고 기억하기 좋은 도메인에 높은 점수 부여
    CVCV (자음-모음-자음-모음) 패턴이 이상적
    """

    VOWELS = set("aeiou")
    CONSONANTS = set("bcdfghjklmnpqrstvwxyz")

    # 좋은 자음 조합 (발음하기 쉬움)
    GOOD_CONSONANT_PAIRS = {
        "bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr",
        "pl", "pr", "sc", "sh", "sk", "sl", "sm", "sn", "sp", "st",
        "sw", "th", "tr", "tw", "wh", "wr"
    }

    # 나쁜 자음 조합 (발음하기 어려움)
    BAD_CONSONANT_PAIRS = {
        "bk", "bz", "cf", "cg", "ck", "cm", "cn", "cp", "cv", "cw",
        "dk", "dz", "fk", "fn", "fp", "fz", "gk", "gm", "gn", "gz",
        "hk", "hz", "jk", "jz", "kf", "km", "kn", "kp", "kz", "lk",
        "mf", "mk", "mz", "nk", "pb", "pf", "pk", "pn", "pz", "qk",
        "sz", "tb", "tf", "tg", "tk", "tm", "tn", "tp", "tz", "vk",
        "vz", "wk", "wz", "xk", "xz", "zb", "zf", "zg", "zk", "zm"
    }

    @classmethod
    def calculate(cls, domain_name: str) -> Tuple[int, str]:
        """
        패턴 점수 계산

        Args:
            domain_name: 도메인 이름 (TLD 제외)

        Returns:
            (점수, 패턴 문자열)
        """
        domain_lower = domain_name.lower()
        pattern = cls._get_cv_pattern(domain_lower)

        score = 50  # 기본 점수

        # 1. CV 패턴 분석 (최대 +30)
        cv_score = cls._analyze_cv_pattern(pattern)
        score += cv_score

        # 2. 자음 연속 분석 (최대 -20)
        consonant_penalty = cls._analyze_consonant_clusters(domain_lower)
        score -= consonant_penalty

        # 3. 반복 문자 분석 (최대 +10)
        repeat_score = cls._analyze_repetition(domain_lower)
        score += repeat_score

        # 4. 시작/끝 문자 분석 (최대 +10)
        edge_score = cls._analyze_edges(domain_lower)
        score += edge_score

        # 범위 제한
        score = min(100, max(0, score))

        return score, pattern

    @classmethod
    def _get_cv_pattern(cls, domain: str) -> str:
        """CV 패턴 추출 (C=자음, V=모음)"""
        pattern = ""
        for char in domain.lower():
            if char in cls.VOWELS:
                pattern += "V"
            elif char in cls.CONSONANTS:
                pattern += "C"
            else:
                pattern += "X"  # 숫자나 특수문자
        return pattern

    @classmethod
    def _analyze_cv_pattern(cls, pattern: str) -> int:
        """CV 패턴 점수"""
        score = 0

        # 이상적인 패턴들
        ideal_patterns = [
            "CVCV",    # 4자: 코코, 라라
            "CVCVC",   # 5자: 애플, 구글
            "CVCCV",   # 5자: 테슬라
            "CVCVCV",  # 6자: 토요타
            "CVCCVC",  # 6자: 넷플릭스
        ]

        # 정확히 이상적인 패턴이면 +30
        if pattern in ideal_patterns:
            return 30

        # 부분 매칭
        # CVCV로 시작하면 +15
        if pattern.startswith("CVCV"):
            score += 15
        # CVC로 시작하면 +10
        elif pattern.startswith("CVC"):
            score += 10
        # CV로 시작하면 +5
        elif pattern.startswith("CV"):
            score += 5

        # VCV로 끝나면 +10 (발음하기 쉬움)
        if pattern.endswith("VCV"):
            score += 10
        elif pattern.endswith("CV"):
            score += 5

        # 자음 연속 3개 이상이면 감점
        if "CCC" in pattern:
            score -= 10
        if "CCCC" in pattern:
            score -= 15

        # 모음 연속 3개 이상이면 감점
        if "VVV" in pattern:
            score -= 5

        return max(0, min(30, score))

    @classmethod
    def _analyze_consonant_clusters(cls, domain: str) -> int:
        """자음 조합 분석 (감점)"""
        penalty = 0

        # 2글자 자음 조합 검사
        for i in range(len(domain) - 1):
            pair = domain[i:i+2].lower()
            if pair in cls.BAD_CONSONANT_PAIRS:
                penalty += 5
            elif pair in cls.GOOD_CONSONANT_PAIRS:
                penalty -= 2  # 좋은 조합은 보너스

        return max(0, penalty)

    @classmethod
    def _analyze_repetition(cls, domain: str) -> int:
        """반복 패턴 분석"""
        score = 0

        # 운율이 맞는 반복 (예: papa, bobo)
        half = len(domain) // 2
        if len(domain) >= 4 and domain[:half] == domain[half:half*2]:
            score += 10

        # 같은 문자 연속 3개 이상은 감점
        for i in range(len(domain) - 2):
            if domain[i] == domain[i+1] == domain[i+2]:
                score -= 5

        return score

    @classmethod
    def _analyze_edges(cls, domain: str) -> int:
        """시작/끝 문자 분석"""
        score = 0

        if not domain:
            return 0

        first = domain[0].lower()
        last = domain[-1].lower()

        # 자음으로 시작하면 +3 (대부분의 좋은 브랜드)
        if first in cls.CONSONANTS:
            score += 3

        # 모음으로 끝나면 +3 (발음하기 쉬움)
        if last in cls.VOWELS:
            score += 3
        # 특정 자음으로 끝나면 +2 (n, r, l, m, s, t)
        elif last in "nrlmst":
            score += 2

        # 발음하기 좋은 시작 자음
        good_starts = {"b", "c", "d", "f", "g", "k", "l", "m", "n", "p", "r", "s", "t", "w"}
        if first in good_starts:
            score += 2

        return score

    @classmethod
    def get_pattern_tier(cls, score: int) -> str:
        """패턴 등급 반환"""
        if score >= 80:
            return "EXCELLENT"
        elif score >= 65:
            return "GOOD"
        elif score >= 50:
            return "AVERAGE"
        elif score >= 35:
            return "POOR"
        else:
            return "BAD"


# 테스트
if __name__ == "__main__":
    test_domains = [
        "google",    # CVVCVV - 좋음
        "apple",     # VCCVV - 괜찮음
        "amazon",    # VCVCVC - 좋음
        "meta",      # CVCV - 이상적
        "tesla",     # CVCCV - 좋음
        "xyz",       # CVC - 짧음
        "strength",  # CCCCVCCC - 발음 어려움
        "papa",      # CVCV 반복 - 좋음
        "crypto",    # CCVCCV - 괜찮음
    ]

    for domain in test_domains:
        score, pattern = PatternScorer.calculate(domain)
        tier = PatternScorer.get_pattern_tier(score)
        print(f"{domain}: {score}점 | 패턴: {pattern} | 등급: {tier}")
