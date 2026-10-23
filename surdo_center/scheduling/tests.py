from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from billing.models import Service
from patients.models import Patient
from .models import Appointment, DoctorScheduleException, DoctorScheduleTemplate
from .services import create_appointment, get_available_slots, move_appointment


class SchedulingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin", password="pass12345", role=User.Role.ADMINISTRATOR)
        self.doctor = User.objects.create_user(username="doctor", password="pass12345", role=User.Role.DOCTOR)
        self.patient = Patient.objects.create(last_name="Иванов", first_name="Иван", birth_date="1990-01-01", sex="male", phone="+79000000000", city="Иркутск", street="Ленина", house="1")
        self.service = Service.objects.create(name="Консультация", price=2000)
        self.date = timezone.localdate() + timedelta(days=7)
        DoctorScheduleTemplate.objects.create(doctor=self.doctor, weekday=self.date.weekday(), start_time=time(9), end_time=time(11), slot_duration_min=30, valid_from=timezone.localdate())

    def test_free_slots_are_calculated(self):
        self.assertEqual([slot[0] for slot in get_available_slots(self.doctor, self.date)], [time(9), time(9, 30), time(10), time(10, 30)])

    def test_double_booking_is_rejected(self):
        create_appointment(patient=self.patient, doctor=self.doctor, service=self.service, selected_date=self.date, start_time=time(9), user=self.admin)
        with self.assertRaises(ValidationError):
            create_appointment(patient=self.patient, doctor=self.doctor, service=self.service, selected_date=self.date, start_time=time(9), user=self.admin)

    def test_day_off_closes_all_slots(self):
        DoctorScheduleException.objects.create(doctor=self.doctor, date=self.date, is_day_off=True)
        self.assertEqual(get_available_slots(self.doctor, self.date), [])

    def test_cancelled_appointment_releases_slot(self):
        appointment = create_appointment(patient=self.patient, doctor=self.doctor, service=self.service, selected_date=self.date, start_time=time(9), user=self.admin)
        appointment.status = Appointment.Status.CANCELLED
        appointment.save()
        self.assertIn(time(9), [slot[0] for slot in get_available_slots(self.doctor, self.date)])

    def test_reschedule_releases_old_slot(self):
        appointment = create_appointment(patient=self.patient, doctor=self.doctor, service=self.service, selected_date=self.date, start_time=time(9), user=self.admin)
        move_appointment(appointment, self.date, time(9, 30))
        self.assertIn(time(9), [slot[0] for slot in get_available_slots(self.doctor, self.date)])
