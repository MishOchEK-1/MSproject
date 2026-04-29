from .models import Notification


def create_notification(*, recipient, notification_type, title, message, reservation=None, actor=None):
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        title=title,
        message=message,
        reservation=reservation,
    )
