import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .constants import CONSUMABLE_ITEMS, WORK_ITEMS
from .forms import EntryEditForm, WorkEntryForm
from .models import ServiceCardEntry


def _get_selected_car(request):
    """Машина из параметра ?car=<id> (только своя) или первая машина пользователя."""
    cars = request.user.car_set.order_by("id")
    car_id = request.POST.get("car") or request.GET.get("car")
    if car_id:
        if not str(car_id).isdigit():
            raise Http404("Автомобиль не найден.")
        return get_object_or_404(cars, pk=car_id), cars
    return cars.first(), cars


def _url_for_car(name, car):
    url = reverse(name)
    return f"{url}?car={car.pk}" if car else url


@login_required
def service_card_view(request):
    car, cars = _get_selected_car(request)
    custom_items_by_type, custom_sections_by_type = services.load_custom_item_maps(car)

    if car is None:
        messages.error(request, "У пользователя пока нет автомобиля.")
        work_form = WorkEntryForm()
    elif request.method == "POST":
        work_form = WorkEntryForm(request.POST, custom_items_by_type=custom_items_by_type, car=car)
        if work_form.is_valid():
            data = work_form.cleaned_data
            section = services.resolve_section(
                data["item_name"],
                data["element_type"],
                data["custom_item_name"],
                data["custom_section"],
                custom_sections_by_type,
            )
            if section:
                services.create_entry(car, section, data)
                messages.success(request, "Запись добавлена в сервисную карту.")
                return redirect(_url_for_car("service:service_card", car))
            work_form.add_error("item_name", "Не удалось определить раздел для записи.")
        messages.error(request, "Проверьте заполнение формы.")
    else:
        work_form = WorkEntryForm(custom_items_by_type=custom_items_by_type, car=car)

    return render(
        request,
        "service/service_card.html",
        {
            "car": car,
            "cars": cars,
            "sections": services.build_sections(car) if car else [],
            "work_form": work_form,
            "consumable_items_json": json.dumps(CONSUMABLE_ITEMS, ensure_ascii=False),
            "work_items_json": json.dumps(WORK_ITEMS, ensure_ascii=False),
            "custom_items_json": json.dumps(custom_items_by_type, ensure_ascii=False),
        },
    )


@login_required
def entry_list_view(request):
    car, cars = _get_selected_car(request)
    entries = []
    if car:
        entries = car.service_card_entries.exclude(section=ServiceCardEntry.Section.PLAN).order_by(
            "-service_date", "-id"
        )
    return render(request, "service/entry_list.html", {"car": car, "cars": cars, "entries": entries})


def _get_own_entry(request, pk):
    return get_object_or_404(
        ServiceCardEntry.objects.select_related("car"),
        pk=pk,
        car__owner=request.user,
    )


@login_required
def entry_edit_view(request, pk):
    entry = _get_own_entry(request, pk)
    if request.method == "POST":
        form = EntryEditForm(request.POST, instance=entry)
        if form.is_valid():
            entry = form.save()
            services.update_car_mileage(entry.car, entry.mileage)
            messages.success(request, "Запись обновлена.")
            return redirect(_url_for_car("service:entry_list", entry.car))
    else:
        form = EntryEditForm(instance=entry)
    return render(request, "service/entry_form.html", {"entry": entry, "car": entry.car, "form": form})


@login_required
@require_POST
def entry_delete_view(request, pk):
    entry = _get_own_entry(request, pk)
    car = entry.car
    entry.delete()
    messages.success(request, "Запись удалена.")
    return redirect(_url_for_car("service:entry_list", car))
