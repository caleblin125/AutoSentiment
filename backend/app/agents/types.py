from dataclasses import dataclass
from enum import StrEnum


class SentimentLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SourceType(StrEnum):
    REDDIT = "reddit"
    NEWS = "news"
    FORUM = "forum"
    SOCIAL = "social"
    VIDEO = "video"
    WEB = "web"


class Freshness(StrEnum):
    DAY = "pd"
    WEEK = "pw"
    MONTH = "pm"
    YEAR = "py"


class SSEEventType(StrEnum):
    RUN_STARTED = "run_started"
    SEARCH_QUERIED = "search_queried"
    FETCH_STARTED = "fetch_started"
    URL_FETCHED = "url_fetched"
    ITEM_ANALYZED = "item_analyzed"
    SYNTHESIS_STARTED = "synthesis_started"
    SYNTHESIS_TOKEN = "synthesis_token"
    RUN_COMPLETED = "run_completed"
    RUN_CANCELLED = "run_cancelled"
    RUN_ERROR = "run_error"


@dataclass
class SentimentResult:
    label: SentimentLabel
    summary: str  # 3–5 words
