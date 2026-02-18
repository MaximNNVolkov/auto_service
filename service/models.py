from django.db import models
from cars.models import Car

class ServiceRecord(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="records")
    date = models.DateField()
    mileage = models.IntegerField()
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)

class Part(models.Model):
    service = models.ForeignKey(ServiceRecord, on_delete=models.CASCADE, related_name="parts")
    name = models.CharField(max_length=255)
    cost = models.DecimalField(max_digits=10, decimal_places=2)

    interval_km = models.IntegerField(null=True, blank=True)
    interval_months = models.IntegerField(null=True, blank=True)


class ServiceCardEntry(models.Model):
    class ElementType(models.TextChoices):
        CONSUMABLE = "consumable", "Расходник ТО"
        WORK = "work", "Работа"

    class Section(models.TextChoices):
        REGULAR = "regular", "Регулярное ТО"
        BRAKES = "brakes", "Тормозная система"
        CHASSIS = "chassis", "Ходовая и рулевое"
        EXTRA = "extra", "Дополнительные работы"
        PLAN = "plan", "План обслуживания"

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="service_card_entries")
    element_type = models.CharField(
        max_length=20,
        choices=ElementType.choices,
        default=ElementType.CONSUMABLE,
    )
    section = models.CharField(max_length=20, choices=Section.choices)
    item_name = models.CharField(max_length=255)
    service_date = models.DateField(null=True, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    interval_text = models.CharField(max_length=255, blank=True)
    forecast_text = models.CharField(max_length=255, blank=True)
    details = models.CharField(max_length=255, blank=True)
    repeatability = models.CharField(max_length=255, blank=True)
    plan_period = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("section", "-service_date", "-id")

    def __str__(self):
        return f"{self.get_section_display()}: {self.item_name}"
