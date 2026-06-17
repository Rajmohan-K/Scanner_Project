from __future__ import annotations

from typing import Any

from utils.logger import logger


def run(event_snapshot: dict[str, Any], **kwargs):
    """
    Score direct event feeds such as earnings calendar, block deals,
    institutional flows, and geopolitical event intensity.
    """

    try:
        score = 0
        reasons = []

        days_to_earnings = event_snapshot.get("days_to_earnings")
        block_deals = event_snapshot.get("block_deals", []) or []
        fii_dii = event_snapshot.get("fii_dii_flow", {}) or {}
        geo = event_snapshot.get("geopolitical_snapshot", {}) or {}

        if isinstance(days_to_earnings, int):
            if 0 <= days_to_earnings <= 3:
                score -= 8
                reasons.append("Earnings event very close")
            elif 4 <= days_to_earnings <= 10:
                score -= 3
                reasons.append("Earnings event approaching")

        deal_score = 0
        for deal in block_deals[:5]:
            side = str(deal.get("side", "unknown") or "unknown").lower()
            value = float(deal.get("value", 0) or 0)
            if side == "buy":
                deal_score += 10 if value >= 100 else 5
            elif side == "sell":
                deal_score -= 10 if value >= 100 else 5
        if deal_score > 0:
            reasons.append("Block or bulk buy support")
        elif deal_score < 0:
            reasons.append("Block or bulk sell pressure")
        score += deal_score

        fii = float(fii_dii.get("fii", 0) or 0)
        dii = float(fii_dii.get("dii", 0) or 0)
        net_flow = fii + dii
        if net_flow > 2500:
            score += 12
            reasons.append("Institutional inflow tailwind")
        elif net_flow > 800:
            score += 6
            reasons.append("Positive institutional flow")
        elif net_flow < -2500:
            score -= 12
            reasons.append("Institutional outflow pressure")
        elif net_flow < -800:
            score -= 6
            reasons.append("Negative institutional flow")

        conflict_level = float(geo.get("conflict_level", 0) or 0)
        oil_risk = float(geo.get("oil_risk", 0) or 0)
        if conflict_level >= 7 or oil_risk >= 7:
            score -= 12
            reasons.append("Geopolitical shock risk")
        elif conflict_level >= 4 or oil_risk >= 4:
            score -= 6
            reasons.append("Geopolitical risk elevated")

        return {
            "score": round(score, 2),
            "reason": ", ".join(reasons),
            "raw": {
                "days_to_earnings": days_to_earnings,
                "block_deal_count": len(block_deals),
                "fii": fii,
                "dii": dii,
                "net_flow": round(net_flow, 2),
                "conflict_level": round(conflict_level, 2),
                "oil_risk": round(oil_risk, 2),
            },
        }

    except Exception as exc:
        logger.error(f"Event impact analysis failed: {exc}")
        return {
            "score": 0,
            "reason": "Event impact error",
            "raw": {},
        }
