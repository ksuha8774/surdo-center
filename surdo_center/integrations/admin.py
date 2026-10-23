from django.contrib import admin

from .models import DoctorExternalMapping, ExternalBookingRequest, ExternalSystem, ServiceExternalMapping, SyncEvent


admin.site.register(ExternalSystem)
admin.site.register(DoctorExternalMapping)
admin.site.register(ServiceExternalMapping)
admin.site.register(ExternalBookingRequest)
admin.site.register(SyncEvent)
