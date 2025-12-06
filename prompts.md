
================================
2025.12.04(목)
================================

참고: 봇에게 먼저 /start를 보내지 않으면 봇이 사용자에게 메시지를 보낼 수 없습니다. 이것은 Telegram의 스팸 방지 정책입니다.


================================

아래의 정보로 github push까지 해줘.

================================
2025.12.06(토)
================================

(venv) dzp@rasp-dzp-1:~/domain-sniper $ python main.py --crawl-now
2025-12-06T10:48:48.712336Z [info     ] initializing_domain_sniper     [__main__]
2025-12-06T10:48:48.716955Z [info     ] database_connected             [database.models] path=/home/dzp/domain-sniper/domains.db
2025-12-06T10:48:48.719216Z [info     ] database_schema_initialized    [database.models]
2025-12-06T10:48:48.720474Z [info     ] custom_keywords_loaded         [scorer.keyword] count=160
2025-12-06T10:48:48.721142Z [info     ] domain_evaluator_initialized   [scorer.evaluator]
2025-12-06T10:48:48.765308Z [info     ] telegram_notifier_initialized  [notifier.telegram]
2025-12-06T10:48:48.766074Z [warning  ] discord_notifier_disabled      [notifier.discord] reason=Missing webhook URL
2025-12-06T10:48:48.766639Z [info     ] notification_manager_initialized [notifier.manager] discord_enabled=False telegram_enabled=True
Adding job tentatively -- it will be properly scheduled when the scheduler starts
Adding job tentatively -- it will be properly scheduled when the scheduler starts
Adding job tentatively -- it will be properly scheduled when the scheduler starts
Adding job tentatively -- it will be properly scheduled when the scheduler starts
2025-12-06T10:48:48.773424Z [info     ] schedules_configured           [__main__]
2025-12-06T10:48:48.773823Z [info     ] domain_sniper_initialized      [__main__]
2025-12-06T10:48:48.774150Z [info     ] running_immediate_crawl        [__main__]
2025-12-06T10:48:48.774550Z [info     ] starting_full_crawl            [__main__]
2025-12-06T10:48:48.795688Z [info     ] http_client_initialized        [crawler.expired_domains]
2025-12-06T10:48:48.796390Z [info     ] crawling_tld                   [crawler.expired_domains] tld=com
2025-12-06T10:48:48.797094Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=com url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=                            0&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:48:51.689666Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:48:51.690337Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:48:51.690828Z [info     ] crawl_completed                [crawler.expired_domains] tld=com total=0
2025-12-06T10:48:56.696655Z [info     ] crawling_tld                   [crawler.expired_domains] tld=net
2025-12-06T10:48:56.698860Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=net url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=                            0&ftld%5B%5D=net&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=net&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:48:59.620157Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:48:59.620969Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:48:59.621435Z [info     ] crawl_completed                [crawler.expired_domains] tld=net total=0
2025-12-06T10:49:04.627315Z [info     ] crawling_tld                   [crawler.expired_domains] tld=io
2025-12-06T10:49:04.629394Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=io url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0                            &ftld%5B%5D=io&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=io&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:49:08.443833Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:49:08.444564Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:49:08.444989Z [info     ] crawl_completed                [crawler.expired_domains] tld=io total=0
2025-12-06T10:49:13.450827Z [info     ] crawling_tld                   [crawler.expired_domains] tld=ai
2025-12-06T10:49:13.453176Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=ai url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0                            &ftld%5B%5D=ai&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=ai&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:49:17.117156Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:49:17.117886Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:49:17.118313Z [info     ] crawl_completed                [crawler.expired_domains] tld=ai total=0
2025-12-06T10:49:22.124238Z [info     ] crawling_tld                   [crawler.expired_domains] tld=co
2025-12-06T10:49:22.126271Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=co url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0                            &ftld%5B%5D=co&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=co&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:49:25.957014Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:49:25.957752Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:49:25.961710Z [info     ] crawl_completed                [crawler.expired_domains] tld=co total=0
2025-12-06T10:49:30.967639Z [info     ] crawling_tld                   [crawler.expired_domains] tld=kr
2025-12-06T10:49:30.969583Z [info     ] crawling_page                  [crawler.expired_domains] page=1 tld=kr url=https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=kr&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1
HTTP Request: GET https://www.expireddomains.net/expired-domains/?fwhois=22&fbl=0&fstatuses%5B%5D=1&start=0&ftld%5B%5D=kr&fmaxchars=12&fminchars=3&fhyphens=1&fnumbers=1 "HTTP/1.1 200 OK"
2025-12-06T10:49:34.361489Z [info     ] html_parsed                    [crawler.parser] domain_count=0
2025-12-06T10:49:34.362238Z [info     ] no_more_domains                [crawler.expired_domains] page=1
2025-12-06T10:49:34.362757Z [info     ] crawl_completed                [crawler.expired_domains] tld=kr total=0
2025-12-06T10:49:39.369923Z [info     ] http_client_closed             [crawler.expired_domains]
2025-12-06T10:49:39.371705Z [info     ] bulk_evaluation_completed      [scorer.evaluator] count=0
2025-12-06T10:49:39.372866Z [info     ] domains_processed              [__main__] high_score=0 new=0 total=0
2025-12-06T10:49:39.379013Z [info     ] no_high_score_domains_to_notify [notifier.manager]
2025-12-06T10:49:39.385601Z [info     ] stopping_domain_sniper         [__main__]
Traceback (most recent call last):
  File "/home/dzp/domain-sniper/main.py", line 410, in <module>
    asyncio.run(main())
  File "/usr/lib/python3.9/asyncio/runners.py", line 44, in run
    return loop.run_until_complete(main)
  File "uvloop/loop.pyx", line 1517, in uvloop.loop.Loop.run_until_complete
  File "/home/dzp/domain-sniper/main.py", line 399, in main
    await sniper.run_crawl_now()
  File "/home/dzp/domain-sniper/main.py", line 377, in run_crawl_now
    await self.stop()
  File "/home/dzp/domain-sniper/main.py", line 365, in stop
    self.scheduler.shutdown(wait=False)
  File "/home/dzp/domain-sniper/venv/lib/python3.9/site-packages/apscheduler/schedulers/asyncio.py", line 13, in wrapper
    self._eventloop.call_soon_threadsafe(wrapped)
