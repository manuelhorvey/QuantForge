import hashlib
import json
import logging
import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from features.macro_narrative import (
    MacroNarrativeFeatures,
    load_narrative_json,
    neutral_narrative,
    save_narrative_json,
)

logger = logging.getLogger("quantforge.fxstreet_fetcher")

FXSTREET_URL = "https://www.fxstreet.com/analysis"
NARRATIVE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "live",
)
NARRATIVE_PENDING = os.path.join(NARRATIVE_DIR, "narrative_pending.json")
NARRATIVE_ACTIVE = os.path.join(NARRATIVE_DIR, "narrative_active.json")
NARRATIVE_ERROR = os.path.join(NARRATIVE_DIR, "narrative_error.json")
LLM_SYSTEM_PROMPT = (
    "You are a macro analyst. Extract structured data from this FX market Week Ahead summary. "
    "Return ONLY valid JSON matching this exact schema:\n"
    '{\n  "usd_strength_narrative": 0.0-1.0,\n  "geopol_risk_score": 0.0-1.0,\n'
    '  "fed_hawkishness": 0.0-1.0,\n  "rbnz_hawkishness": 0.0-1.0,\n'
    '  "rba_hawkishness": 0.0-1.0,\n  "boj_intervention_risk": 0.0-1.0,\n'
    '  "energy_crisis_pressure": 0.0-1.0,\n  "usd_bias": "bullish"|"bearish"|"neutral",\n'
    '  "nzd_bias": "bullish"|"bearish"|"neutral",\n'
    '  "aud_bias": "bullish"|"bearish"|"neutral",\n'
    '  "jpy_bias": "bullish"|"bearish"|"neutral",\n'
    '  "cad_bias": "bullish"|"bearish"|"neutral",\n'
    '  "eur_bias": "bullish"|"bearish"|"neutral",\n'
    '  "key_events": ["event1", "event2"],\n'
    '  "overall_regime": "risk_on"|"risk_off"|"data_driven"|"geopol_tension",\n'
    '  "confidence": 0.0-1.0\n}'
)


def fetch_fxstreet_article() -> str | None:
    url = FXSTREET_URL
    headers = {"User-Agent": "QuantForge Research Bot"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.find_all("a", href=True, string=re.compile(r"Week ahead", re.I))
        if not articles:
            articles = soup.find_all("a", href=True, string=re.compile(r"Weekly (outlook|forecast)", re.I))
        if articles:
            href = articles[0]["href"]
            if href.startswith("/"):
                href = "https://www.fxstreet.com" + href
            article_resp = requests.get(href, headers=headers, timeout=15)
            article_resp.raise_for_status()
            article_soup = BeautifulSoup(article_resp.text, "html.parser")
            content = article_soup.find("div", class_=re.compile(r"article-content|entry-content|post-content"))
            if content:
                for tag in content.find_all(["script", "style", "nav", "footer"]):
                    tag.decompose()
                return content.get_text(separator="\n", strip=True)
        return None
    except Exception as e:
        logger.error("Failed to fetch FXStreet: %s", e)
        return None


def call_llm(text: str, api_key: str, model: str = "deepseek-v4-flash-free") -> dict | None:
    url = "https://opencode.ai/zen/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        logger.error("LLM response contained no JSON: %s", content[:200])
        return None
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return None


def run_weekly_narrative_pipeline(api_key: str | None = None) -> bool:
    os.makedirs(NARRATIVE_DIR, exist_ok=True)
    text = fetch_fxstreet_article()
    if not text:
        _write_error("scrape_failed", "No FXStreet article found or fetch returned empty")
        logger.warning("FXStreet scrape returned no content — narrative not updated")
        return False

    content_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
    week_start = datetime.now().strftime("%Y-%m-%d")

    if api_key:
        llm_result = call_llm(text, api_key)
        if llm_result is None:
            _write_error("llm_failed", "LLM call returned no result")
            logger.warning("LLM extraction failed — narrative not updated")
            return False
        llm_result["narrative_version"] = f"{week_start}_{content_hash}"
        features = MacroNarrativeFeatures(
            week_start=week_start,
            **{k: v for k, v in llm_result.items() if k in MacroNarrativeFeatures.__dataclass_fields__},
        )
    else:
        logger.info("No API key set — writing neutral fallback narrative for %s", week_start)
        features = neutral_narrative(week_start)
        features.narrative_version = f"{week_start}_{content_hash}_fallback"

    save_narrative_json(NARRATIVE_PENDING, features)
    logger.info("Narrative pending for week starting %s (version=%s)", week_start, features.narrative_version)
    return True


def confirm_pending_narrative() -> bool:
    if not os.path.exists(NARRATIVE_PENDING):
        logger.warning("No pending narrative to confirm")
        return False
    try:
        import shutil

        shutil.copy2(NARRATIVE_PENDING, NARRATIVE_ACTIVE)
        logger.info("Narrative confirmed: %s → %s", NARRATIVE_PENDING, NARRATIVE_ACTIVE)
        if os.path.exists(NARRATIVE_ERROR):
            os.remove(NARRATIVE_ERROR)
        return True
    except Exception as e:
        logger.error("Failed to confirm narrative: %s", e)
        return False


def get_active_narrative() -> MacroNarrativeFeatures | None:
    if not os.path.exists(NARRATIVE_ACTIVE):
        return None
    try:
        return load_narrative_json(NARRATIVE_ACTIVE)
    except Exception as e:
        logger.error("Failed to load active narrative: %s", e)
        return None


def get_pending_narrative() -> MacroNarrativeFeatures | None:
    if not os.path.exists(NARRATIVE_PENDING):
        return None
    try:
        return load_narrative_json(NARRATIVE_PENDING)
    except Exception as e:
        logger.warning("Failed to load pending narrative: %s", e)
        return None


def is_narrative_stale(week_start: str) -> bool:
    try:
        start = datetime.strptime(week_start, "%Y-%m-%d").date()
        now = datetime.now().date()
        days_since = (now - start).days
        return days_since >= 7
    except (ValueError, TypeError):
        return True


def _write_error(reason: str, detail: str) -> None:
    try:
        with open(NARRATIVE_ERROR, "w") as f:
            json.dump({"reason": reason, "detail": detail, "timestamp": datetime.now().isoformat()}, f)
    except Exception:
        pass


def get_fetch_error() -> dict | None:
    if not os.path.exists(NARRATIVE_ERROR):
        return None
    try:
        with open(NARRATIVE_ERROR) as f:
            return json.load(f)
    except Exception:
        return None


def get_narrative_status() -> dict:
    active = get_active_narrative()
    pending = get_pending_narrative()
    error = get_fetch_error()
    stale = is_narrative_stale(active.week_start) if active else False
    week_start_candidates = [p.week_start for p in [pending, active] if p]
    return {
        "week_start": max(week_start_candidates) if week_start_candidates else datetime.now().strftime("%Y-%m-%d"),
        "active": active.to_dict() if active else None,
        "pending": pending.to_dict() if pending else None,
        "stale": stale,
        "fetch_error": error,
        "has_pending": pending is not None,
        "needs_confirmation": pending is not None and (active is None or pending.week_start != active.week_start),
    }
