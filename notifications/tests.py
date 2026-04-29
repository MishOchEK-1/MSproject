from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory
from reservations.models import Reservation
from users.models import User

from .models import Notification, NotificationType


class NotificationModelTests(TestCase):
    def test_mark_as_read_sets_timestamp(self):
        user = User.objects.create_user(
            username='notify-user',
            password='secure-pass-123',
            email='notify@example.com',
            full_name='Notify User',
            phone='+70000000003',
        )
        category = EquipmentCategory.objects.create(name='Верстаки')
        equipment = Equipment.objects.create(
            name='Workbench 1',
            category=category,
            inventory_number='WB-001',
        )
        reservation = Reservation.objects.create(
            user=user,
            equipment=equipment,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
        )
        notification = Notification.objects.create(
            recipient=user,
            notification_type=NotificationType.RESERVATION_CREATED,
            title='Новая заявка',
            message='Заявка отправлена на подтверждение.',
            reservation=reservation,
        )

        notification.mark_as_read()

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
