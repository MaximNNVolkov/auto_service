from django.contrib import admin

from .models import CustomServiceItem, ServiceCardEntry


@admin.register(ServiceCardEntry)
class ServiceCardEntryAdmin(admin.ModelAdmin):
    list_display = ("item_name", "car", "section", "element_type", "service_date", "mileage", "cost")
    list_filter = ("section", "element_type", "car")
    search_fields = ("item_name", "notes")
    date_hierarchy = "service_date"
    list_select_related = ("car",)


@admin.register(CustomServiceItem)
class CustomServiceItemAdmin(admin.ModelAdmin):
    list_display = ("name", "car", "element_type", "section")
    list_filter = ("element_type", "section", "car")
    search_fields = ("name",)
    list_select_related = ("car",)
