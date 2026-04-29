from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory, EquipmentDowntime
from notifications.models import Notification
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


class ReservationFlowTests(TestCase):
    def setUp(self):
        self.category = EquipmentCategory.objects.create(name='Лазерные станки')
        self.equipment = Equipment.objects.create(
            name='Laser X',
            category=self.category,
            inventory_number='LAS-001',
            requires_training=True,
            slot_duration_minutes=60,
        )
        self.student = User.objects.create_user(
            username='flow-student',
            password='secure-pass-123',
            email='student-flow@edu.omsk.ru',
            full_name='Flow Student',
            phone='+70000000040',
            role='student',
            has_completed_training=True,
        )
        self.staff = User.objects.create_user(
            username='flow-staff',
            password='secure-pass-123',
            email='staff-flow@edu.omsk.ru',
            full_name='Flow Staff',
            phone='+70000000041',
            role='staff',
        )
        self.guest = User.objects.create_user(
            username='flow-guest',
            password='secure-pass-123',
            email='guest-flow@example.com',
            full_name='Flow Guest',
            phone='+70000000042',
            role='guest',
        )

    def test_student_reservation_goes_to_pending(self):
        self.client.force_login(self.student)
        start_at = (timezone.localtime(timezone.now()) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': 'Нужен рез для проекта',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment)
        self.assertEqual(reservation.status, ReservationStatus.PENDING)
        self.assertGreaterEqual(Notification.objects.filter(reservation=reservation).count(), 2)

    def test_staff_reservation_is_auto_approved(self):
        self.client.force_login(self.staff)
        start_at = (timezone.localtime(timezone.now()) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.staff, equipment=self.equipment)
        self.assertEqual(reservation.status, ReservationStatus.APPROVED)
        self.assertEqual(reservation.reviewed_by, self.staff)

    def test_guest_without_training_cannot_book_training_equipment(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse('reservations:create', args=[self.equipment.pk]))

        self.assertRedirects(response, reverse('equipment:detail', args=[self.equipment.pk]))

    def test_owner_can_cancel_reservation(self):
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('reservations:cancel', args=[reservation.pk]),
            {'cancellation_reason': 'Планы изменились'},
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, ReservationStatus.CANCELLED)

    def test_owner_can_extend_reservation_when_slot_is_free(self):
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
            status=ReservationStatus.APPROVED,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('reservations:extend', args=[reservation.pk]),
            {'extra_minutes': 60},
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation.refresh_from_db()
        self.assertEqual(reservation.duration_minutes, 120)

    def test_staff_can_approve_pending_reservation(self):
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
            status=ReservationStatus.PENDING,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('reservations:approve', args=[reservation.pk]),
            {'staff_comment': 'Все в порядке'},
        )

        self.assertRedirects(response, reverse('reservations:staff-dashboard'))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, ReservationStatus.APPROVED)

    def test_staff_rejection_requires_reason(self):
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
            status=ReservationStatus.PENDING,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('reservations:reject', args=[reservation.pk]),
            {'staff_comment': 'Недостаточно данных', 'rejection_reason': ''},
        )

        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, ReservationStatus.PENDING)

    def test_guest_cannot_open_staff_dashboard(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse('reservations:staff-dashboard'))

        self.assertEqual(response.status_code, 403)
