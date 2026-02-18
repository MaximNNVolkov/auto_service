from django import forms

from .constants import (
    CONSUMABLE_ITEMS,
    ELEMENT_TYPE_CHOICES,
    ELEMENT_TYPE_CONSUMABLE,
    ELEMENT_TYPE_WORK,
    WORK_ITEMS,
)


class WorkEntryForm(forms.Form):
    element_type = forms.ChoiceField(
        label="Тип элемента",
        choices=ELEMENT_TYPE_CHOICES,
        initial=ELEMENT_TYPE_CONSUMABLE,
    )
    item_name = forms.ChoiceField(
        label="Выберите расходник/Работу",
        choices=(),
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
        super().__init__(*args, **kwargs)
        selected_type = (
            self.data.get("element_type")
            or self.initial.get("element_type")
            or ELEMENT_TYPE_CONSUMABLE
        )
        self.fields["item_name"].choices = self._choices_for_type(selected_type)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input")

    @staticmethod
    def _choices_for_type(element_type):
        items = WORK_ITEMS if element_type == ELEMENT_TYPE_WORK else CONSUMABLE_ITEMS
        return [(item, item) for item in items]

    def clean_item_name(self):
        element_type = self.cleaned_data.get("element_type")
        item_name = self.cleaned_data.get("item_name")
        allowed_values = {value for value, _ in self._choices_for_type(element_type)}
        if item_name not in allowed_values:
            raise forms.ValidationError("Некорректный выбор элемента.")
        return item_name
