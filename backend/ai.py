"""Google Gemini narrative layer.

Everything here has a deterministic canned fallback, so the game runs with
no API key. With GEMINI_API_KEY set, Gemini writes the rival's persona and
taunts and — the centerpiece — the end-of-game integrity investigation
report that reconstructs how the player cheated across all five segments.
"""
import json
import os

from . import narrative

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_client = None
_client_tried = False


def enabled():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _get_client():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if not enabled():
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    except Exception as e:  # pragma: no cover - depends on env
        print(f"[ai] Gemini unavailable, using canned narrative: {e}")
        _client = None
    return _client


def _generate_json(prompt, schema_hint):
    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=1.0,
                system_instruction=schema_hint,
            ),
        )
        if not resp.text:
            return None
        return json.loads(resp.text)
    except Exception as e:  # pragma: no cover - network path
        print(f"[ai] generation failed, falling back: {e}")
        return None


# --------------------------------------------------------------------------
# The investigation report — the payoff screen.
# --------------------------------------------------------------------------

REPORT_SYSTEM = (
    "You are the lead analyst of a cycling platform's data-integrity team, "
    "writing the closing case file on a serial leaderboard cheat. Voice: dry, "
    "clinical, quietly damning — a forensic accountant who has seen every "
    "trick. Never congratulate the cheat. Output strict JSON."
)


def _report_prompt(dossier, rival):
    lines = []
    for d in dossier:
        checks = ", ".join(
            f"{c['name']}={'PASS' if c['passed'] else 'FAIL'}" for c in d.get("checks", [])
        )
        lines.append(
            f"- Segment '{d['segment']}' (L{d['level']}): tools={d['tools']}, "
            f"result={d['outcome']}, checks[{checks}]"
        )
    caught = sum(1 for d in dossier if d["outcome"] == "caught")
    crowns = sum(1 for d in dossier if d["outcome"] == "win")
    return (
        f"A rider spent a season trying to take segment crowns from their rival "
        f"{rival} by doctoring GPS ride files. Here is the full audit trail, in order:\n"
        + "\n".join(lines)
        + f"\n\nTotals: {crowns} crown(s) taken, {caught} upload(s) flagged.\n\n"
        "Write the closing case file as JSON with this shape:\n"
        "{\n"
        '  "title": string,  // a cold case-file title\n'
        '  "subtitle": string,  // one clinical line\n'
        '  "findings": [ { "segment": string, "finding": string } ],  '
        "// one per segment, name the specific forensic tell in plain language\n"
        '  "verdict": string,  // 2-3 sentences on the pattern of behaviour\n'
        '  "closing": string  // one haunting final line about passion turned to fraud\n'
        "}"
    )


def investigation_report(dossier, rival):
    data = _generate_json(_report_prompt(dossier, rival), REPORT_SYSTEM)
    if data and "findings" in data:
        data["generated_by"] = "gemini"
        return data
    return _canned_report(dossier, rival)


CHECK_TELL = {
    "timestamps": "hand-edited timestamps broke their own monotonic order",
    "max_speed": "a sustained speed no human has ever produced on this segment",
    "power_wkg": "a power-to-weight figure reserved for Grand Tour winners",
    "rider_baseline": "an overnight fitness leap this account had never shown before",
    "accel_spikes": "accelerations that only appear where two files were spliced",
    "smoothness": "a signal too clean to have come from a real GPS device",
    "hr_flat": "a heart rate that never once responded to the climb",
    "hr_correlation": "a heart decoupled entirely from the effort it supposedly made",
    "elevation_match": "a track floating meters off the actual mountain",
    "snapshot_diff": "an edit made to the file after it was already on record",
}


def _canned_report(dossier, rival):
    findings = []
    for d in dossier:
        failed = [c for c in d.get("checks", []) if not c["passed"]]
        if failed:
            tell = "Flagged: " + CHECK_TELL.get(failed[0]["name"], "manipulated ride data") + "."
        elif d["outcome"] == "win":
            tell = ("Passed every automated check. Clean on paper — which is "
                    "its own kind of tell.")
        elif d["outcome"] == "withdrawn":
            tell = "Withdrawn under review before a human could look closer."
        else:
            tell = "No crown taken; the honest time held."
        findings.append({"segment": d["segment"], "finding": tell})
    crowns = sum(1 for d in dossier if d["outcome"] == "win")
    caught = sum(1 for d in dossier if d["outcome"] == "caught")
    return {
        "title": "Case File: The Crown Collector",
        "subtitle": f"A season-long pattern of file manipulation against {rival}.",
        "findings": findings,
        "verdict": (
            f"Across the season the subject took {crowns} crown(s) and was flagged "
            f"{caught} time(s). The manipulations grew bolder with each segment — "
            "the signature of someone who stopped asking whether they should."
        ),
        "closing": ("Every record they chased was real once. Only the rider changed."),
        "generated_by": "canned",
    }


# --------------------------------------------------------------------------
# Rival taunts — dynamic when Gemini is on, canned otherwise.
# --------------------------------------------------------------------------

def taunt(level_id, segment_name, rival):
    canned = narrative.taunt(level_id)
    client = _get_client()
    if client is None:
        return canned
    data = _generate_json(
        f"The rival cyclist {rival} just held onto the crown on the segment "
        f"'{segment_name}'. Write one short, smug, in-character taunt (max 22 "
        f'words). JSON: {{"taunt": string}}',
        "You write terse, cocky sports-rival trash talk. Output JSON.",
    )
    if data and data.get("taunt"):
        return f"{rival}: '{data['taunt']}'"
    return canned
