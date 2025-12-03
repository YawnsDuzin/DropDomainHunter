"""
Domain Sniper - 데이터베이스 모델
SQLite + aiosqlite 비동기 데이터베이스 관리
"""

import aiosqlite
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
import structlog

logger = structlog.get_logger()


@dataclass
class Domain:
    """도메인 엔티티"""
    id: Optional[int] = None
    name: str = ""
    tld: str = ""
    full_name: str = ""
    length: int = 0
    expiry_date: Optional[date] = None

    # 점수
    length_score: int = 0
    keyword_score: int = 0
    pattern_score: int = 0
    total_score: int = 0

    # 메타
    source: str = ""
    auction_url: str = ""
    estimated_value_min: Optional[int] = None
    estimated_value_max: Optional[int] = None
    status: str = "pending"

    # 타임스탬프
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    notified_at: Optional[datetime] = None

    @property
    def days_until_expiry(self) -> Optional[int]:
        """만료까지 남은 일수"""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - date.today()
        return delta.days

    @property
    def estimated_value_str(self) -> str:
        """예상 가치 문자열"""
        if self.estimated_value_min and self.estimated_value_max:
            return f"${self.estimated_value_min:,}~${self.estimated_value_max:,}"
        return "N/A"

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 변환"""
        return {
            "id": self.id,
            "name": self.name,
            "tld": self.tld,
            "full_name": self.full_name,
            "length": self.length,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "length_score": self.length_score,
            "keyword_score": self.keyword_score,
            "pattern_score": self.pattern_score,
            "total_score": self.total_score,
            "source": self.source,
            "auction_url": self.auction_url,
            "estimated_value_min": self.estimated_value_min,
            "estimated_value_max": self.estimated_value_max,
            "status": self.status,
            "days_until_expiry": self.days_until_expiry,
            "estimated_value_str": self.estimated_value_str,
        }


@dataclass
class WatchlistItem:
    """워치리스트 아이템"""
    id: Optional[int] = None
    domain_id: int = 0
    domain: Optional[Domain] = None
    note: str = ""
    priority: int = 5
    reminder_date: Optional[date] = None
    added_at: Optional[datetime] = None


@dataclass
class CrawlLog:
    """크롤링 로그"""
    id: Optional[int] = None
    source: str = ""
    crawl_type: str = ""
    total_found: int = 0
    new_domains: int = 0
    high_score_count: int = 0
    status: str = ""
    error_message: str = ""
    duration_seconds: float = 0.0
    created_at: Optional[datetime] = None


class Database:
    """비동기 SQLite 데이터베이스 관리자"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """데이터베이스 연결"""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # WAL 모드 활성화 (동시 읽기/쓰기 성능 향상)
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA cache_size=10000")
        await self._connection.execute("PRAGMA temp_store=MEMORY")

        logger.info("database_connected", path=str(self.db_path))

    async def close(self) -> None:
        """데이터베이스 연결 종료"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("database_closed")

    async def init_schema(self) -> None:
        """스키마 초기화"""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            schema = schema_path.read_text()
            await self._connection.executescript(schema)
            await self._connection.commit()
            logger.info("database_schema_initialized")

    # ===== Domain CRUD =====

    async def insert_domain(self, domain: Domain) -> int:
        """도메인 추가"""
        score_date = f"{domain.total_score:03d}_{domain.expiry_date or '9999-99-99'}"

        query = """
            INSERT OR REPLACE INTO domains
            (name, tld, full_name, length, expiry_date,
             length_score, keyword_score, pattern_score, total_score,
             source, auction_url, estimated_value_min, estimated_value_max,
             status, score_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """

        cursor = await self._connection.execute(query, (
            domain.name, domain.tld, domain.full_name, domain.length,
            domain.expiry_date.isoformat() if domain.expiry_date else None,
            domain.length_score, domain.keyword_score, domain.pattern_score, domain.total_score,
            domain.source, domain.auction_url,
            domain.estimated_value_min, domain.estimated_value_max,
            domain.status, score_date
        ))
        await self._connection.commit()
        return cursor.lastrowid

    async def bulk_insert_domains(self, domains: List[Domain]) -> int:
        """도메인 일괄 추가"""
        if not domains:
            return 0

        query = """
            INSERT OR IGNORE INTO domains
            (name, tld, full_name, length, expiry_date,
             length_score, keyword_score, pattern_score, total_score,
             source, auction_url, estimated_value_min, estimated_value_max,
             status, score_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        data = []
        for d in domains:
            score_date = f"{d.total_score:03d}_{d.expiry_date or '9999-99-99'}"
            data.append((
                d.name, d.tld, d.full_name, d.length,
                d.expiry_date.isoformat() if d.expiry_date else None,
                d.length_score, d.keyword_score, d.pattern_score, d.total_score,
                d.source, d.auction_url,
                d.estimated_value_min, d.estimated_value_max,
                d.status, score_date
            ))

        cursor = await self._connection.executemany(query, data)
        await self._connection.commit()
        return cursor.rowcount

    async def get_domain_by_name(self, full_name: str) -> Optional[Domain]:
        """도메인명으로 조회"""
        query = "SELECT * FROM domains WHERE full_name = ?"
        cursor = await self._connection.execute(query, (full_name,))
        row = await cursor.fetchone()
        return self._row_to_domain(row) if row else None

    async def get_domains(
        self,
        limit: int = 100,
        offset: int = 0,
        min_score: Optional[int] = None,
        status: Optional[str] = None,
        days_until_expiry: Optional[int] = None,
        order_by: str = "total_score DESC"
    ) -> List[Domain]:
        """도메인 목록 조회"""
        conditions = []
        params = []

        if min_score is not None:
            conditions.append("total_score >= ?")
            params.append(min_score)

        if status:
            conditions.append("status = ?")
            params.append(status)

        if days_until_expiry is not None:
            conditions.append("expiry_date <= date('now', '+' || ? || ' days')")
            params.append(days_until_expiry)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        query = f"""
            SELECT * FROM domains {where_clause}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = await self._connection.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_domain(row) for row in rows]

    async def get_unnotified_high_score_domains(self, min_score: int) -> List[Domain]:
        """알림 미발송 고점수 도메인 조회"""
        query = """
            SELECT * FROM domains
            WHERE total_score >= ? AND notified_at IS NULL AND status = 'pending'
            ORDER BY total_score DESC
        """
        cursor = await self._connection.execute(query, (min_score,))
        rows = await cursor.fetchall()
        return [self._row_to_domain(row) for row in rows]

    async def mark_domain_notified(self, domain_id: int) -> None:
        """도메인 알림 완료 처리"""
        query = """
            UPDATE domains
            SET notified_at = CURRENT_TIMESTAMP, status = 'notified'
            WHERE id = ?
        """
        await self._connection.execute(query, (domain_id,))
        await self._connection.commit()

    async def update_domain_status(self, domain_id: int, status: str) -> None:
        """도메인 상태 업데이트"""
        query = "UPDATE domains SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        await self._connection.execute(query, (status, domain_id))
        await self._connection.commit()

    async def get_domain_stats(self) -> Dict[str, Any]:
        """도메인 통계"""
        stats = {}

        # 총 도메인 수
        cursor = await self._connection.execute("SELECT COUNT(*) FROM domains")
        stats["total_count"] = (await cursor.fetchone())[0]

        # 상태별 수
        cursor = await self._connection.execute(
            "SELECT status, COUNT(*) FROM domains GROUP BY status"
        )
        stats["by_status"] = dict(await cursor.fetchall())

        # 점수 분포
        cursor = await self._connection.execute("""
            SELECT
                SUM(CASE WHEN total_score >= 80 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN total_score >= 60 AND total_score < 80 THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN total_score < 60 THEN 1 ELSE 0 END) as low
            FROM domains
        """)
        row = await cursor.fetchone()
        stats["score_distribution"] = {"high": row[0] or 0, "medium": row[1] or 0, "low": row[2] or 0}

        # 오늘 추가된 수
        cursor = await self._connection.execute(
            "SELECT COUNT(*) FROM domains WHERE date(created_at) = date('now')"
        )
        stats["today_count"] = (await cursor.fetchone())[0]

        return stats

    def _row_to_domain(self, row: aiosqlite.Row) -> Domain:
        """Row를 Domain 객체로 변환"""
        return Domain(
            id=row["id"],
            name=row["name"],
            tld=row["tld"],
            full_name=row["full_name"],
            length=row["length"],
            expiry_date=date.fromisoformat(row["expiry_date"]) if row["expiry_date"] else None,
            length_score=row["length_score"],
            keyword_score=row["keyword_score"],
            pattern_score=row["pattern_score"],
            total_score=row["total_score"],
            source=row["source"] or "",
            auction_url=row["auction_url"] or "",
            estimated_value_min=row["estimated_value_min"],
            estimated_value_max=row["estimated_value_max"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            notified_at=datetime.fromisoformat(row["notified_at"]) if row["notified_at"] else None,
        )

    # ===== Watchlist CRUD =====

    async def add_to_watchlist(self, domain_id: int, note: str = "", priority: int = 5) -> int:
        """워치리스트에 추가"""
        query = """
            INSERT INTO watchlist (domain_id, note, priority)
            VALUES (?, ?, ?)
        """
        cursor = await self._connection.execute(query, (domain_id, note, priority))
        await self._connection.execute(
            "UPDATE domains SET status = 'watched' WHERE id = ?", (domain_id,)
        )
        await self._connection.commit()
        return cursor.lastrowid

    async def get_watchlist(self) -> List[WatchlistItem]:
        """워치리스트 조회"""
        query = """
            SELECT w.*, d.* FROM watchlist w
            JOIN domains d ON w.domain_id = d.id
            ORDER BY w.priority DESC, d.expiry_date ASC
        """
        cursor = await self._connection.execute(query)
        rows = await cursor.fetchall()

        items = []
        for row in rows:
            domain = self._row_to_domain(row)
            item = WatchlistItem(
                id=row["id"],
                domain_id=row["domain_id"],
                domain=domain,
                note=row["note"] or "",
                priority=row["priority"],
                added_at=datetime.fromisoformat(row["added_at"]) if row["added_at"] else None,
            )
            items.append(item)
        return items

    async def remove_from_watchlist(self, watchlist_id: int) -> None:
        """워치리스트에서 제거"""
        # 먼저 domain_id 조회
        cursor = await self._connection.execute(
            "SELECT domain_id FROM watchlist WHERE id = ?", (watchlist_id,)
        )
        row = await cursor.fetchone()
        if row:
            await self._connection.execute(
                "UPDATE domains SET status = 'pending' WHERE id = ?", (row[0],)
            )

        await self._connection.execute("DELETE FROM watchlist WHERE id = ?", (watchlist_id,))
        await self._connection.commit()

    # ===== Crawl Log =====

    async def add_crawl_log(self, log: CrawlLog) -> int:
        """크롤링 로그 추가"""
        query = """
            INSERT INTO crawl_logs
            (source, crawl_type, total_found, new_domains, high_score_count,
             status, error_message, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = await self._connection.execute(query, (
            log.source, log.crawl_type, log.total_found, log.new_domains,
            log.high_score_count, log.status, log.error_message, log.duration_seconds
        ))
        await self._connection.commit()
        return cursor.lastrowid

    async def get_crawl_logs(self, limit: int = 50) -> List[CrawlLog]:
        """크롤링 로그 조회"""
        query = "SELECT * FROM crawl_logs ORDER BY created_at DESC LIMIT ?"
        cursor = await self._connection.execute(query, (limit,))
        rows = await cursor.fetchall()

        return [CrawlLog(
            id=row["id"],
            source=row["source"],
            crawl_type=row["crawl_type"],
            total_found=row["total_found"],
            new_domains=row["new_domains"],
            high_score_count=row["high_score_count"],
            status=row["status"],
            error_message=row["error_message"] or "",
            duration_seconds=row["duration_seconds"] or 0.0,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        ) for row in rows]

    # ===== Settings =====

    async def get_setting(self, key: str, default: str = "") -> str:
        """설정 조회"""
        cursor = await self._connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        """설정 저장"""
        query = """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """
        await self._connection.execute(query, (key, value))
        await self._connection.commit()

    # ===== Keywords =====

    async def get_keywords(self) -> Dict[str, int]:
        """키워드 딕셔너리 조회"""
        cursor = await self._connection.execute("SELECT word, score FROM keywords")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    async def add_keyword(self, word: str, category: str = "", score: int = 50) -> None:
        """키워드 추가"""
        query = """
            INSERT OR REPLACE INTO keywords (word, category, score)
            VALUES (?, ?, ?)
        """
        await self._connection.execute(query, (word, category, score))
        await self._connection.commit()

    async def bulk_add_keywords(self, keywords: Dict[str, int]) -> None:
        """키워드 일괄 추가"""
        query = "INSERT OR IGNORE INTO keywords (word, score) VALUES (?, ?)"
        data = [(word, score) for word, score in keywords.items()]
        await self._connection.executemany(query, data)
        await self._connection.commit()


async def init_database(db_path: str | Path) -> Database:
    """데이터베이스 초기화 및 연결"""
    db = Database(db_path)
    await db.connect()
    await db.init_schema()
    return db


# 테스트용
if __name__ == "__main__":
    async def test():
        db = await init_database("test_domains.db")

        # 테스트 도메인 추가
        domain = Domain(
            name="startup",
            tld="io",
            full_name="startup.io",
            length=7,
            expiry_date=date.today(),
            length_score=85,
            keyword_score=95,
            pattern_score=80,
            total_score=87,
            source="test"
        )

        domain_id = await db.insert_domain(domain)
        print(f"Inserted domain ID: {domain_id}")

        # 조회
        domains = await db.get_domains(limit=10)
        for d in domains:
            print(f"{d.full_name}: {d.total_score}")

        # 통계
        stats = await db.get_domain_stats()
        print(f"Stats: {stats}")

        await db.close()

    asyncio.run(test())
