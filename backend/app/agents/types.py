from dataclasses import dataclass
from enum import StrEnum


class SentimentLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SourceType(StrEnum):
    REDDIT = "reddit"
    NEWS = "news"


class Freshness(StrEnum):
    DAY = "pd"
    WEEK = "pw"
    MONTH = "pm"
    YEAR = "py"


class SSEEventType(StrEnum):
    RUN_STARTED = "run_started"
    SEARCH_QUERIED = "search_queried"
    URL_FETCHED = "url_fetched"
    ITEM_ANALYZED = "item_analyzed"
    SYNTHESIS_STARTED = "synthesis_started"
    RUN_COMPLETED = "run_completed"
    RUN_ERROR = "run_error"


@dataclass
class SentimentResult:
    label: SentimentLabel
    summary: str  # 3–5 words
