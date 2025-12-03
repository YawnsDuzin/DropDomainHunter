"""
Domain Sniper - 도메인 종합 평가기
길이, 키워드, 패턴 점수를 통합하여 최종 점수 산출
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import structlog

from .length import LengthScorer
from .keyword import KeywordScorer
from .pattern import PatternScorer
from database.models import Domain

logger = structlog.get_logger()


@dataclass
class EvaluationResult:
    """평가 결과"""
    domain_name: str
    tld: str
    full_name: str

    # 개별 점수
    length_score: int
    keyword_score: int
    pattern_score: int

    # 총점
    total_score: int

    # 상세 정보
    matched_keywords: List[str]
    cv_pattern: str
    length_tier: str
    pattern_tier: str

    # 예상 가치
    estimated_value_min: int
    estimated_value_max: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_name": self.domain_name,
            "tld": self.tld,
            "full_name": self.full_name,
            "length_score": self.length_score,
            "keyword_score": self.keyword_score,
            "pattern_score": self.pattern_score,
            "total_score": self.total_score,
            "matched_keywords": self.matched_keywords,
            "cv_pattern": self.cv_pattern,
            "length_tier": self.length_tier,
            "pattern_tier": self.pattern_tier,
            "estimated_value_min": self.estimated_value_min,
            "estimated_value_max": self.estimated_value_max,
        }


class DomainEvaluator:
    """
    도메인 종합 평가기

    점수 가중치:
    - 길이: 35%
    - 키워드: 40%
    - 패턴: 25%
    """

    # 점수 가중치
    WEIGHT_LENGTH = 0.35
    WEIGHT_KEYWORD = 0.40
    WEIGHT_PATTERN = 0.25

    # TLD별 가치 배수
    TLD_VALUE_MULTIPLIERS = {
        "com": 1.0,
        "io": 0.8,
        "ai": 0.9,
        "co": 0.7,
        "net": 0.6,
        "org": 0.5,
        "kr": 0.4,
        "dev": 0.6,
        "app": 0.6,
    }

    def __init__(self, custom_keywords_path: Optional[Path] = None):
        """
        초기화

        Args:
            custom_keywords_path: 커스텀 키워드 파일 경로
        """
        self.keyword_scorer = KeywordScorer(custom_keywords_path)
        logger.info("domain_evaluator_initialized")

    def evaluate(self, domain_name: str, tld: str = "com") -> EvaluationResult:
        """
        도메인 평가

        Args:
            domain_name: 도메인 이름 (TLD 제외)
            tld: TLD

        Returns:
            EvaluationResult 객체
        """
        # 개별 점수 계산
        length_score = LengthScorer.calculate(domain_name, tld)
        keyword_score, matched_keywords = self.keyword_scorer.calculate(domain_name)
        pattern_score, cv_pattern = PatternScorer.calculate(domain_name)

        # 가중 평균 계산
        total_score = int(
            length_score * self.WEIGHT_LENGTH +
            keyword_score * self.WEIGHT_KEYWORD +
            pattern_score * self.WEIGHT_PATTERN
        )

        # 등급 계산
        length_tier = LengthScorer.get_length_tier(len(domain_name))
        pattern_tier = PatternScorer.get_pattern_tier(pattern_score)

        # 예상 가치 계산
        value_min, value_max = self._estimate_value(
            total_score, len(domain_name), tld
        )

        return EvaluationResult(
            domain_name=domain_name,
            tld=tld,
            full_name=f"{domain_name}.{tld}",
            length_score=length_score,
            keyword_score=keyword_score,
            pattern_score=pattern_score,
            total_score=total_score,
            matched_keywords=matched_keywords,
            cv_pattern=cv_pattern,
            length_tier=length_tier,
            pattern_tier=pattern_tier,
            estimated_value_min=value_min,
            estimated_value_max=value_max,
        )

    def evaluate_domain_object(self, domain: Domain) -> Domain:
        """
        Domain 객체 평가 및 업데이트

        Args:
            domain: Domain 객체

        Returns:
            점수가 업데이트된 Domain 객체
        """
        result = self.evaluate(domain.name, domain.tld)

        domain.length_score = result.length_score
        domain.keyword_score = result.keyword_score
        domain.pattern_score = result.pattern_score
        domain.total_score = result.total_score
        domain.estimated_value_min = result.estimated_value_min
        domain.estimated_value_max = result.estimated_value_max

        return domain

    def bulk_evaluate(self, domains: List[Domain]) -> List[Domain]:
        """
        도메인 일괄 평가

        Args:
            domains: Domain 객체 리스트

        Returns:
            평가된 Domain 객체 리스트
        """
        evaluated = []
        for domain in domains:
            try:
                evaluated.append(self.evaluate_domain_object(domain))
            except Exception as e:
                logger.error("evaluation_error", domain=domain.full_name, error=str(e))
                evaluated.append(domain)

        logger.info("bulk_evaluation_completed", count=len(evaluated))
        return evaluated

    def _estimate_value(self, score: int, length: int, tld: str) -> Tuple[int, int]:
        """
        예상 가치 계산 (USD)

        Args:
            score: 총점
            length: 도메인 길이
            tld: TLD

        Returns:
            (최소 가치, 최대 가치)
        """
        # 기본 가치 (점수 기반)
        if score >= 90:
            base_min, base_max = 5000, 50000
        elif score >= 80:
            base_min, base_max = 1000, 10000
        elif score >= 70:
            base_min, base_max = 500, 5000
        elif score >= 60:
            base_min, base_max = 100, 1000
        elif score >= 50:
            base_min, base_max = 50, 500
        else:
            base_min, base_max = 10, 100

        # 길이 보정
        if length <= 3:
            base_min *= 5
            base_max *= 10
        elif length <= 4:
            base_min *= 3
            base_max *= 5
        elif length <= 5:
            base_min *= 2
            base_max *= 3

        # TLD 보정
        tld_mult = self.TLD_VALUE_MULTIPLIERS.get(tld.lower(), 0.3)
        base_min = int(base_min * tld_mult)
        base_max = int(base_max * tld_mult)

        return base_min, base_max

    def get_score_breakdown(self, domain_name: str, tld: str = "com") -> str:
        """
        점수 분석 리포트 생성

        Args:
            domain_name: 도메인 이름
            tld: TLD

        Returns:
            포맷된 리포트 문자열
        """
        result = self.evaluate(domain_name, tld)

        report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 도메인 평가 리포트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 도메인: {result.full_name}
📏 길이: {len(domain_name)}자 [{result.length_tier}]
🔤 패턴: {result.cv_pattern} [{result.pattern_tier}]

━━━ 점수 상세 ━━━
• 길이 점수: {result.length_score}/100 (가중치 {int(self.WEIGHT_LENGTH*100)}%)
• 키워드 점수: {result.keyword_score}/100 (가중치 {int(self.WEIGHT_KEYWORD*100)}%)
• 패턴 점수: {result.pattern_score}/100 (가중치 {int(self.WEIGHT_PATTERN*100)}%)

🎯 총점: {result.total_score}/100

━━━ 키워드 분석 ━━━
• 매칭된 키워드: {', '.join(result.matched_keywords) if result.matched_keywords else '없음'}

━━━ 가치 추정 ━━━
💰 ${result.estimated_value_min:,} ~ ${result.estimated_value_max:,}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return report


# 테스트
if __name__ == "__main__":
    evaluator = DomainEvaluator()

    test_domains = [
        ("ai", "com"),
        ("startup", "io"),
        ("cloudpay", "com"),
        ("techdata", "net"),
        ("xyz", "io"),
        ("mycoolapp", "co"),
    ]

    print("=" * 60)
    print("도메인 평가 테스트")
    print("=" * 60)

    for name, tld in test_domains:
        result = evaluator.evaluate(name, tld)
        print(f"\n{result.full_name}:")
        print(f"  총점: {result.total_score}/100")
        print(f"  길이: {result.length_score} | 키워드: {result.keyword_score} | 패턴: {result.pattern_score}")
        print(f"  예상가치: ${result.estimated_value_min:,}~${result.estimated_value_max:,}")

    # 상세 리포트 출력
    print("\n" + "=" * 60)
    print(evaluator.get_score_breakdown("startup", "io"))
