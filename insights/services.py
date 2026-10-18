"""
Hotspot detection.

Step 1 (plain database query, fast and free): find places where the SAME kind of
problem keeps coming back.
Step 2 (the "AI conclusion"): turn each hotspot into a short, plain-language
write-up with a suggested action. If an ANTHROPIC_API_KEY is set we ask the AI;
if not (or if the call fails) a built-in rule-based writer is used, so the demo
never breaks.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from reports.models import Report

from .models import Insight

CATEGORY_LABEL = dict(Report.CATEGORY_CHOICES)

# What an experienced maintenance manager would suspect, per kind of problem.
RULES = {
    ("plumbing", "indoor"): (
        "Several homes in the same block report plumbing trouble. This usually points to a shared "
        "pipe or riser problem, not separate faults inside each unit.",
        "Send a plumber to inspect the shared pipe riser and water-supply lines for this block, "
        "instead of fixing each unit one by one.",
    ),
    ("electrical", "indoor"): (
        "Repeated electrical reports in one block can mean an overloaded or ageing distribution board.",
        "Have an electrician inspect the main distribution board and wiring for this block.",
    ),
    ("pathway", "outdoor"): (
        "The same pathway keeps getting damaged. Patching is clearly not holding.",
        "Plan a proper resurfacing or base repair, and check drainage underneath. Put up a "
        "temporary detour for the elderly and wheelchair users meanwhile.",
    ),
    ("drainage", "outdoor"): (
        "Repeated drain or flooding reports at one spot suggest a blocked or undersized drain.",
        "Inspect and desilt the drain line, and check whether it needs a bigger pipe before the rainy season.",
    ),
    ("lighting", "outdoor"): (
        "Street lights here keep failing, which is a safety risk at night.",
        "Check the power feed and replace the aged fittings along this stretch in one go.",
    ),
    ("lift", "indoor"): (
        "Repeated lift faults point to a worn-out component or poor servicing.",
        "Ask the lift contractor for a full inspection and review the maintenance contract.",
    ),
}
DEFAULT_RULE = (
    "The same type of problem keeps being reported at this place, which suggests a root cause "
    "that quick fixes are not solving.",
    "Do a proper site inspection and decide between a lasting repair and an upgrade.",
)


def find_hotspots(days=60, threshold=3):
    """Group recent reports by (location, category, indoor/outdoor); keep the repeating ones."""
    since = timezone.now() - timedelta(days=days)
    rows = (
        Report.objects.filter(created_at__gte=since)
        .values("location", "location__name", "category", "scope")
        .annotate(
            total=Count("id"),
            open_count=Count("id", filter=~Q(status="resolved")),
            people=Count("reporter", distinct=True),
            first=Min("created_at"),
            last=Max("created_at"),
        )
        .filter(total__gte=threshold)
        .order_by("-total", "-last")
    )
    hotspots = []
    for r in rows:
        spots = list(
            Report.objects.filter(
                created_at__gte=since, location_id=r["location"], category=r["category"], scope=r["scope"]
            ).exclude(spot_detail="").values_list("spot_detail", flat=True)[:6]
        )
        hotspots.append(
            {
                "location_id": r["location"],
                "location": r["location__name"],
                "category": r["category"],
                "category_label": CATEGORY_LABEL.get(r["category"], r["category"]),
                "scope": r["scope"],
                "total": r["total"],
                "open_count": r["open_count"],
                "people": r["people"],
                "first": r["first"],
                "last": r["last"],
                "spots": sorted(set(spots)),
                "days": days,
                "severity": "high" if r["total"] >= threshold * 2 else "medium",
            }
        )
    return hotspots


def rule_based_writeup(h):
    summary_tail, action = RULES.get((h["category"], h["scope"]), DEFAULT_RULE)
    people = f"{h['people']} resident" + ("" if h["people"] == 1 else "s")
    summary = (
        f"{h['total']} {h['category_label'].lower()} reports at {h['location']} in the last "
        f"{h['days']} days, from {people}. {summary_tail}"
    )
    return summary, action


def ai_writeup(h):
    """Ask the AI for a conclusion. Returns (summary, action) or None if unavailable."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        facts = (
            f"Place: {h['location']}\nProblem type: {h['category_label']} "
            f"({'inside homes/buildings' if h['scope'] == 'indoor' else 'outdoor shared area'})\n"
            f"Reports in the last {h['days']} days: {h['total']} (still open: {h['open_count']})\n"
            f"Different residents reporting: {h['people']}\n"
            f"Exact spots mentioned: {', '.join(h['spots']) or 'none'}"
        )
        msg = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "You advise a township management team. Based ONLY on these facts, write:\n"
                    "1) A 2-sentence plain-language conclusion about the likely root cause.\n"
                    "2) One concrete recommended action (repair vs upgrade vs inspect).\n"
                    "Do not invent numbers. Reply in exactly this format:\n"
                    "SUMMARY: <text>\nACTION: <text>\n\n" + facts
                ),
            }],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        summary = text.split("SUMMARY:", 1)[1].split("ACTION:", 1)[0].strip()
        action = text.split("ACTION:", 1)[1].strip()
        if summary and action:
            return summary, action
    except Exception:
        pass
    return None


def refresh_insight(h):
    """Write (or rewrite) the saved conclusion for one hotspot."""
    result = ai_writeup(h)
    source = "ai"
    if result is None:
        result = rule_based_writeup(h)
        source = "rules"
    summary, action = result
    obj, _ = Insight.objects.update_or_create(
        location_id=h["location_id"], category=h["category"],
        defaults={
            "window_days": h["days"], "report_count": h["total"],
            "summary": summary, "suggested_action": action, "source": source,
        },
    )
    return obj


def hotspots_with_insights(days=60, threshold=3):
    spots = find_hotspots(days, threshold)
    saved = {(i.location_id, i.category): i for i in Insight.objects.all()}
    for h in spots:
        h["insight"] = saved.get((h["location_id"], h["category"]))
    return spots
