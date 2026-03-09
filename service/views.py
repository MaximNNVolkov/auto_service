import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .constants import (
    CONSUMABLE_ITEMS,
    ELEMENT_TYPE_WORK,
    ITEM_TO_SECTION,
    WORK_ITEMS,
)
from .forms import WorkEntryForm
from .models import CustomServiceItem, ServiceCardEntry

SECTION_CONFIG = {
    "plan": {
        "section": ServiceCardEntry.Section.PLAN,
        "title": "📅 План обслуживания",
        "columns": ("Узел", "Следующая замена", "Прогнозная цена"),
    },
    "regular": {
        "section": ServiceCardEntry.Section.REGULAR,
        "title": "🔧 Регулярное ТО",
        "columns": ("Узел", "Последняя замена", "Пробег", "Интервал", "Следующая замена", "Стоимость"),
    },
    "brakes": {
        "section": ServiceCardEntry.Section.BRAKES,
        "title": "🛞 Тормозная система",
        "columns": ("Узел", "Последняя замена", "Пробег", "Интервал", "Следующая замена", "Стоимость"),
    },
    "chassis": {
        "section": ServiceCardEntry.Section.CHASSIS,
        "title": "🛠 Ходовая и рулевое",
        "columns": ("Узел", "Последняя замена", "Пробег", "Интервал", "Следующая замена", "Стоимость"),
    },
    "extra": {
        "section": ServiceCardEntry.Section.EXTRA,
        "title": "🔩 Дополнительные работы",
        "columns": ("Узел", "Последняя замена", "Пробег", "Интервал", "Следующая замена", "Стоимость"),
    },
}


def _empty_custom_items_by_type():
    return {
        ServiceCardEntry.ElementType.CONSUMABLE: [],
        ServiceCardEntry.ElementType.WORK: [],
    }


def _load_custom_item_maps(car):
    items_by_type = _empty_custom_items_by_type()
    sections_by_type = {
        ServiceCardEntry.ElementType.CONSUMABLE: {},
        ServiceCardEntry.ElementType.WORK: {},
    }
    for item in CustomServiceItem.objects.filter(car=car).order_by("name"):
        items_by_type[item.element_type].append(item.name)
        sections_by_type[item.element_type][item.name] = item.section
    return items_by_type, sections_by_type


def _calculate_average_interval_days(entries):
    dated_entries = [entry for entry in entries if entry.service_date]
    if len(dated_entries) < 2:
        return None

    intervals = []
    for previous, current in zip(dated_entries, dated_entries[1:]):
        diff = (current.service_date - previous.service_date).days
        if diff > 0:
            intervals.append(diff)

    if not intervals:
        return None

    return round(sum(intervals) / len(intervals))


def _build_section_rows(section_entries):
    grouped_entries = defaultdict(list)
    for entry in section_entries:
        grouped_entries[entry.item_name].append(entry)

    rows = []
    for item_name, entries in grouped_entries.items():
        entries = sorted(
            entries,
            key=lambda entry: (
                entry.service_date or timezone.datetime.min.date(),
                entry.id,
            ),
        )
        latest_entry = entries[-1]
        average_days = _calculate_average_interval_days(entries)
        interval_text = f"{average_days} дн." if average_days else ""
        next_date = (
            latest_entry.service_date + timedelta(days=average_days)
            if average_days and latest_entry.service_date
            else None
        )
        rows.append(
            {
                "item_name": item_name,
                "last_date": latest_entry.service_date,
                "mileage": latest_entry.mileage,
                "interval_days": average_days,
                "interval_text": interval_text,
                "next_date": next_date,
                "cost": latest_entry.cost,
            }
        )

    rows.sort(
        key=lambda row: (row["last_date"] or timezone.datetime.min.date(), row["item_name"]),
        reverse=True,
    )
    return rows


