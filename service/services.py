"""Расчёты сервисной карты и создание записей (без привязки к HTTP)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .constants import ELEMENT_TYPE_WORK, ITEM_TO_SECTION
from .models import CustomServiceItem, ServiceCardEntry

Section = ServiceCardEntry.Section

HISTORY_COLUMNS = ("Узел", "Последняя замена", "Пробег", "Интервал", "Следующая замена", "Стоимость")
PLAN_COLUMNS = ("Узел", "Следующая замена", "Ожидаемый пробег", "Прогнозная цена")

SECTION_ICONS = {
    Section.PLAN: "📅",
    Section.REGULAR: "🔧",
    Section.BRAKES: "🛞",
    Section.CHASSIS: "🛠",
    Section.EXTRA: "🔩",
}

# Разделы с историей работ, в порядке вывода. План строится из них.
HISTORY_SECTIONS = (Section.REGULAR, Section.BRAKES, Section.CHASSIS, Section.EXTRA)

YEARLY_PRICE_GROWTH = Decimal("0.15")


def section_title(section):
    return f"{SECTION_ICONS[section]} {Section(section).label}"


def empty_items_by_type():
    return {
        ServiceCardEntry.ElementType.CONSUMABLE: [],
        ServiceCardEntry.ElementType.WORK: [],
    }


def load_custom_item_maps(car):
    items_by_type = empty_items_by_type()
    sections_by_type = {
        ServiceCardEntry.ElementType.CONSUMABLE: {},
        ServiceCardEntry.ElementType.WORK: {},
    }
    if car is None:
        return items_by_type, sections_by_type
    for item in CustomServiceItem.objects.filter(car=car).order_by("name"):
        items_by_type[item.element_type].append(item.name)
        sections_by_type[item.element_type][item.name] = item.section
    return items_by_type, sections_by_type


def _average_positive_step(values):
    steps = [current - previous for previous, current in zip(values, values[1:])]
    steps = [step.days if isinstance(step, timedelta) else step for step in steps]
    steps = [step for step in steps if step > 0]
    if not steps:
        return None
    return round(sum(steps) / len(steps))


def calculate_daily_mileage(entries):
    """Средний пробег автомобиля в сутки как (км, дней) по всем записям с датой и пробегом."""
    points = sorted(
        (entry.service_date, entry.mileage)
        for entry in entries
        if entry.service_date and entry.mileage is not None
    )
    if len(points) < 2:
        return None
    (first_date, first_mileage), (last_date, last_mileage) = points[0], points[-1]
    km = last_mileage - first_mileage
    days = (last_date - first_date).days
    if km <= 0 or days <= 0:
        return None
    return km, days


def _format_interval(days, km):
    parts = []
    if days:
        parts.append(f"{days} дн.")
    if km:
        parts.append(f"{km} км")
    return " / ".join(parts)


def _build_row(item_name, entries, daily_mileage, current_mileage, today):
    entries = sorted(entries, key=lambda entry: (entry.service_date or date.min, entry.id))
    latest_entry = entries[-1]

    interval_days = _average_positive_step([e.service_date for e in entries if e.service_date])
    with_mileage = [e for e in entries if e.mileage is not None]
    interval_km = _average_positive_step([e.mileage for e in with_mileage])

    candidates = []
    if interval_days and latest_entry.service_date:
        candidates.append(latest_entry.service_date + timedelta(days=interval_days))

    next_mileage = None
    if interval_km:
        last_with_mileage = with_mileage[-1]
        next_mileage = last_with_mileage.mileage + interval_km
        if daily_mileage and last_with_mileage.service_date:
            km, days = daily_mileage
            days_by_mileage = round(interval_km * days / km)
            candidates.append(last_with_mileage.service_date + timedelta(days=days_by_mileage))

    next_date = min(candidates) if candidates else None
    overdue = bool(
        (next_date and next_date <= today)
        or (next_mileage and current_mileage is not None and current_mileage >= next_mileage)
    )

    return {
        "item_name": item_name,
        "last_date": latest_entry.service_date,
        "mileage": latest_entry.mileage,
        "interval_days": interval_days,
        "interval_km": interval_km,
        "interval_text": _format_interval(interval_days, interval_km),
        "next_date": next_date,
        "next_mileage": next_mileage,
        "overdue": overdue,
        "cost": latest_entry.cost,
    }


def build_section_rows(section_entries, daily_mileage=None, current_mileage=None, today=None):
    today = today or timezone.localdate()
    grouped_entries = defaultdict(list)
    for entry in section_entries:
        grouped_entries[entry.item_name].append(entry)

    rows = [
        _build_row(item_name, entries, daily_mileage, current_mileage, today)
        for item_name, entries in grouped_entries.items()
    ]
    rows.sort(
        key=lambda row: (row["last_date"] or date.min, row["item_name"]),
        reverse=True,
    )
    return rows


def calculate_forecast_cost(last_cost, last_date, next_date):
    if last_cost is None or last_date is None or next_date is None:
        return None

    years = max(
        0,
        next_date.year
        - last_date.year
        - (1 if (next_date.month, next_date.day) < (last_date.month, last_date.day) else 0),
    )
    multiplier = Decimal("1.00") + YEARLY_PRICE_GROWTH * Decimal(str(years))
    return (last_cost * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_plan_rows(source_rows):
    rows = []
    for row in source_rows:
        if not row.get("next_date") and not row.get("next_mileage"):
            continue
        rows.append(
            {
                "item_name": row["item_name"],
                "next_date": row["next_date"],
                "next_mileage": row["next_mileage"],
                "overdue": row["overdue"],
                "forecast_cost": calculate_forecast_cost(
                    row.get("cost"),
                    row.get("last_date"),
                    row.get("next_date"),
                ),
            }
        )

    rows.sort(key=lambda row: (row["next_date"] or date.max, row["item_name"]))
    return rows


def build_sections(car):
    """Секции сервисной карты: план первым, затем разделы с историей."""
    entries = list(car.service_card_entries.exclude(section=Section.PLAN))
    daily_mileage = calculate_daily_mileage(entries)
    today = timezone.localdate()

    history_sections = []
    all_rows = []
    for section in HISTORY_SECTIONS:
        rows = build_section_rows(
            [entry for entry in entries if entry.section == section],
            daily_mileage=daily_mileage,
            current_mileage=car.current_mileage,
            today=today,
        )
        all_rows.extend(rows)
        history_sections.append(
            {"key": section.value, "title": section_title(section), "columns": HISTORY_COLUMNS, "rows": rows}
        )

    plan_section = {
        "key": Section.PLAN.value,
        "title": section_title(Section.PLAN),
        "columns": PLAN_COLUMNS,
        "rows": build_plan_rows(all_rows),
    }
    return [plan_section, *history_sections]


def resolve_section(item_name, element_type, custom_item_name, custom_section, custom_sections_by_type):
    section = ITEM_TO_SECTION.get(item_name)
    if not section:
        section = custom_sections_by_type.get(element_type, {}).get(item_name)
    if not section and custom_item_name:
        section = custom_section
    return section or None


def update_car_mileage(car, mileage):
    if mileage is not None and mileage > car.current_mileage:
        car.current_mileage = mileage
        car.save(update_fields=["current_mileage"])


def create_entry(car, section, cleaned_data):
    element_type = cleaned_data["element_type"]
    item_name = cleaned_data["item_name"]
    create_kwargs = {
        "car": car,
        "section": section,
        "element_type": element_type,
        "item_name": item_name,
        "service_date": cleaned_data["service_date"],
        "mileage": cleaned_data["mileage"],
        "cost": cleaned_data["cost"],
    }
    if element_type == ELEMENT_TYPE_WORK:
        if section == Section.CHASSIS:
            create_kwargs["details"] = "выполнено"
            create_kwargs["repeatability"] = "разово"
        elif section == Section.EXTRA:
            create_kwargs["notes"] = "выполнено"

    entry = ServiceCardEntry.objects.create(**create_kwargs)
    update_car_mileage(car, entry.mileage)

    if cleaned_data.get("custom_item_name") and item_name not in ITEM_TO_SECTION:
        custom_item, created = CustomServiceItem.objects.get_or_create(
            car=car,
            element_type=element_type,
            name=item_name,
            defaults={"section": section},
        )
        if not created and custom_item.section != section:
            custom_item.section = section
            custom_item.save(update_fields=["section"])

    return entry
