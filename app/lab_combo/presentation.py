"""Short Latvian public presentation for isolated Lab selections and results."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.telegram_service import TelegramMessageReceipt, TelegramService


LATVIA = ZoneInfo("Europe/Riga")
MARKET_LABELS = {
    "HOME_WIN": "Mājinieku uzvara",
    "DRAW": "Neizšķirts",
    "AWAY_WIN": "Viesu uzvara",
    "OVER_1_5": "Vairāk par 1.5 vārtiem",
    "UNDER_1_5": "Mazāk par 1.5 vārtiem",
    "OVER_2_5": "Vairāk par 2.5 vārtiem",
    "UNDER_2_5": "Mazāk par 2.5 vārtiem",
    "OVER_3_5": "Vairāk par 3.5 vārtiem",
    "UNDER_3_5": "Mazāk par 3.5 vārtiem",
    "BTTS_YES": "Abas gūs – Jā",
    "BTTS_NO": "Abas gūs – Nē",
}
OUTCOME_LABELS = {
    "WON": "✅ UZVARA",
    "LOST": "❌ ZAUDĒJUMS",
    "VOID": "⚪ ATCELTS",
    "PARTIAL_VOID": "⚪ DAĻĒJI ATCELTS",
}


@dataclass(frozen=True, slots=True)
class ResultImagePaths:
    """Optional filesystem assets; paths are never persisted in the ledger."""

    win: Path | None = None
    loss: Path | None = None
    void: Path | None = None

    @classmethod
    def from_directory(cls, directory: Path) -> "ResultImagePaths":
        return cls(directory / "win.png", directory / "loss.png", directory / "void.png")

    def available_for(self, status: str) -> Path | None:
        path = self.win if status == "WON" else self.loss if status == "LOST" else self.void
        return path if path is not None and path.is_file() else None


class LabTelegramTransport(TelegramService):
    """Lab transport extension supporting an optional result-photo caption."""

    async def send_photo_receipt(
        self,
        *,
        chat_id: str,
        image_path: Path,
        caption: str,
        timeout_seconds: float,
    ) -> TelegramMessageReceipt:
        with image_path.open("rb") as photo:
            message = await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                read_timeout=timeout_seconds,
                write_timeout=timeout_seconds,
                connect_timeout=timeout_seconds,
                pool_timeout=timeout_seconds,
            )
        message_id = getattr(message, "message_id", None)
        accepted_chat_id = getattr(message, "chat_id", None)
        if accepted_chat_id is None:
            accepted_chat_id = getattr(getattr(message, "chat", None), "id", None)
        if not isinstance(message_id, int) or accepted_chat_id is None:
            raise ValueError("Telegram response did not contain a photo receipt.")
        return TelegramMessageReceipt(message_id=message_id, chat_id=str(accepted_chat_id))


def single_message(value: dict) -> str:
    lines = [
        "🧪 GoalVision AI Lab",
        f"⚽ Mačs: {value['home_team']} – {value['away_team']}",
        f"🏆 Līga: {value['competition']}",
        f"🎯 Likme: {market_label(value['market'])}",
        f"💰 Koef.: {public_decimal(value['captured_odds'])}",
        f"⏰ Starts: {latvia_time(value['kickoff_utc'])}",
        "🔎 Pamatojums: sastāvs apstiprināts; komandas un tirgus signāli saskan.",
    ]
    confidence = value.get("experimental_confidence")
    if confidence in {"MEDIUM", "HIGH", "ELITE"}:
        lines.append(f"⭐ Pārliecība: {confidence}")
    return "\n".join(lines)


def combo_message(value: dict, number: int) -> str:
    lines = [f"🧪 GoalVision AI Lab Combo #{number}"]
    symbols = ("1️⃣", "2️⃣", "3️⃣")
    for symbol, leg in zip(symbols, value["legs"]):
        lines.append(
            f"{symbol} {leg['home_team']} – {leg['away_team']} ({leg['competition']}) "
            f"🎯 Likme: {market_label(leg['market'])} 💰 Koef.: {public_decimal(leg['captured_odds'])}"
        )
    first = min(datetime.fromisoformat(leg["kickoff_utc"]) for leg in value["legs"])
    lines.extend((
        f"🔥 Kopējais koef.: {public_decimal(value['combined_odds'])}",
        f"⏰ Pirmais starts: {first.astimezone(LATVIA).strftime('%H:%M')}",
    ))
    return "\n".join(lines)


def single_result_message(value: dict, stats: dict) -> str:
    return "\n".join((
        "🧪 GoalVision AI Lab",
        OUTCOME_LABELS[value["status"]],
        f"⚽ Mačs: {team_pair(value)}",
        f"🎯 Likme: {market_label(value['market'])}",
        f"💰 Koef.: {public_decimal(value['captured_odds'])}",
        f"📊 Rezultāts: {score(value)}",
        statistics_line("Single", stats),
    ))


def combo_result_message(value: dict, stats: dict) -> str:
    lines = ["🧪 GoalVision AI Lab Combo", OUTCOME_LABELS[value["status"]]]
    for index, leg in enumerate(value["legs"], 1):
        teams = team_pair(leg)
        lines.append(
            f"{index}. {teams} · {market_label(leg['market'])} · "
            f"{OUTCOME_LABELS[leg['outcome']]} · {score(leg)}"
        )
    lines.extend((
        f"🔥 Gala koef.: {public_decimal(value['effective_combined_odds'])}",
        statistics_line("Combo", stats),
    ))
    return "\n".join(lines)


def statistics_line(kind: str, stats: dict) -> str:
    partial = f" / PV: {stats.get('PARTIAL_VOID', 0)}" if kind == "Combo" else ""
    return (
        f"📈 {kind} statistika: ✅ W: {stats.get('WON', 0)} "
        f"❌ L: {stats.get('LOST', 0)} ⚪ Void: {stats.get('VOID', 0)}{partial} "
        f"💵 P/L: {signed_units(stats.get('hypothetical_profit_loss', 0))} "
        f"📊 ROI: {public_percent(stats.get('roi_yield'))}"
    )


def market_label(market: str) -> str:
    return MARKET_LABELS.get(market, market.replace("_", " "))


def latvia_time(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(LATVIA).strftime("%H:%M")


def public_decimal(value: object) -> str:
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return "—"


def public_percent(value: object) -> str:
    if value is None:
        return "—"
    try:
        percent = Decimal(str(value)) * Decimal(100)
        return f"{percent.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"
    except (InvalidOperation, TypeError, ValueError):
        return "—"


def signed_units(value: object) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return "—"
    sign = "+" if amount > 0 else ""
    return f"{sign}{amount}u"


def score(value: dict) -> str:
    home, away = value.get("fulltime_home"), value.get("fulltime_away")
    return f"{home}:{away}" if isinstance(home, int) and isinstance(away, int) else "—"


def team_pair(value: dict) -> str:
    home = value.get("home_team") or str(value["fixture_id"])
    away = value.get("away_team")
    return f"{home} – {away}" if away else home
