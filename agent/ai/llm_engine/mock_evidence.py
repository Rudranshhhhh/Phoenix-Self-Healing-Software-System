"""
Phoenix LLM Engine — Mock Evidence Scenarios

Realistic MoodOS-style evidence payloads for local development and smoke testing.

Each scenario represents a common Python failure mode that could be detected
by the Phoenix monitoring agent in the sample-app / MoodOS codebase.

Usage
-----
    from agent.ai.llm_engine.mock_evidence import SCENARIOS, get_scenario

    evidence = get_scenario("type_error")   # returns EvidenceInput
    evidence = get_scenario(0)              # first scenario by index

All scenarios are also available as raw dicts via SCENARIOS_RAW so they can
be passed directly to LLMEngine.run() without importing EvidenceInput.
"""
from __future__ import annotations

from typing import Union

from agent.ai.llm_engine.diagnosis import EvidenceInput


# ============================================================================ #
# Raw scenario dicts                                                             #
# ============================================================================ #
# These mirror the exact shape that the Evidence Collection component will send.

SCENARIOS_RAW: list[dict] = [
    # ---------------------------------------------------------------------- #
    # 1. TypeError — mixing int and str in mood score calculation             #
    # ---------------------------------------------------------------------- #
    {
        "id": "type_error",
        "error_type": "TypeError",
        "error_message": "unsupported operand type(s) for +: 'int' and 'str'",
        "file": "backend/app/moods.py",
        "line": 42,
        "function_name": "calculate_mood_score",
        "relevant_code": "    score = mood_score + mood",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File \"backend/app/routes.py\", line 88, in post_mood\n"
            "    result = calculate_mood_score(mood_score, mood)\n"
            "  File \"backend/app/moods.py\", line 42, in calculate_mood_score\n"
            "    score = mood_score + mood\n"
            "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        ),
        "extra_context": {
            "service": "moodOS-backend",
            "endpoint": "POST /api/moods",
            "mood_score_type": "int",
            "mood_type": "str",
            "example_input": {"mood_score": 7, "mood": "happy"},
        },
    },

    # ---------------------------------------------------------------------- #
    # 2. KeyError — missing key in mood entry dict                            #
    # ---------------------------------------------------------------------- #
    {
        "id": "key_error",
        "error_type": "KeyError",
        "error_message": "'intensity'",
        "file": "backend/app/moods.py",
        "line": 67,
        "function_name": "process_mood_entry",
        "relevant_code": "    intensity = entry['intensity']",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File \"backend/app/routes.py\", line 101, in post_mood\n"
            "    processed = process_mood_entry(entry)\n"
            "  File \"backend/app/moods.py\", line 67, in process_mood_entry\n"
            "    intensity = entry['intensity']\n"
            "KeyError: 'intensity'"
        ),
        "extra_context": {
            "service": "moodOS-backend",
            "endpoint": "POST /api/moods",
            "received_payload": {"mood": "happy", "score": 8},
            "note": "Client submitted payload without 'intensity' field",
        },
    },

    # ---------------------------------------------------------------------- #
    # 3. AttributeError — calling method on None (uninitialized DB session)  #
    # ---------------------------------------------------------------------- #
    {
        "id": "attribute_error",
        "error_type": "AttributeError",
        "error_message": "'NoneType' object has no attribute 'query'",
        "file": "backend/app/database.py",
        "line": 31,
        "function_name": "get_mood_history",
        "relevant_code": "    results = db.query(MoodEntry).filter_by(user_id=user_id).all()",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File \"backend/app/routes.py\", line 120, in get_history\n"
            "    history = get_mood_history(user_id)\n"
            "  File \"backend/app/database.py\", line 31, in get_mood_history\n"
            "    results = db.query(MoodEntry).filter_by(user_id=user_id).all()\n"
            "AttributeError: 'NoneType' object has no attribute 'query'"
        ),
        "extra_context": {
            "service": "moodOS-backend",
            "endpoint": "GET /api/moods/history",
            "db_initialized": False,
            "note": "Database session 'db' was never assigned — init_db() not called",
        },
    },

    # ---------------------------------------------------------------------- #
    # 4. ZeroDivisionError — computing average mood with empty dataset        #
    # ---------------------------------------------------------------------- #
    {
        "id": "zero_division",
        "error_type": "ZeroDivisionError",
        "error_message": "division by zero",
        "file": "backend/app/analytics.py",
        "line": 55,
        "function_name": "compute_average_mood",
        "relevant_code": "    average = total_score / count",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File \"backend/app/routes.py\", line 145, in get_analytics\n"
            "    avg = compute_average_mood(user_id)\n"
            "  File \"backend/app/analytics.py\", line 55, in compute_average_mood\n"
            "    average = total_score / count\n"
            "ZeroDivisionError: division by zero"
        ),
        "extra_context": {
            "service": "moodOS-backend",
            "endpoint": "GET /api/analytics/average",
            "user_id": "usr_009",
            "mood_entry_count": 0,
            "note": "New user with no mood entries yet",
        },
    },

    # ---------------------------------------------------------------------- #
    # 5. ValueError — invalid mood score range from untrusted input           #
    # ---------------------------------------------------------------------- #
    {
        "id": "value_error",
        "error_type": "ValueError",
        "error_message": "invalid literal for int() with base 10: 'great'",
        "file": "backend/app/validators.py",
        "line": 19,
        "function_name": "validate_mood_score",
        "relevant_code": "    score = int(raw_score)",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            "  File \"backend/app/routes.py\", line 78, in post_mood\n"
            "    score = validate_mood_score(request.json.get('score'))\n"
            "  File \"backend/app/validators.py\", line 19, in validate_mood_score\n"
            "    score = int(raw_score)\n"
            "ValueError: invalid literal for int() with base 10: 'great'"
        ),
        "extra_context": {
            "service": "moodOS-backend",
            "endpoint": "POST /api/moods",
            "raw_score": "great",
            "note": "Client sent a string instead of an integer for mood score",
        },
    },
]


# ============================================================================ #
# Typed scenario objects                                                         #
# ============================================================================ #

# Build EvidenceInput objects from the raw dicts (strip the 'id' key)
SCENARIOS: list[EvidenceInput] = [
    EvidenceInput(**{k: v for k, v in s.items() if k != "id"})
    for s in SCENARIOS_RAW
]

# Lookup by id string
_SCENARIO_INDEX: dict[str, int] = {
    s["id"]: i for i, s in enumerate(SCENARIOS_RAW)
}


def get_scenario(key: Union[str, int]) -> EvidenceInput:
    """
    Return a mock EvidenceInput by name or index.

    Args:
        key: Scenario id string (e.g. "type_error") or integer index (0–4).

    Returns:
        EvidenceInput ready to pass to LLMEngine.run().

    Raises:
        KeyError:   If the string key does not match any scenario.
        IndexError: If the integer index is out of range.
    """
    if isinstance(key, int):
        return SCENARIOS[key]
    idx = _SCENARIO_INDEX.get(key)
    if idx is None:
        available = list(_SCENARIO_INDEX.keys())
        raise KeyError(f"Unknown scenario '{key}'. Available: {available}")
    return SCENARIOS[idx]


def list_scenarios() -> list[str]:
    """Return all available scenario id strings."""
    return list(_SCENARIO_INDEX.keys())
