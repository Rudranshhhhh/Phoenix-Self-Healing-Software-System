"""
Phoenix LLM Engine — Mock LLM Client

FOR LOCAL DEVELOPMENT AND TESTING ONLY.
Does NOT call any external API. No network. No API key required.

Drop-in replacement for GroqLLMClient during local development.
Exposes exactly the same complete() interface so it can be passed directly
to generate_diagnosis(), generate_patch(), and LLMEngine without any changes
to those modules.

How it works
------------
The mock inspects the prompt text to decide which type of response to return:
  - If the prompt contains the diagnosis task marker  → returns a diagnosis JSON
  - If the prompt contains the patch task marker      → returns a patch JSON

The returned JSON values are extracted from the prompt itself wherever possible
(file path, line number, error type, relevant code) so the responses are
realistic and vary per scenario rather than returning the same hardcoded string.

Usage
-----
    from agent.ai.llm_engine.mock_client import MockLLMClient
    from agent.ai.llm_engine.diagnosis import generate_diagnosis, EvidenceInput

    client = MockLLMClient()
    evidence = EvidenceInput(
        error_type="TypeError",
        error_message="unsupported operand type(s) for +: 'int' and 'str'",
        file="backend/app/moods.py",
        line=42,
        relevant_code="    score = mood_score + mood",
    )
    result = generate_diagnosis(evidence, client)
    print(result.root_cause)

See the bottom of this file for a self-contained runnable example.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt markers written by prompts.py ─────────────────────────────────────
# These strings appear verbatim in the prompts built by build_diagnosis_prompt()
# and build_patch_prompt(). We use them to tell the two call types apart.
_DIAGNOSIS_MARKER = '"root_cause"'   # present in the diagnosis task template
_PATCH_MARKER = '"old_code"'         # present in the patch task template


# ============================================================================ #
# Helpers — extract values from the rendered prompt text                        #
# ============================================================================ #

def _extract_field(prompt: str, label: str) -> str:
    """
    Pull a single-line value from a prompt that looks like:
        File          : backend/app/moods.py
    Returns an empty string if the field is not found.
    """
    match = re.search(rf"{re.escape(label)}\s*:\s*(.+)", prompt)
    return match.group(1).strip() if match else ""


def _extract_line(prompt: str) -> int:
    """Extract the 'Line : <int>' value from the prompt."""
    raw = _extract_field(prompt, "Line")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _extract_relevant_code(prompt: str) -> str:
    """Extract 'Relevant Code : <code>' from the prompt."""
    return _extract_field(prompt, "Relevant Code")


# ============================================================================ #
# Response builders                                                              #
# ============================================================================ #

# Maps common Python exception names to short root-cause templates.
# The mock uses this so different error types produce different responses.
_ROOT_CAUSE_TEMPLATES: dict[str, str] = {
    "TypeError": (
        "A value of the wrong type was passed to an operation that does not "
        "support it, causing a TypeError at runtime."
    ),
    "KeyError": (
        "The code attempted to access a dictionary key that does not exist "
        "in the provided data, raising a KeyError."
    ),
    "AttributeError": (
        "The code called a method or accessed an attribute on an object that "
        "is None or does not define that attribute, raising an AttributeError."
    ),
    "ZeroDivisionError": (
        "The code divided a number by zero because no guard was in place for "
        "an empty or zero-valued denominator."
    ),
    "ValueError": (
        "The code passed a value in the correct type but with an unexpected "
        "format or range, raising a ValueError."
    ),
    "IndexError": (
        "The code accessed a list or sequence by an index that is out of "
        "range for the actual length of the collection."
    ),
    "NameError": (
        "The code referenced a variable or function name that has not been "
        "defined in the current scope."
    ),
    "ImportError": (
        "A required module could not be found or imported, likely because it "
        "is not installed or the module path is incorrect."
    ),
}

_EXPLANATION_TEMPLATES: dict[str, str] = {
    "TypeError": (
        "Python raises TypeError when an operation is applied to an object of "
        "an inappropriate type. In this case the relevant code combines two "
        "values where at least one has a type incompatible with the operator. "
        "The fix is to ensure both operands are of the expected type before "
        "performing the operation."
    ),
    "KeyError": (
        "Python raises KeyError when a dictionary lookup uses a key that is "
        "not present in the dictionary. The incoming data does not always "
        "include every expected field. The fix is to use .get() with a default "
        "or to validate the payload before accessing the key directly."
    ),
    "AttributeError": (
        "Python raises AttributeError when an attribute or method is accessed "
        "on an object that does not have it, often because the object is None. "
        "This usually means an initialization step was skipped or a function "
        "returned None unexpectedly. The fix is to guard against None before "
        "calling the method."
    ),
    "ZeroDivisionError": (
        "Python raises ZeroDivisionError when the right-hand side of a "
        "division is zero. This typically happens when processing an empty "
        "data set where the count variable is zero. The fix is to check "
        "whether the denominator is zero before dividing."
    ),
    "ValueError": (
        "Python raises ValueError when a function receives an argument of the "
        "correct type but an inappropriate value. Here the conversion function "
        "cannot parse the given string as the expected type. The fix is to "
        "validate or sanitize the input before conversion."
    ),
    "IndexError": (
        "Python raises IndexError when a sequence subscript is out of range. "
        "The code assumes the collection has at least a certain number of "
        "elements, but it may be empty or shorter than expected. The fix is "
        "to check the length before accessing by index."
    ),
    "NameError": (
        "Python raises NameError when a name is not found in the local or "
        "global scope. The variable was likely never assigned or was assigned "
        "in a code path that did not execute. The fix is to ensure the "
        "variable is initialized before use."
    ),
    "ImportError": (
        "Python raises ImportError when it cannot locate the specified module. "
        "This is usually caused by a missing dependency or a wrong module "
        "path. The fix is to install the package or correct the import path."
    ),
}

_PATCH_EXPLANATIONS: dict[str, str] = {
    "TypeError": (
        "Converts the operand to the correct type before the operation to "
        "prevent the TypeError."
    ),
    "KeyError": (
        "Uses dict.get() with a sensible default value so a missing key does "
        "not raise KeyError."
    ),
    "AttributeError": (
        "Adds a None guard before calling the method so AttributeError is "
        "not raised when the object is uninitialized."
    ),
    "ZeroDivisionError": (
        "Adds a zero-check on the denominator and returns a safe default "
        "value when the divisor is zero."
    ),
    "ValueError": (
        "Wraps the conversion in a try/except block and returns a default "
        "value when the input cannot be parsed."
    ),
    "IndexError": (
        "Adds a length check before index access and returns a safe default "
        "when the collection is shorter than expected."
    ),
    "NameError": (
        "Initializes the variable with a safe default value before the code "
        "path that uses it."
    ),
    "ImportError": (
        "Wraps the import in a try/except ImportError block so the failure is "
        "handled gracefully."
    ),
}

_DEFAULT_ROOT_CAUSE = (
    "An unhandled runtime exception was raised due to an unexpected input or "
    "unguarded edge case in the application code."
)
_DEFAULT_EXPLANATION = (
    "The code encountered an unexpected condition that it was not written to "
    "handle, resulting in an unhandled exception. Review the relevant code "
    "and add appropriate validation or error handling."
)
_DEFAULT_PATCH_EXPLANATION = (
    "Adds a guard condition to handle the unexpected input and prevent the "
    "runtime exception."
)


def _build_new_code(error_type: str, relevant_code: str) -> str:
    """
    Produce a plausible new_code replacement based on error type and old code.
    Keeps the same leading whitespace as the original.
    """
    indent = len(relevant_code) - len(relevant_code.lstrip())
    pad = " " * indent
    stripped = relevant_code.strip()

    if error_type == "TypeError":
        # Wrap the right-hand variable in str() or int() as appropriate
        if " + " in stripped:
            left, right = stripped.split(" + ", 1)
            return f"{pad}{left} + str({right})"
        return f"{pad}str({stripped})"

    if error_type == "KeyError":
        # Replace ['key'] with .get('key', None)
        match = re.search(r"\[(['\"][\w]+['\"])\]", stripped)
        if match:
            key = match.group(1)
            return re.sub(
                r"\[" + re.escape(match.group(1)) + r"\]",
                f".get({key})",
                f"{pad}{stripped}",
                count=1,
            )
        return f"{pad}{stripped}  # TODO: add .get() default"

    if error_type == "AttributeError":
        # Wrap in an if guard
        return (
            f"{pad}if {stripped.split('.')[0]} is not None:\n"
            f"{pad}    {stripped}"
        )

    if error_type == "ZeroDivisionError":
        # Add a denominator guard
        if " / " in stripped:
            lhs, rhs = stripped.split(" = ", 1) if " = " in stripped else ("result", stripped)
            num, den = (rhs.split(" / ", 1) if " / " in rhs else (rhs, "count"))
            return (
                f"{pad}{lhs} = {num.strip()} / {den.strip()} "
                f"if {den.strip()} != 0 else 0"
            )
        return f"{pad}{stripped} if {stripped.split('/')[-1].strip()} != 0 else 0"

    if error_type == "ValueError":
        var = stripped.split("=")[0].strip() if "=" in stripped else "value"
        return (
            f"{pad}try:\n"
            f"{pad}    {stripped}\n"
            f"{pad}except ValueError:\n"
            f"{pad}    {var} = None"
        )

    if error_type == "IndexError":
        return f"{pad}{stripped.split('[')[0].strip()} = next(iter(collection), None)"

    # Generic fallback
    return f"{pad}{stripped}  # TODO: add error handling"


# ============================================================================ #
# Response builders                                                              #
# ============================================================================ #

def _build_diagnosis_response(prompt: str) -> str:
    """Build a realistic diagnosis JSON string from the rendered prompt."""
    error_type = _extract_field(prompt, "Error Type")
    file_path   = _extract_field(prompt, "File")
    line_num    = _extract_line(prompt)

    root_cause  = _ROOT_CAUSE_TEMPLATES.get(error_type, _DEFAULT_ROOT_CAUSE)
    explanation = _EXPLANATION_TEMPLATES.get(error_type, _DEFAULT_EXPLANATION)

    response = {
        "root_cause":    root_cause,
        "explanation":   explanation,
        "affected_file": file_path or "unknown",
        "affected_line": line_num,
        "confidence":    0.92,
    }
    return json.dumps(response, indent=2)


def _build_patch_response(prompt: str) -> str:
    """Build a realistic multi-file patch JSON string from the rendered prompt.

    The mock returns a single patch (the simple-error case), in the multi-file
    envelope {"patches": [...], "explanation": ...} so it matches the current
    PatchResult schema.
    """
    error_type    = _extract_field(prompt, "Error Type")
    file_path     = _extract_field(prompt, "File")
    relevant_code = _extract_relevant_code(prompt)

    old_code = relevant_code if relevant_code not in ("(not provided)", "") else ""
    new_code = _build_new_code(error_type, old_code) if old_code else ""
    explanation = _PATCH_EXPLANATIONS.get(error_type, _DEFAULT_PATCH_EXPLANATION)

    response = {
        "patches": [
            {
                "file": file_path or "unknown",
                "old_code": old_code,
                "new_code": new_code,
            }
        ],
        "explanation": explanation,
    }
    return json.dumps(response, indent=2)


# ============================================================================ #
# MockLLMClient                                                                  #
# ============================================================================ #

class MockLLMClient:
    """
    FOR LOCAL DEVELOPMENT AND TESTING ONLY.

    Drop-in replacement for GroqLLMClient. Matches its complete() signature
    exactly so it can be passed to generate_diagnosis(), generate_patch(),
    and LLMEngine without any modifications to those modules.

    No network calls. No API key. No external dependencies.

    The response content is derived from the prompt text itself so each
    error scenario produces a distinct, realistic-looking output.
    """

    # Fake model name — visible in logs so it's obvious this is the mock
    model: str = "mock-local-v1"

    def complete(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Optional[str]:
        """
        Return a pre-built JSON string without calling any external API.

        Detects prompt type by looking for known marker strings:
          - Diagnosis prompts contain '"root_cause"' in the task section.
          - Patch prompts contain '"old_code"' in the task section.

        Args:
            user_prompt:   The formatted prompt from build_diagnosis_prompt()
                           or build_patch_prompt().
            system_prompt: Ignored — the mock does not use it.
            max_tokens:    Ignored — the mock always returns the full response.
            temperature:   Ignored — the mock is deterministic.

        Returns:
            A valid JSON string matching DiagnosisResult or PatchResult schema.
        """
        if _DIAGNOSIS_MARKER in user_prompt:
            logger.debug("MockLLMClient: returning mock diagnosis response")
            return _build_diagnosis_response(user_prompt)

        if _PATCH_MARKER in user_prompt:
            logger.debug("MockLLMClient: returning mock patch response")
            return _build_patch_response(user_prompt)

        # Unknown prompt type — log a warning and return None so upstream
        # code handles the failure path the same way it would with a real API.
        logger.warning(
            "MockLLMClient: could not determine prompt type — "
            "neither '%s' nor '%s' found in prompt",
            _DIAGNOSIS_MARKER,
            _PATCH_MARKER,
        )
        return None


# ============================================================================ #
# Runnable example (python -m agent.ai.llm_engine.mock_client)                  #
# ============================================================================ #

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    from agent.ai.llm_engine.diagnosis import EvidenceInput, generate_diagnosis
    from agent.ai.llm_engine.patch import generate_patch

    evidence = EvidenceInput(
        error_type="TypeError",
        error_message="unsupported operand type(s) for +: 'int' and 'str'",
        file="backend/app/moods.py",
        line=42,
        relevant_code="    score = mood_score + mood",
        stack_trace=(
            "  File \"backend/app/routes.py\", line 88, in post_mood\n"
            "    result = calculate_mood_score(mood_score, mood)\n"
            "  File \"backend/app/moods.py\", line 42, in calculate_mood_score\n"
            "    score = mood_score + mood\n"
            "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        ),
    )

    client = MockLLMClient()

    print("\n── DIAGNOSIS ───────────────────────────────────────────────")
    diagnosis = generate_diagnosis(evidence, client)
    if diagnosis:
        print(f"Root cause    : {diagnosis.root_cause}")
        print(f"Affected file : {diagnosis.affected_file}:{diagnosis.affected_line}")
        print(f"Confidence    : {diagnosis.confidence * 100:.0f}%")
    else:
        print("Diagnosis failed.")
        sys.exit(1)

    print("\n── PATCH ───────────────────────────────────────────────────")
    patch = generate_patch(evidence, diagnosis, client)
    if patch:
        print(f"Patches    : {len(patch.patches)}")
        for i, fp in enumerate(patch.patches, 1):
            print(f"  [{i}] File     : {fp.file}")
            print(f"      Old code : {fp.old_code}")
            print(f"      New code : {fp.new_code}")
        print(f"Why        : {patch.explanation}")
    else:
        print("Patch generation failed.")
        sys.exit(1)

    print("\n✅ MockLLMClient working correctly.")