AttributeError: 'NoneType' object has no attribute 'call_soon_threadsafe'

[추가]
(venv) dzp@rasp-dzp-1:~/domain-sniper $ python main.py --crawl-now

Traceback (most recent call last):
  File "/home/dzp/domain-sniper/main.py", line 29, in <module>
    from config import settings, validate_settings
  File "/home/dzp/domain-sniper/config.py", line 94, in <module>
    settings = Settings()
  File "/home/dzp/domain-sniper/venv/lib/python3.9/site-packages/pydantic_settings/main.py", line 71, in __init__
    super().__init__(
  File "/home/dzp/domain-sniper/venv/lib/python3.9/site-packages/pydantic/main.py", line 171, in __init__
    self.__pydantic_validator__.validate_python(data, self_instance=self)
pydantic_core._pydantic_core.ValidationError: 2 validation errors for Settings
expired_domains_username
  Extra inputs are not permitted [type=extra_forbidden, input_value='yawnsduzin', input_type=str]
    For further information visit https://errors.pydantic.dev/2.6/v/extra_forbidden
expired_domains_password
  Extra inputs are not permitted [type=extra_forbidden, input_value='4,X6Dt2a$HyVkLH', input_type=str]
    For further information visit https://errors.pydantic.dev/2.6/v/extra_forbidden

[작업내용]
크롤러에 로그인 기능이 없습니다. ExpiredDomains.net은 로그인이 필요하므로 로그인 기능을 추가하겠습니다:

================================

아마도 https://www.expireddomains.net/expired-domains 접속 후에 로그인을 다시해야 하는 것 같아.

================================

/init

================================

변경된 사항에 맞게 ./docs 폴더의 파일과 수정필요한 문서 수정해줘.

================================

git push

================================
================================
================================
================================
================================
================================
================================
================================
================================
================================
================================
================================
