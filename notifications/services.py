from audit.models import AuditAction
from audit.services import log_action

from .models import Notification


def create_notification(*, recipient, notification_type, title, message, reservation=None, actor=None):
    notification = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        title=title,
        message=message,
        reservation=reservation,
    )
    log_action(
        actor=actor,
        action=AuditAction.NOTIFICATION_CREATED,
        entity=notification,
        description=f'Создано уведомление "{title}" для пользователя {recipient.full_name or recipient.username}.',
        payload={'notification_type': notification_type},
    )
    return notification
