from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory, EquipmentDowntime
from notifications.models import Notification, NotificationType
from users.models import User

from .models import Reservation, ReservationStatus


def make_local_datetime(*, day_offset=1, hour=10, minute=0):
    target_day = timezone.localdate() + timedelta(days=day_offset)
    return timezone.make_aware(datetime.combine(target_day, time(hour=hour, minute=minute)))


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
        start_at = make_local_datetime(day_offset=1, hour=10)
        reservation = Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
        )

        self.assertEqual(reservation.status, ReservationStatus.PENDING)
        self.assertIsNotNone(reservation.expires_at)

    def test_reservation_rejects_too_short_duration(self):
        start_at = make_local_datetime(day_offset=1, hour=10)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=10),
        )

        with self.assertRaisesMessage(Exception, 'Минимальная длительность брони для этого оборудования - 60 минут.'):
            reservation.full_clean()

    def test_reservation_allows_exact_slot_even_when_not_multiple_of_ten(self):
        self.equipment.slot_duration_minutes = 45
        self.equipment.save(update_fields=['slot_duration_minutes'])
        start_at = make_local_datetime(day_offset=1, hour=10)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=45),
        )

        reservation.full_clean()

    def test_reservation_rejects_duration_above_slot_when_not_multiple_of_ten(self):
        self.equipment.slot_duration_minutes = 45
        self.equipment.save(update_fields=['slot_duration_minutes'])
        start_at = make_local_datetime(day_offset=1, hour=10)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=55),
        )

        with self.assertRaisesMessage(Exception, 'Если длительность больше базового слота, она должна быть кратна 10 минутам.'):
            reservation.full_clean()

    def test_reservation_rejects_overlap_for_same_equipment(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
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

    def test_reservation_rejects_overlap_with_pending_reservation(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            status=ReservationStatus.PENDING,
        )
        another_user = User.objects.create_user(
            username='student-3',
            password='secure-pass-123',
            email='student3@example.com',
            full_name='Student Three',
            phone='+70000000003',
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
        start_at = make_local_datetime(day_offset=1, hour=10)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.REJECTED,
        )

        with self.assertRaisesMessage(Exception, 'Для отклоненной заявки нужно указать причину отказа.'):
            reservation.full_clean()

    def test_reservation_rejects_downtime_overlap(self):
        start_at = make_local_datetime(day_offset=3, hour=10)
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

    def test_reservation_rejects_start_before_nine(self):
        start_at = make_local_datetime(day_offset=1, hour=8, minute=59)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
        )

        with self.assertRaisesMessage(Exception, 'Начать бронь можно только с 09:00 до 19:00. Завершение может быть позже 19:00.'):
            reservation.full_clean()

    def test_reservation_allows_start_at_nineteen_and_end_after_nineteen(self):
        start_at = make_local_datetime(day_offset=1, hour=19, minute=0)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
        )

        reservation.full_clean()

    def test_reservation_rejects_start_after_nineteen(self):
        start_at = make_local_datetime(day_offset=1, hour=19, minute=1)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
        )

        with self.assertRaisesMessage(Exception, 'Начать бронь можно только с 09:00 до 19:00. Завершение может быть позже 19:00.'):
            reservation.full_clean()

    def test_reservation_rejects_start_outside_twenty_minute_step(self):
        start_at = make_local_datetime(day_offset=1, hour=9, minute=7)
        reservation = Reservation(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
        )

        with self.assertRaisesMessage(Exception, 'Время старта должно быть с шагом 20 минут: 09:00, 09:20, 09:40 и далее.'):
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
            email='student-flow@auca.kg',
            full_name='Flow Student',
            phone='+70000000040',
            role='student',
            has_completed_training=True,
        )
        self.staff = User.objects.create_user(
            username='flow-staff',
            password='secure-pass-123',
            email='staff-flow@tsiauca.kg',
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
        start_at = make_local_datetime(day_offset=1, hour=10)
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

    def test_pending_user_notification_includes_date_time_and_duration(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=10)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 70,
                'request_comment': 'Нужен рез для проекта',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment)
        user_notification = Notification.objects.get(
            recipient=self.student,
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CREATED,
        )
        self.assertIn('Дата:', user_notification.message)
        self.assertIn(start_at.strftime('%d.%m.%Y'), user_notification.message)
        self.assertIn('Время: 10:00-11:10.', user_notification.message)
        self.assertIn('Длительность: 1 ч 10 мин.', user_notification.message)

    def test_pending_reviewer_notification_includes_date_time_and_duration(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=19)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment, start_at=start_at)
        reviewer_notification = Notification.objects.get(
            recipient=self.staff,
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CREATED,
        )
        self.assertIn('Дата:', reviewer_notification.message)
        self.assertIn(start_at.strftime('%d.%m.%Y'), reviewer_notification.message)
        self.assertIn('Время: 19:00-20:00.', reviewer_notification.message)
        self.assertIn('Длительность: 1 ч.', reviewer_notification.message)
        self.assertIn(self.student.full_name, reviewer_notification.message)

    def test_pending_notification_adds_explicit_end_datetime_when_reservation_crosses_midnight(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=19)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 360,
                'request_comment': '',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment, start_at=start_at)
        user_notification = Notification.objects.get(
            recipient=self.student,
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CREATED,
        )
        reviewer_notification = Notification.objects.get(
            recipient=self.staff,
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CREATED,
        )
        expected_end = (start_at + timedelta(hours=6)).strftime('%d.%m.%Y %H:%M')
        self.assertIn('Время: 19:00-01:00.', user_notification.message)
        self.assertIn(f'Окончание: {expected_end}.', user_notification.message)
        self.assertIn(f'Окончание: {expected_end}.', reviewer_notification.message)
        self.assertIn('Длительность: 6 ч.', user_notification.message)

    def test_staff_reservation_is_auto_approved(self):
        self.client.force_login(self.staff)
        start_at = make_local_datetime(day_offset=1, hour=11)
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

    def test_create_reservation_rejects_duration_less_than_slot(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=10)
        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 50,
                'request_comment': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Минимальная длительность брони для этого оборудования - 60 минут.')

    def test_create_reservation_accepts_duration_above_slot_when_multiple_of_ten(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=10)
        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 70,
                'request_comment': 'Нужно чуть больше времени',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment)
        self.assertEqual(reservation.duration_minutes, 70)

    def test_guest_without_training_cannot_book_training_equipment(self):
        self.client.force_login(self.guest)
        response = self.client.get(reverse('reservations:create', args=[self.equipment.pk]))

        self.assertRedirects(response, reverse('equipment:detail', args=[self.equipment.pk]))

    def test_owner_can_cancel_reservation(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
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
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('reservations:extend', args=[reservation.pk]),
            {'extra_minutes': 10},
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation.refresh_from_db()
        self.assertEqual(reservation.duration_minutes, 70)

    def test_owner_cannot_extend_reservation_to_non_multiple_duration_above_slot(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )
        self.client.force_login(self.student)
        response = self.client.post(
            reverse('reservations:extend', args=[reservation.pk]),
            {'extra_minutes': 5},
        )

        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.duration_minutes, 60)
        self.assertContains(response, 'Убедитесь, что это значение больше либо равно 10.')

    def test_reservation_create_form_uses_ten_minute_step(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse('reservations:create', args=[self.equipment.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="start_at"')
        self.assertContains(response, 'step="1200"')
        self.assertContains(response, 'name="duration_minutes"')
        self.assertContains(response, 'step="10"')

    def test_reservation_extend_form_uses_ten_minute_step(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.APPROVED,
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse('reservations:extend', args=[reservation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="extra_minutes"')
        self.assertContains(response, 'step="10"')

    def test_staff_can_approve_pending_reservation(self):
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
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
        start_at = make_local_datetime(day_offset=2, hour=10)
        reservation = Reservation.objects.create(
            user=self.student,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
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

    def test_create_reservation_rejects_start_before_nine(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=8, minute=59)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Начать бронь можно только с 09:00 до 19:00. Завершение может быть позже 19:00.')

    def test_create_reservation_allows_start_at_nineteen_and_end_later(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=19, minute=0)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertRedirects(response, reverse('reservations:list'))
        reservation = Reservation.objects.get(user=self.student, equipment=self.equipment, start_at=start_at)
        self.assertEqual(reservation.end_at, start_at + timedelta(hours=1))

    def test_create_reservation_rejects_start_after_nineteen(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=19, minute=1)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Начать бронь можно только с 09:00 до 19:00. Завершение может быть позже 19:00.')

    def test_create_reservation_rejects_start_outside_twenty_minute_step(self):
        self.client.force_login(self.student)
        start_at = make_local_datetime(day_offset=1, hour=9, minute=7)

        response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': start_at.strftime('%Y-%m-%dT%H:%M'),
                'duration_minutes': 60,
                'request_comment': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Время старта должно быть с шагом 20 минут: 09:00, 09:20, 09:40 и далее.')


class ReservationListViewTests(TestCase):
    def setUp(self):
        self.category = EquipmentCategory.objects.create(name='Токарные станки')
        self.equipment = Equipment.objects.create(
            name='Lathe 1',
            category=self.category,
            inventory_number='LAT-001',
            requires_training=False,
        )
        self.user = User.objects.create_user(
            username='calendar-user',
            password='secure-pass-123',
            email='calendar@example.com',
            full_name='Calendar User',
            phone='+70000000090',
        )

    def test_reservation_list_renders_week_calendar_with_actions(self):
        target_day = timezone.localdate() + timedelta(days=1)
        start_at = timezone.make_aware(datetime.combine(target_day, time(hour=11, minute=0)))
        reservation = Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.PENDING,
            request_comment='Нужна настройка под деталь',
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('reservations:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Календарь недели')
        self.assertContains(response, 'Lathe 1')
        self.assertContains(response, '11:00 - 12:00')
        self.assertContains(response, 'Нужна настройка под деталь')
        self.assertContains(response, reverse('reservations:extend', args=[reservation.pk]))
        self.assertContains(response, reverse('reservations:cancel', args=[reservation.pk]))

    def test_reservation_list_supports_week_navigation(self):
        today = timezone.localdate()
        target_day = today + timedelta(days=10)
        target_start = timezone.make_aware(datetime.combine(target_day, time(hour=15, minute=0)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=target_start,
            end_at=target_start + timedelta(hours=2),
            status=ReservationStatus.APPROVED,
        )
        week_param = (target_day - timedelta(days=target_day.weekday())).strftime('%Y-%m-%d')
        self.client.force_login(self.user)

        response = self.client.get(reverse('reservations:list'), {'week': week_param})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target_day.strftime('%d.%m.%Y'))
        self.assertContains(response, '15:00 - 17:00')

    def test_reservation_list_wraps_week_grid_in_horizontal_scroller(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('reservations:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reservation-calendar__board-wrap')
        self.assertContains(response, 'reservation-calendar__board')

    def test_reservation_list_shows_cross_midnight_reservation_on_both_days(self):
        target_day = timezone.localdate() + timedelta(days=2)
        start_at = timezone.make_aware(datetime.combine(target_day, time(hour=19, minute=0)))
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=5, minutes=30),
            status=ReservationStatus.APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('reservations:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target_day.strftime('%d.%m.%Y'))
        self.assertContains(response, (target_day + timedelta(days=1)).strftime('%d.%m.%Y'))
        self.assertContains(response, '19:00 - 00:30', count=2)

    def test_reservation_list_keeps_history_separate(self):
        start_at = make_local_datetime(day_offset=-3, hour=10)
        Reservation.objects.create(
            user=self.user,
            equipment=self.equipment,
            start_at=start_at,
            end_at=start_at + timedelta(hours=1),
            status=ReservationStatus.CANCELLED,
            archived_at=timezone.now(),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('reservations:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'История')
        self.assertContains(response, ReservationStatus.CANCELLED.label)


class ReservationEndToEndTests(TestCase):
    def setUp(self):
        self.category = EquipmentCategory.objects.create(name='Фрезеры ЧПУ')
        self.equipment = Equipment.objects.create(
            name='CNC E2E',
            category=self.category,
            inventory_number='E2E-001',
            requires_training=True,
            slot_duration_minutes=60,
        )
        self.user = User.objects.create_user(
            username='e2e-student',
            password='secure-pass-123',
            email='e2e-student@auca.kg',
            full_name='E2E Student',
            phone='+70000000110',
            role='student',
            has_completed_training=True,
        )

    def test_student_can_book_from_schedule_and_see_reservation_in_calendar(self):
        selected_day = timezone.localdate() + timedelta(days=1)
        self.client.force_login(self.user)

        schedule_response = self.client.get(
            reverse('equipment:schedule'),
            {'date': selected_day.strftime('%Y-%m-%d')},
        )
        booking_url = f'{reverse("reservations:create", args=[self.equipment.pk])}?start_at={selected_day.strftime("%Y-%m-%d")}T09:00'
        self.assertEqual(schedule_response.status_code, 200)
        self.assertContains(schedule_response, booking_url)
        self.assertNotContains(schedule_response, f'{reverse("reservations:create", args=[self.equipment.pk])}?start_at={selected_day.strftime("%Y-%m-%d")}T00:00')

        form_response = self.client.get(
            reverse('reservations:create', args=[self.equipment.pk]),
            {'start_at': f'{selected_day.strftime("%Y-%m-%d")}T09:00'},
        )
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, f'value="{selected_day.strftime("%Y-%m-%d")}T09:00"')

        create_response = self.client.post(
            reverse('reservations:create', args=[self.equipment.pk]),
            {
                'start_at': f'{selected_day.strftime("%Y-%m-%d")}T09:00',
                'duration_minutes': 60,
                'request_comment': 'Сквозной сценарий бронирования',
            },
        )
        self.assertRedirects(create_response, reverse('reservations:list'))

        reservation = Reservation.objects.get(user=self.user, equipment=self.equipment)
        self.assertEqual(reservation.status, ReservationStatus.PENDING)

        calendar_response = self.client.get(reverse('reservations:list'))
        self.assertEqual(calendar_response.status_code, 200)
        self.assertContains(calendar_response, 'CNC E2E')
        self.assertContains(calendar_response, '09:00 - 10:00')
        self.assertContains(calendar_response, 'Сквозной сценарий бронирования')
        self.assertContains(calendar_response, ReservationStatus.PENDING.label)
