from django.contrib import admin
from .models import Part, ServiceCardEntry, ServiceRecord

admin.site.register(ServiceRecord)
admin.site.register(Part)
admin.site.register(ServiceCardEntry)
