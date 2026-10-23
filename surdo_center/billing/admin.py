from django.contrib import admin

from .models import Payment, ProvidedService, Service


admin.site.register(Service)
admin.site.register(ProvidedService)
admin.site.register(Payment)
