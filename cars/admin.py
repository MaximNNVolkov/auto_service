from django.contrib import admin

from .models import Car


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("__str__", "year", "vin", "current_mileage", "owner")
    list_filter = ("brand",)
    search_fields = ("brand", "model", "vin", "owner__username")
    list_select_related = ("owner",)
