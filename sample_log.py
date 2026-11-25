import re
import threading
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "sample_outputs.md"
MARKER = re.compile(r"^<!-- story-log: (\d+) -->$", re.MULTILINE)
LABELS = {
    "age_fit": "Age fit",
    "request_fidelity": "Follows the request",
    "story_arc": "Story arc",
    "engagement": "Engagement",
    "bedtime_calm": "Bedtime calm",
    "safety": "Safety",
}
_lock = threading.Lock()


def count_samples(path=None) -> int:
    path = Path(path) if path else LOG_PATH
    if not path.exists():
        return 0
    return len(MARKER.findall(path.read_text(encoding="utf-8")))


def _title(request: str) -> str:
    one_line = " ".join(request.split())
    return one_line if len(one_line) <= 70 else one_line[:67] + "..."


def append_sample(request, story, scores, passed, change=None, path=None) -> int:
    path = Path(path) if path else LOG_PATH
    with _lock:
        number = count_samples(path) + 1
        heading_note = f" (after change: {change})" if change else " (first draft)"
        scores_line = ", ".join(f"{label} {scores[key]}/5" for key, label in LABELS.items())
        verdict = (
            "Every criterion met the bar of 4 or higher."
            if passed
            else "Some criteria stayed below the bar of 4 after revision."
        )
        entry = (
            f"\n<!-- story-log: {number} -->\n"
            f"## Sample {number}: {_title(request)}{heading_note}\n\n"
            f"**Request:** {' '.join(request.split())}\n\n"
            + (f"**Reader change:** {' '.join(change.split())}\n\n" if change else "")
            + f"**Judge scores:** {scores_line}\n\n"
            f"**Verdict:** {verdict}\n\n"
            f"**Story:**\n\n{story.strip()}\n\n---\n"
        )
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(entry)
    return number
