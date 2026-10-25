from datetime import time, timedelta
from threading import Barrier, Thread

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Doctor, User
from billing.models import Service
from integrations.models import ExternalSystem
from patients.models import Patient
from .forms import AppointmentWizardForm
from .models import Appointment, DoctorScheduleException, DoctorScheduleTemplate
from .services import create_appointment, get_available_slots, move_appointment


class SchedulingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass12345", role=User.Role.ADMINISTRATOR)
        doctor_user = User.objects.create_user(username="doctor", password="pass12345", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=doctor_user, specialization="Сурдолог-оториноларинголог")
        self.patient = Patient.objects.create(
            last_name="Иванов", first_name="Иван", birth_date="1990-01-01", sex="male",
            phone="+79000000000", city="Иркутск", street="Ленина", house="1",
        )
        self.service = Service.objects.create(service_name="Консультация", price=2000, duration_minutes=60)
        self.date = timezone.localdate() + timedelta(days=7)
        DoctorScheduleTemplate.objects.create(
            doctor=self.doctor,
            weekday=self.date.weekday(),
            start_time=time(9),
            end_time=time(12),
            booking_step_minutes=15,
            valid_from=timezone.localdate(),
        )

    def test_doctor_and_schedule_are_created(self):
        self.assertEqual(self.doctor.user.role, User.Role.DOCTOR)
        self.assertEqual(self.doctor.schedule_templates.count(), 1)

    def test_slots_use_service_duration_and_booking_step(self):
        starts = [slot[0] for slot in get_available_slots(self.doctor, self.date, self.service)]
        self.assertEqual(starts, [time(9), time(9, 15), time(9, 30), time(9, 45), time(10), time(10, 15), time(10, 30), time(10, 45), time(11)])

    def test_multiple_breaks_are_excluded(self):
        DoctorScheduleException.objects.create(
            doctor=self.doctor, exception_date=self.date, start_time=time(10), end_time=time(10, 30), reason="Перерыв",
        )
        DoctorScheduleException.objects.create(
            doctor=self.doctor, exception_date=self.date, start_time=time(11, 15), end_time=time(11, 30), reason="Совещание",
        )
        starts = [slot[0] for slot in get_available_slots(self.doctor, self.date, self.service)]
        self.assertEqual(starts, [time(9)])

    def test_double_booking_is_rejected(self):
        create_appointment(
            patient=self.patient, doctor=self.doctor, service=self.service,
            selected_date=self.date, start_time=time(9), user=self.admin,
        )
        with self.assertRaises(ValidationError):
            create_appointment(
                patient=self.patient, doctor=self.doctor, service=self.service,
                selected_date=self.date, start_time=time(9), user=self.admin,
            )

    def test_database_constraint_rejects_partial_overlap(self):
        create_appointment(
            patient=self.patient, doctor=self.doctor, service=self.service,
            selected_date=self.date, start_time=time(9), user=self.admin,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                patient=self.patient, doctor=self.doctor, created_by=self.admin,
                planned_service=self.service, planned_price=self.service.price,
                appointment_date=self.date, start_time=time(9, 30), end_time=time(10, 30),
            )

    def test_external_booking_identity_is_unique_and_creator_can_be_empty(self):
        system = ExternalSystem.objects.create(code="yclients", name="YCLIENTS")
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, created_by=None,
            planned_service=self.service, planned_price=self.service.price,
            appointment_date=self.date, start_time=time(9), end_time=time(10),
            booking_source=Appointment.BookingSource.YCLIENTS,
            external_system=system, external_booking_id="external-100",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                patient=self.patient, doctor=self.doctor, created_by=None,
                planned_service=self.service, planned_price=self.service.price,
                appointment_date=self.date, start_time=time(10), end_time=time(11),
                booking_source=Appointment.BookingSource.YCLIENTS,
                external_system=system, external_booking_id="external-100",
            )

    def test_day_off_closes_all_slots(self):
        DoctorScheduleException.objects.create(doctor=self.doctor, exception_date=self.date, is_day_off=True)
        self.assertEqual(get_available_slots(self.doctor, self.date, self.service), [])

    def test_cancelled_appointment_releases_slot(self):
        appointment = create_appointment(
            patient=self.patient, doctor=self.doctor, service=self.service,
            selected_date=self.date, start_time=time(9), user=self.admin,
        )
        appointment.status = Appointment.Status.CANCELLED
        appointment.save(update_fields=("status", "updated_at"))
        self.assertIn(time(9), [slot[0] for slot in get_available_slots(self.doctor, self.date, self.service)])

    def test_existing_bounds_survive_service_duration_change_and_move(self):
        appointment = create_appointment(
            patient=self.patient, doctor=self.doctor, service=self.service,
            selected_date=self.date, start_time=time(9), user=self.admin,
        )
        self.service.duration_minutes = 30
        self.service.save(update_fields=("duration_minutes",))
        appointment.refresh_from_db()
        self.assertEqual((appointment.start_time, appointment.end_time), (time(9), time(10)))
        move_appointment(appointment, self.date, time(10))
        appointment.refresh_from_db()
        self.assertEqual((appointment.start_time, appointment.end_time), (time(10), time(11)))

    def test_available_slots_endpoint_uses_selected_service_duration(self):
        long_service = Service.objects.create(service_name="Расширенная диагностика", price=3000, duration_minutes=90)
        self.client.force_login(self.admin)
        url = reverse("scheduling:available_slots")
        common = {"doctor": self.doctor.pk, "date": self.date.isoformat()}

        regular = self.client.get(url, {**common, "service": self.service.pk})
        extended = self.client.get(url, {**common, "service": long_service.pk})

        self.assertEqual(regular.status_code, 200)
        self.assertEqual(extended.status_code, 200)
        self.assertEqual(regular.json()["slots"][-1], {"start": "11:00", "end": "12:00"})
        self.assertEqual(extended.json()["slots"][-1], {"start": "10:30", "end": "12:00"})

    def test_create_form_shows_service_duration(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("scheduling:create"))
        self.assertContains(response, "Консультация — 60 мин.")

    def test_create_view_rechecks_a_stale_slot(self):
        create_appointment(
            patient=self.patient, doctor=self.doctor, service=self.service,
            selected_date=self.date, start_time=time(9), user=self.admin,
        )
        self.client.force_login(self.admin)
        response = self.client.post(reverse("scheduling:create"), {
            "patient": self.patient.pk,
            "doctor": self.doctor.pk,
            "service": self.service.pk,
            "appointment_date": self.date.isoformat(),
            "slot": "09:00",
            "action": "book",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выбранный интервал уже занят или недоступен")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_archived_patient_cannot_be_selected_or_booked_with_stale_object(self):
        stale_patient = Patient.objects.get(pk=self.patient.pk)
        Patient.objects.filter(pk=self.patient.pk).update(is_archived=True, archived_at=timezone.now())

        form = AppointmentWizardForm()
        self.assertFalse(form.fields["patient"].queryset.filter(pk=self.patient.pk).exists())
        with self.assertRaisesMessage(ValidationError, "Архивного пациента нельзя записать"):
            create_appointment(
                patient=stale_patient,
                doctor=self.doctor,
                service=self.service,
                selected_date=self.date,
                start_time=time(9),
                user=self.admin,
            )
        self.assertFalse(Appointment.objects.exists())

        with self.assertRaisesMessage(ValidationError, "Архивного пациента нельзя записать"):
            Appointment.objects.create(
                patient=stale_patient,
                doctor=self.doctor,
                created_by=self.admin,
                planned_service=self.service,
                planned_price=self.service.price,
                appointment_date=self.date,
                start_time=time(9),
                end_time=time(10),
            )
        self.assertFalse(Appointment.objects.exists())

    def test_create_move_and_cancel_views_refresh_availability(self):
        self.client.force_login(self.admin)
        create_response = self.client.post(reverse("scheduling:create"), {
            "patient": self.patient.pk,
            "doctor": self.doctor.pk,
            "service": self.service.pk,
            "appointment_date": self.date.isoformat(),
            "slot": "09:00",
            "action": "book",
        })
        self.assertEqual(create_response.status_code, 302)
        appointment = Appointment.objects.get()

        move_response = self.client.post(reverse("scheduling:reschedule", args=(appointment.pk,)), {
            "appointment_date": self.date.isoformat(),
            "slot": "10:00",
            "action": "move",
        })
        self.assertEqual(move_response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual((appointment.start_time, appointment.end_time), (time(10), time(11)))

        slots_url = reverse("scheduling:available_slots")
        params = {"doctor": self.doctor.pk, "service": self.service.pk, "date": self.date.isoformat()}
        starts_after_move = {item["start"] for item in self.client.get(slots_url, params).json()["slots"]}
        self.assertIn("09:00", starts_after_move)
        self.assertNotIn("10:00", starts_after_move)

        cancel_response = self.client.post(reverse("scheduling:cancel", args=(appointment.pk,)))
        self.assertEqual(cancel_response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        starts_after_cancel = {item["start"] for item in self.client.get(slots_url, params).json()["slots"]}
        self.assertIn("10:00", starts_after_cancel)


class ConcurrentBookingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = User.objects.create_user(username="concurrent-admin", password="pass12345", role=User.Role.ADMINISTRATOR)
        doctor_user = User.objects.create_user(username="concurrent-doctor", password="pass12345", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=doctor_user)
        self.patient = Patient.objects.create(
            last_name="Петров", first_name="Пётр", birth_date="1991-01-01", sex="male",
            phone="+79000000001", city="Иркутск", street="Мира", house="2",
        )
        self.service = Service.objects.create(service_name="Диагностика", price=1500, duration_minutes=60)
        self.date = timezone.localdate() + timedelta(days=8)
        DoctorScheduleTemplate.objects.create(
            doctor=self.doctor, weekday=self.date.weekday(), start_time=time(9), end_time=time(11),
            booking_step_minutes=15, valid_from=timezone.localdate(),
        )

    def test_simultaneous_booking_creates_only_one_appointment(self):
        barrier = Barrier(2)
        results = []

        def attempt_booking():
            close_old_connections()
            try:
                patient = Patient.objects.get(pk=self.patient.pk)
                doctor = Doctor.objects.get(pk=self.doctor.pk)
                service = Service.objects.get(pk=self.service.pk)
                user = User.objects.get(pk=self.admin.pk)
                barrier.wait()
                create_appointment(
                    patient=patient, doctor=doctor, service=service,
                    selected_date=self.date, start_time=time(9), user=user,
                )
            except ValidationError:
                results.append("rejected")
            else:
                results.append("created")
            finally:
                connections.close_all()

        threads = [Thread(target=attempt_booking) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sorted(results), ["created", "rejected"])
        self.assertEqual(Appointment.objects.count(), 1)