def _calculate_forecast_cost(last_cost, last_date, next_date):
    if last_cost is None or last_date is None or next_date is None:
        return None

    years = max(
        0,
        next_date.year
        - last_date.year
        - (1 if (next_date.month, next_date.day) < (last_date.month, last_date.day) else 0),
    )
    multiplier = Decimal("1.00") + Decimal("0.15") * Decimal(str(years))
    return (last_cost * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _build_plan_rows(source_rows):
    rows = []
    for row in source_rows:
        if not row.get("interval_days") or not row.get("next_date"):
            continue
        rows.append(
            {
                "item_name": row["item_name"],
                "next_date": row["next_date"],
                "forecast_cost": _calculate_forecast_cost(
                    row.get("cost"),
                    row.get("last_date"),
                    row.get("next_date"),
                ),
            }
        )

    rows.sort(key=lambda row: row["next_date"])
    return rows


@login_required
def service_card_view(request):
    car = request.user.car_set.order_by("id").first()
    custom_items_by_type = _empty_custom_items_by_type()
    custom_sections_by_type = {
        ServiceCardEntry.ElementType.CONSUMABLE: {},
        ServiceCardEntry.ElementType.WORK: {},
    }
    if not car:
        messages.error(request, "У пользователя пока нет автомобиля.")
        return render(
            request,
            "service/service_card.html",
            {
                "car": None,
                "sections": [],
                "work_form": WorkEntryForm(),
                "consumable_items_json": json.dumps(CONSUMABLE_ITEMS, ensure_ascii=False),
                "work_items_json": json.dumps(WORK_ITEMS, ensure_ascii=False),
                "custom_items_json": json.dumps(custom_items_by_type, ensure_ascii=False),
            },
        )
    custom_items_by_type, custom_sections_by_type = _load_custom_item_maps(car)

    if request.method == "POST":
        work_form = WorkEntryForm(
            request.POST,
            custom_items_by_type=custom_items_by_type,
        )
        if work_form.is_valid():
            element_type = work_form.cleaned_data["element_type"]
            item_name = work_form.cleaned_data["item_name"]
            custom_item_name = work_form.cleaned_data["custom_item_name"]
            custom_section = work_form.cleaned_data["custom_section"]
            mileage = work_form.cleaned_data["mileage"]
            cost = work_form.cleaned_data["cost"]
            section = ITEM_TO_SECTION.get(item_name)
            if not section:
                section = custom_sections_by_type.get(element_type, {}).get(item_name)
            if not section and custom_item_name:
                section = custom_section

            if not section:
                work_form.add_error("item_name", "Не удалось определить раздел для записи.")
            else:
                create_kwargs = {
                    "car": car,
                    "section": section,
                    "element_type": element_type,
                    "item_name": item_name,
                    "service_date": timezone.localdate(),
                    "mileage": mileage,
                    "cost": cost,
                }
                if element_type == ELEMENT_TYPE_WORK:
                    if section == ServiceCardEntry.Section.CHASSIS:
                        create_kwargs["details"] = "выполнено"
                        create_kwargs["repeatability"] = "разово"
                    elif section == ServiceCardEntry.Section.EXTRA:
                        create_kwargs["notes"] = "выполнено"

                ServiceCardEntry.objects.create(
                    **create_kwargs,
                )

                if custom_item_name and item_name not in ITEM_TO_SECTION:
                    custom_item, created = CustomServiceItem.objects.get_or_create(
                        car=car,
                        element_type=element_type,
                        name=item_name,
                        defaults={"section": section},
                    )
                    if not created and custom_item.section != section:
                        custom_item.section = section
                        custom_item.save(update_fields=["section"])

                messages.success(request, "Запись добавлена в сервисную карту.")
                return redirect("service:service_card")

        messages.error(request, "Проверьте заполнение формы.")
    else:
        work_form = WorkEntryForm(custom_items_by_type=custom_items_by_type)

    entries = ServiceCardEntry.objects.filter(car=car)
    sections = []
    interval_rows_for_plan = []
    section_rows_map = {}
    for key, config in SECTION_CONFIG.items():
        if key == "plan":
            continue

        section_entries = list(
            entries.filter(section=config["section"]).order_by("item_name", "service_date", "id")
        )
        section_rows = _build_section_rows(section_entries)
        interval_rows_for_plan.extend(section_rows)
        section_rows_map[key] = section_rows

    plan_rows = _build_plan_rows(interval_rows_for_plan)
    for key, config in SECTION_CONFIG.items():
        rows = plan_rows if key == "plan" else section_rows_map.get(key, [])
        sections.append(
            {
                "key": key,
                "title": config["title"],
                "columns": config["columns"],
                "rows": rows,
            }
        )

    return render(
        request,
        "service/service_card.html",
        {
            "car": car,
            "sections": sections,
            "work_form": work_form,
            "consumable_items_json": json.dumps(CONSUMABLE_ITEMS, ensure_ascii=False),
            "work_items_json": json.dumps(WORK_ITEMS, ensure_ascii=False),
            "custom_items_json": json.dumps(custom_items_by_type, ensure_ascii=False),
        },
    )
