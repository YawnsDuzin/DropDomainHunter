"""
Domain Sniper - 길이 기반 스코어러
도메인 길이에 따른 가치 평가
"""


class LengthScorer:
    """
    도메인 길이 기반 점수 계산

    짧은 도메인일수록 가치가 높음:
    - 2-3자: 100점 (매우 희귀)
    - 4자: 90점 (희귀)
    - 5자: 80점 (좋음)
    - 6자: 70점 (괜찮음)
    - 7자: 60점
    - 8자: 50점
    - 9자: 40점
    - 10자: 30점
    - 11자: 20점
    - 12자+: 10점
    """

    # 길이별 기본 점수
    LENGTH_SCORES = {
        1: 100,
        2: 100,
        3: 100,
        4: 90,
        5: 80,
        6: 70,
        7: 60,
        8: 50,
        9: 40,
        10: 30,
        11: 20,
        12: 10,
    }

    # TLD별 가중치
    TLD_MULTIPLIERS = {
        "com": 1.0,
        "net": 0.85,
        "io": 0.95,
        "co": 0.9,
        "ai": 1.0,
        "kr": 0.7,
        "org": 0.75,
        "app": 0.85,
        "dev": 0.9,
    }

    @classmethod
    def calculate(cls, domain_name: str, tld: str = "com") -> int:
        """
        도메인 길이 점수 계산

        Args:
            domain_name: 도메인 이름 (TLD 제외)
            tld: TLD

        Returns:
            0-100 사이의 점수
        """
        length = len(domain_name)

        # 기본 점수
        if length >= 12:
            base_score = 10
        else:
            base_score = cls.LENGTH_SCORES.get(length, 10)

        # TLD 가중치 적용
        tld_multiplier = cls.TLD_MULTIPLIERS.get(tld.lower(), 0.7)
        final_score = int(base_score * tld_multiplier)

        return min(100, max(0, final_score))

    @classmethod
    def get_length_tier(cls, length: int) -> str:
        """
        길이 등급 반환

        Args:
            length: 도메인 길이

        Returns:
            등급 문자열
        """
        if length <= 3:
            return "PREMIUM"
        elif length <= 4:
            return "ULTRA"
        elif length <= 5:
            return "HIGH"
        elif length <= 7:
            return "MEDIUM"
        elif length <= 10:
            return "LOW"
        else:
            return "VERY_LOW"


# 테스트
if __name__ == "__main__":
    test_cases = [
        ("ai", "com"),       # 2자 .com
        ("tech", "io"),      # 4자 .io
        ("startup", "com"),  # 7자 .com
        ("blockchain", "net"),  # 10자 .net
        ("cryptocurrency", "kr"),  # 14자 .kr
    ]

    for name, tld in test_cases:
        score = LengthScorer.calculate(name, tld)
        tier = LengthScorer.get_length_tier(len(name))
        print(f"{name}.{tld} ({len(name)}자): {score}점 [{tier}]")
