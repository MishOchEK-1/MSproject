from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory, EquipmentDowntime
from users.models import User

from .models import Reservation, ReservationStatus


class ReservationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='student-1',
            password='secure-pass-123',
            email='student1@example.com',
            full_name='Student One',
            phone='+70000000001',
        )
        self.category = EquipmentCategory.objects.create(name='Фрезеры')
        self.equipment = Equipment.objects.create(
            name='CNC 1',
            category=self.category,
            inventory_number='CNC-001',
        )

    def test_pending_reservation_gets_default_expiry(self):
        reservation = Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=2),
        )

        self.assertEqual(reservation.status, ReservationStatus.PENDING)
        self.assertIsNotNone(reservation.expires_at)

    def test_reservation_rejects_too_short_duration(self):
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, minutes=10),
        )

        with self.assertRaisesMessage(Exception, 'Минимальная длительность брони - 20 минут.'):
            reservation.full_clean()

    def test_reservation_rejects_overlap_for_same_equipment(self):
        start_at = timezone.now() + timedelta(days=2)
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            status=ReservationStatus.APPROVED,
        )
        another_user = User.objects.create_user(
            username='student-2',
            password='secure-pass-123',
            email='student2@example.com',
            full_name='Student Two',
            phone='+70000000002',
        )
        overlapping = Reservation(
            user=another_user,
            equipment=self.equipment,
            start_at=start_at + timedelta(minutes=30),
            end_at=start_at + timedelta(hours=3),
        )

        with self.assertRaisesMessage(Exception, 'Это оборудование уже забронировано на выбранное время.'):
            overlapping.full_clean()

    def test_rejected_reservation_requires_reason(self):
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
            status=ReservationStatus.REJECTED,
        )

        with self.assertRaisesMessage(Exception, 'Для отклоненной заявки нужно указать причину отказа.'):
            reservation.full_clean()

    def test_reservation_rejects_downtime_overlap(self):
        start_at = timezone.now() + timedelta(days=3)
        EquipmentDowntime.objects.create(
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            reason='Профилактика',
        )
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at + timedelta(minutes=30),
            end_at=start_at + timedelta(hours=1, minutes=30),
        )

        with self.assertRaisesMessage(Exception, 'Оборудование недоступно в выбранный период.'):
            reservation.full_clean()
