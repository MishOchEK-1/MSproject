from django.test import TestCase

from .models import User, UserRole


class UserModelTests(TestCase):
    def test_user_role_defaults_to_guest(self):
        user = User.objects.create_user(
            username='guest-user',
            password='secure-pass-123',
            email='guest@example.com',
            full_name='Guest User',
            phone='+70000000000',
        )

        self.assertEqual(user.role, UserRole.GUEST)
        self.assertFalse(user.has_completed_training)
