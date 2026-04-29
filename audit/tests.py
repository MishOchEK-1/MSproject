from django.test import TestCase

from users.models import User

from .models import AuditAction, AuditLog


class AuditLogModelTests(TestCase):
    def test_payload_defaults_to_empty_dict(self):
        actor = User.objects.create_user(
            username='audit-user',
            password='secure-pass-123',
            email='audit@example.com',
            full_name='Audit User',
            phone='+70000000004',
        )
        log = AuditLog.objects.create(
            actor=actor,
            action=AuditAction.RESERVATION_CREATED,
            entity_type='reservation',
            entity_id=1,
            description='Создана новая заявка на бронирование.',
        )

        self.assertEqual(log.payload, {})
