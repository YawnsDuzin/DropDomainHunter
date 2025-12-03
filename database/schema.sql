-- Domain Sniper - SQLite 스키마
-- 라즈베리파이4 최적화 버전

-- 도메인 정보 테이블
CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,              -- 도메인 이름 (TLD 제외)
    tld TEXT NOT NULL,                       -- TLD (com, net, io 등)
    full_name TEXT NOT NULL,                 -- 전체 도메인 (name.tld)
    length INTEGER NOT NULL,                 -- 도메인 길이
    expiry_date DATE,                        -- 만료 예정일

    -- 점수 정보
    length_score INTEGER DEFAULT 0,          -- 길이 점수 (0-100)
    keyword_score INTEGER DEFAULT 0,         -- 키워드 점수 (0-100)
    pattern_score INTEGER DEFAULT 0,         -- 패턴 점수 (0-100)
    total_score INTEGER DEFAULT 0,           -- 총점 (0-100)

    -- 메타 정보
    source TEXT,                             -- 수집 소스 (expireddomains, parkio 등)
    auction_url TEXT,                        -- 경매 URL
    estimated_value_min INTEGER,             -- 예상 최소 가치 ($)
    estimated_value_max INTEGER,             -- 예상 최대 가치 ($)

    -- 상태
    status TEXT DEFAULT 'pending',           -- pending, notified, watched, ignored

    -- 타임스탬프
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified_at TIMESTAMP,                   -- 알림 발송 시간

    -- 인덱스 최적화를 위한 복합 필드
    score_date TEXT                          -- 정렬용 (total_score + expiry_date)
);

-- 관심 도메인 (워치리스트)
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL,
    note TEXT,                               -- 사용자 메모
    priority INTEGER DEFAULT 5,              -- 우선순위 (1-10)
    reminder_date DATE,                      -- 알림 예정일
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
);

-- 애플리케이션 설정
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 크롤링 로그
CREATE TABLE IF NOT EXISTS crawl_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                    -- 크롤링 소스
    crawl_type TEXT NOT NULL,                -- full, week, day
    total_found INTEGER DEFAULT 0,           -- 발견된 도메인 수
    new_domains INTEGER DEFAULT 0,           -- 새로 추가된 도메인 수
    high_score_count INTEGER DEFAULT 0,      -- 고점수 도메인 수
    status TEXT NOT NULL,                    -- success, failed, partial
    error_message TEXT,                      -- 에러 메시지 (실패 시)
    duration_seconds REAL,                   -- 소요 시간
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 알림 로그
CREATE TABLE IF NOT EXISTS notification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER,
    channel TEXT NOT NULL,                   -- telegram, discord
    message_type TEXT NOT NULL,              -- alert, daily_report, heartbeat
    status TEXT NOT NULL,                    -- sent, failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE SET NULL
);

-- 키워드 사전 (고가치 키워드)
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT UNIQUE NOT NULL,
    category TEXT,                           -- tech, finance, brand, generic
    score INTEGER DEFAULT 50,                -- 기본 점수 (0-100)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_domains_full_name ON domains(full_name);
CREATE INDEX IF NOT EXISTS idx_domains_expiry_date ON domains(expiry_date);
CREATE INDEX IF NOT EXISTS idx_domains_total_score ON domains(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_domains_status ON domains(status);
CREATE INDEX IF NOT EXISTS idx_domains_score_date ON domains(score_date DESC);
CREATE INDEX IF NOT EXISTS idx_domains_created_at ON domains(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_domain_id ON watchlist(domain_id);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_source ON crawl_logs(source);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_created_at ON crawl_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_keywords_word ON keywords(word);

-- 기본 설정 삽입
INSERT OR IGNORE INTO settings (key, value, description) VALUES
    ('last_full_crawl', '', '마지막 전체 크롤링 시간'),
    ('last_week_crawl', '', '마지막 7일 크롤링 시간'),
    ('last_day_crawl', '', '마지막 1일 크롤링 시간'),
    ('total_domains_count', '0', '총 도메인 수'),
    ('app_version', '1.0.0', '애플리케이션 버전');
