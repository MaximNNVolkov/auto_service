from django import forms
from django.core.validators import MinValueValidator
from django.db.models import Max, Min
from django.utils import timezone

from .constants import (
    CONSUMABLE_ITEMS,
    ELEMENT_TYPE_CHOICES,
    ELEMENT_TYPE_CONSUMABLE,
    ELEMENT_TYPE_WORK,
    WORK_ITEMS,
)
from .models import ServiceCardEntry


class EntryValidationMixin:
    """Проверки даты и пробега относительно других записей автомобиля."""

    car = None
    exclude_entry_pk = None

    def clean_service_date(self):
        service_date = self.cleaned_data["service_date"]
        if service_date and service_date > timezone.localdate():
            raise forms.ValidationError("Дата не может быть в будущем.")
        return service_date

    def _validate_mileage(self, service_date, mileage):
        if self.car is None or service_date is None or mileage is None:
            return
        entries = self.car.service_card_entries.filter(mileage__isnull=False)
        if self.exclude_entry_pk is not None:
            entries = entries.exclude(pk=self.exclude_entry_pk)
        max_before = entries.filter(service_date__lt=service_date).aggregate(value=Max("mileage"))["value"]
        min_after = entries.filter(service_date__gt=service_date).aggregate(value=Min("mileage"))["value"]
        if max_before is not None and mileage < max_before:
            self.add_error("mileage", f"Пробег меньше, чем в более ранней записи ({max_before} км).")
        elif min_after is not None and mileage > min_after:
            self.add_error("mileage", f"Пробег больше, чем в более поздней записи ({min_after} км).")


def _date_widget():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class WorkEntryForm(EntryValidationMixin, forms.Form):
    CUSTOM_SECTION_CHOICES = [
        choice for choice in ServiceCardEntry.Section.choices if choice[0] != ServiceCardEntry.Section.PLAN
    ]

    element_type = forms.ChoiceField(
        label="Тип элемента",
        choices=ELEMENT_TYPE_CHOICES,
        initial=ELEMENT_TYPE_CONSUMABLE,
    )
    item_name = forms.ChoiceField(
        label="Выберите расходник/Работу",
        choices=(),
    )
    custom_item_name = forms.CharField(
        label="Свой пункт",
        max_length=255,
        required=False,
    )
    custom_section = forms.ChoiceField(
        label="Раздел для нового пункта",
        choices=CUSTOM_SECTION_CHOICES,
        required=False,
    )
    service_date = forms.DateField(
        label="Дата выполнения",
        widget=_date_widget(),
    )
    mileage = forms.IntegerField(
        label="Пробег (км)",
        min_value=0,
    )
    cost = forms.DecimalField(
        label="Стоимость (руб.)",
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )

    def __init__(self, *args, **kwargs):
        custom_items_by_type = kwargs.pop("custom_items_by_type", None)
        self.car = kwargs.pop("car", None)
        super().__init__(*args, **kwargs)
        self.fields["service_date"].initial = timezone.localdate
        self.custom_items_by_type = custom_items_by_type or {
            ELEMENT_TYPE_CONSUMABLE: [],
            ELEMENT_TYPE_WORK: [],
        }
        selected_type = (
            self.data.get("element_type")
            or self.initial.get("element_type")
            or ELEMENT_TYPE_CONSUMABLE
        )
        self.fields["item_name"].choices = self._choices_for_type(selected_type)
        self.fields["custom_item_name"].widget.attrs.setdefault(
            "placeholder", "Например: Замена лампы ближнего света"
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    def _choices_for_type(self, element_type):
        base_items = WORK_ITEMS if element_type == ELEMENT_TYPE_WORK else CONSUMABLE_ITEMS
        custom_items = self.custom_items_by_type.get(element_type, [])
        merged_items = list(dict.fromkeys([*base_items, *custom_items]))
        return [(item, item) for item in merged_items]

    @staticmethod
    def _normalize_name(value):
        return " ".join((value or "").split())

    def clean_custom_item_name(self):
        return self._normalize_name(self.cleaned_data.get("custom_item_name"))

    def clean(self):
        cleaned_data = super().clean()
        element_type = cleaned_data.get("element_type")
        item_name = self._normalize_name(cleaned_data.get("item_name"))
        custom_item_name = cleaned_data.get("custom_item_name")
        resolved_item_name = custom_item_name or item_name

        allowed_values = {value for value, _ in self._choices_for_type(element_type)}

        if resolved_item_name not in allowed_values and not custom_item_name:
            raise forms.ValidationError("Некорректный выбор элемента.")
        if custom_item_name and custom_item_name not in allowed_values and not cleaned_data.get("custom_section"):
            self.add_error("custom_section", "Укажите раздел для нового пункта.")

        self._validate_mileage(cleaned_data.get("service_date"), cleaned_data.get("mileage"))

        cleaned_data["item_name"] = resolved_item_name
        return cleaned_data


class EntryEditForm(EntryValidationMixin, forms.ModelForm):
    class Meta:
        model = ServiceCardEntry
        fields = ("service_date", "mileage", "cost")
        labels = {
            "service_date": "Дата выполнения",
            "mileage": "Пробег (км)",
            "cost": "Стоимость (руб.)",
        }
        widgets = {"service_date": _date_widget()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.car = self.instance.car
        self.exclude_entry_pk = self.instance.pk
        self.fields["service_date"].required = True
        self.fields["cost"].validators.append(MinValueValidator(0))
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    def clean(self):
        cleaned_data = super().clean()
        self._validate_mileage(cleaned_data.get("service_date"), cleaned_data.get("mileage"))
        return cleaned_data
