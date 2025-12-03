"""
Domain Sniper - 키워드 기반 스코어러
도메인에 포함된 고가치 키워드 평가
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()


class KeywordScorer:
    """
    키워드 기반 점수 계산

    고가치 키워드가 포함된 도메인에 높은 점수 부여
    """

    # 내장 고가치 키워드 데이터베이스
    DEFAULT_KEYWORDS: Dict[str, int] = {
        # Tech (90-100점)
        "ai": 100, "ml": 95, "api": 95, "app": 90, "bot": 90,
        "cloud": 95, "data": 90, "dev": 90, "code": 85, "tech": 90,
        "web": 85, "net": 80, "io": 85, "crypto": 95, "nft": 90,
        "meta": 90, "cyber": 85, "digital": 80, "smart": 85,
        "auto": 85, "robot": 85, "vr": 90, "ar": 90, "xr": 90,

        # Finance (85-95점)
        "pay": 95, "bank": 90, "cash": 90, "coin": 90, "money": 85,
        "fund": 85, "trade": 85, "stock": 85, "invest": 85,
        "finance": 80, "credit": 80, "loan": 80, "wallet": 85,

        # Business (80-90점)
        "pro": 85, "biz": 80, "corp": 80, "inc": 75, "hub": 85,
        "lab": 85, "studio": 80, "agency": 75, "group": 75,
        "team": 80, "work": 80, "job": 80, "hire": 80,
        "market": 85, "shop": 85, "store": 85, "buy": 85, "sell": 85,

        # Startup/Innovation (85-95점)
        "startup": 95, "launch": 85, "grow": 80, "scale": 85,
        "boost": 80, "rapid": 80, "fast": 80, "quick": 75,
        "next": 85, "new": 80, "fresh": 75, "prime": 85,

        # Generic Premium (75-85점)
        "best": 80, "top": 80, "first": 80, "one": 85,
        "go": 85, "get": 80, "my": 75, "the": 75,
        "easy": 75, "simple": 75, "smart": 80, "super": 75,

        # Action Words (70-80점)
        "find": 75, "search": 75, "discover": 70, "explore": 70,
        "create": 75, "make": 75, "build": 80, "design": 75,
        "learn": 75, "teach": 70, "train": 75, "coach": 70,
        "play": 75, "game": 80, "fun": 70, "live": 80,

        # Communication (70-80점)
        "chat": 80, "talk": 75, "call": 75, "meet": 80,
        "connect": 75, "link": 80, "share": 75, "send": 75,
        "mail": 80, "message": 70, "notify": 70, "alert": 70,

        # Media/Content (70-85점)
        "video": 85, "audio": 75, "music": 80, "photo": 75,
        "image": 70, "media": 75, "news": 80, "blog": 70,
        "stream": 85, "cast": 80, "pod": 80, "tube": 75,

        # Health/Lifestyle (70-80점)
        "health": 80, "fit": 80, "life": 80, "care": 75,
        "well": 75, "zen": 80, "yoga": 70, "med": 75,
        "food": 80, "eat": 75, "diet": 70, "cook": 70,

        # Nature/Environment (65-75점)
        "green": 75, "eco": 80, "solar": 80, "wind": 70,
        "water": 70, "air": 70, "earth": 70, "bio": 75,
        "nature": 65, "organic": 65, "clean": 70, "pure": 70,

        # Travel/Location (70-80점)
        "travel": 80, "trip": 75, "tour": 70, "fly": 75,
        "hotel": 75, "stay": 70, "book": 75, "rent": 75,
        "local": 70, "city": 70, "world": 75, "global": 75,

        # Single Letters (희귀, 높은 점수)
        "x": 95, "z": 90, "q": 85, "k": 80,
    }

    def __init__(self, custom_keywords_path: Optional[Path] = None):
        """
        초기화

        Args:
            custom_keywords_path: 커스텀 키워드 JSON 파일 경로
        """
        self.keywords = self.DEFAULT_KEYWORDS.copy()

        # 커스텀 키워드 로드
        if custom_keywords_path and custom_keywords_path.exists():
            self._load_custom_keywords(custom_keywords_path)

    def _load_custom_keywords(self, path: Path) -> None:
        """커스텀 키워드 파일 로드"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                custom = json.load(f)
                if isinstance(custom, dict):
                    self.keywords.update(custom)
                    logger.info("custom_keywords_loaded", count=len(custom))
        except Exception as e:
            logger.warning("custom_keywords_load_failed", error=str(e))

    def calculate(self, domain_name: str) -> Tuple[int, List[str]]:
        """
        키워드 점수 계산

        Args:
            domain_name: 도메인 이름 (TLD 제외)

        Returns:
            (점수, 매칭된 키워드 리스트)
        """
        domain_lower = domain_name.lower()
        matched_keywords = []
        max_score = 0

        # 정확히 일치하는 키워드 찾기
        if domain_lower in self.keywords:
            matched_keywords.append(domain_lower)
            max_score = self.keywords[domain_lower]

        # 포함된 키워드 찾기
        for keyword, score in self.keywords.items():
            if len(keyword) >= 2 and keyword in domain_lower:
                if keyword not in matched_keywords:
                    matched_keywords.append(keyword)
                    max_score = max(max_score, score)

        # 보너스: 여러 키워드 조합
        if len(matched_keywords) >= 2:
            max_score = min(100, max_score + 10)

        return max_score, matched_keywords

    def get_keyword_category(self, keyword: str) -> str:
        """
        키워드 카테고리 반환

        Args:
            keyword: 키워드

        Returns:
            카테고리 문자열
        """
        tech_keywords = {"ai", "ml", "api", "app", "bot", "cloud", "data", "dev", "code", "tech", "web", "crypto", "nft"}
        finance_keywords = {"pay", "bank", "cash", "coin", "money", "fund", "trade", "stock", "invest", "wallet"}
        business_keywords = {"pro", "biz", "corp", "hub", "lab", "studio", "market", "shop", "store"}

        keyword_lower = keyword.lower()

        if keyword_lower in tech_keywords:
            return "TECH"
        elif keyword_lower in finance_keywords:
            return "FINANCE"
        elif keyword_lower in business_keywords:
            return "BUSINESS"
        else:
            return "GENERIC"

    def add_keyword(self, keyword: str, score: int) -> None:
        """키워드 추가"""
        self.keywords[keyword.lower()] = min(100, max(0, score))

    def remove_keyword(self, keyword: str) -> None:
        """키워드 제거"""
        self.keywords.pop(keyword.lower(), None)


# 테스트
if __name__ == "__main__":
    scorer = KeywordScorer()

    test_domains = [
        "ai",
        "cloudpay",
        "startuplab",
        "mycoolapp",
        "randomxyz",
        "techdata",
        "cryptowallet",
    ]

    for domain in test_domains:
        score, keywords = scorer.calculate(domain)
        categories = [scorer.get_keyword_category(k) for k in keywords]
        print(f"{domain}: {score}점 | 키워드: {keywords} | 카테고리: {categories}")
