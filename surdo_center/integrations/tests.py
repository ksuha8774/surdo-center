from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import ExternalBookingRequest, ExternalSystem, SyncEvent


class IntegrationPreparationTests(TestCase):
    def setUp(self):
        self.system = ExternalSystem.objects.create(code="yclients", name="YCLIENTS")

    def test_repeated_external_booking_is_idempotent(self):
        request, created = ExternalBookingRequest.objects.get_or_create(
            external_system=self.system,
            external_booking_id="booking-42",
            defaults={"client_name": "Клиент", "phone": "+79000000003"},
        )
        repeated, repeated_created = ExternalBookingRequest.objects.get_or_create(
            external_system=self.system,
            external_booking_id="booking-42",
            defaults={"client_name": "Дубликат"},
        )
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(request.pk, repeated.pk)

    def test_external_event_id_is_unique_within_system(self):
        SyncEvent.objects.create(
            external_system=self.system, external_event_id="event-1",
            entity_type="appointment", direction=SyncEvent.Direction.INBOUND,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SyncEvent.objects.create(
                external_system=self.system, external_event_id="event-1",
                entity_type="appointment", direction=SyncEvent.Direction.INBOUND,
            )
