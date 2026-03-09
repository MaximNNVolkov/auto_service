from django import forms

from .constants import (
    CONSUMABLE_ITEMS,
    ELEMENT_TYPE_CHOICES,
    ELEMENT_TYPE_CONSUMABLE,
    ELEMENT_TYPE_WORK,
    WORK_ITEMS,
)
from .models import ServiceCardEntry


class WorkEntryForm(forms.Form):
    CUSTOM_SECTION_CHOICES = (
        (ServiceCardEntry.Section.REGULAR, "Регулярное ТО"),
        (ServiceCardEntry.Section.BRAKES, "Тормозная система"),
        (ServiceCardEntry.Section.CHASSIS, "Ходовая и рулевое"),
        (ServiceCardEntry.Section.EXTRA, "Дополнительные работы"),
    )

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
        super().__init__(*args, **kwargs)
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

        cleaned_data["item_name"] = resolved_item_name
        return cleaned_data
