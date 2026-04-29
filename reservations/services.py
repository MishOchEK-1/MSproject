from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_action
from notifications.models import NotificationType
from notifications.services import create_notification
from users.models import UserRole

from .models import Reservation, ReservationStatus


def sync_reservation_lifecycle():
    now = timezone.now()

    expired = Reservation.objects.filter(
        status=ReservationStatus.PENDING,
        expires_at__lt=now,
    )
    for reservation in expired:
        reservation.status = ReservationStatus.EXPIRED
        reservation.archived_at = now
        reservation.save(update_fields=['status', 'archived_at', 'updated_at'])

    completed = Reservation.objects.filter(
        status=ReservationStatus.APPROVED,
        end_at__lt=now,
    )
    for reservation in completed:
        reservation.status = ReservationStatus.COMPLETED
        reservation.completed_at = reservation.completed_at or now
        reservation.archived_at = reservation.archived_at or now
        reservation.save(update_fields=['status', 'completed_at', 'archived_at', 'updated_at'])
        create_notification(
            recipient=reservation.user,
            actor=reservation.reviewed_by,
            notification_type=NotificationType.RESERVATION_COMPLETED,
            title='Бронирование завершено',
            message=f'Бронь оборудования "{reservation.equipment.name}" завершена.',
            reservation=reservation,
        )


@transaction.atomic
def create_reservation(*, user, equipment, start_at, duration_minutes, request_comment=''):
    reservation = Reservation(
        user=user,
        equipment=equipment,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=duration_minutes),
        request_comment=request_comment,
    )
    if user.can_book_without_approval:
        reservation.status = ReservationStatus.APPROVED
        reservation.reviewed_by = user
        reservation.reviewed_at = timezone.now()
    reservation.full_clean()
    reservation.save()

    if reservation.status == ReservationStatus.PENDING:
        title = 'Новая заявка на бронирование'
        message = f'Ваша заявка на "{equipment.name}" отправлена на подтверждение.'
        notification_type = NotificationType.RESERVATION_CREATED
    else:
        title = 'Бронь подтверждена автоматически'
        message = f'Бронь оборудования "{equipment.name}" подтверждена сразу, так как у вас есть права персонала.'
        notification_type = NotificationType.RESERVATION_APPROVED

    create_notification(
        recipient=user,
        actor=user,
        notification_type=notification_type,
        title=title,
        message=message,
        reservation=reservation,
    )
    if reservation.status == ReservationStatus.PENDING:
        reviewers = get_user_model().objects.filter(role__in=[UserRole.STAFF, UserRole.ADMIN])
        for reviewer in reviewers:
            create_notification(
                recipient=reviewer,
                actor=user,
                notification_type=NotificationType.RESERVATION_CREATED,
                title='Новая заявка на подтверждение',
                message=f'Поступила новая заявка на "{equipment.name}" от пользователя {user.full_name or user.username}.',
                reservation=reservation,
            )
    log_action(
        actor=user,
        action=AuditAction.RESERVATION_CREATED,
        entity=reservation,
        description=f'Создана заявка на {equipment.name}.',
        payload={'status': reservation.status},
    )
    return reservation


@transaction.atomic
def approve_reservation(*, reservation, reviewer, staff_comment=''):
    reservation.status = ReservationStatus.APPROVED
    reservation.reviewed_by = reviewer
    reservation.reviewed_at = timezone.now()
    reservation.staff_comment = staff_comment
    reservation.rejection_reason = ''
    reservation.full_clean()
    reservation.save()

    create_notification(
        recipient=reservation.user,
        actor=reviewer,
        notification_type=NotificationType.RESERVATION_APPROVED,
        title='Заявка подтверждена',
        message=f'Заявка на "{reservation.equipment.name}" подтверждена.',
        reservation=reservation,
    )
    log_action(
        actor=reviewer,
        action=AuditAction.RESERVATION_APPROVED,
        entity=reservation,
        description=f'Заявка на {reservation.equipment.name} подтверждена.',
        payload={'staff_comment': staff_comment},
    )
    return reservation


@transaction.atomic
def reject_reservation(*, reservation, reviewer, rejection_reason, staff_comment=''):
    reservation.status = ReservationStatus.REJECTED
    reservation.reviewed_by = reviewer
    reservation.reviewed_at = timezone.now()
    reservation.rejection_reason = rejection_reason
    reservation.staff_comment = staff_comment
    reservation.archived_at = timezone.now()
    reservation.full_clean()
    reservation.save()

    create_notification(
        recipient=reservation.user,
        actor=reviewer,
        notification_type=NotificationType.RESERVATION_REJECTED,
        title='Заявка отклонена',
        message=f'Заявка на "{reservation.equipment.name}" отклонена: {rejection_reason}',
        reservation=reservation,
    )
    log_action(
        actor=reviewer,
        action=AuditAction.RESERVATION_REJECTED,
        entity=reservation,
        description=f'Заявка на {reservation.equipment.name} отклонена.',
        payload={'rejection_reason': rejection_reason, 'staff_comment': staff_comment},
    )
    return reservation


@transaction.atomic
def cancel_reservation(*, reservation, actor, reason=''):
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancellation_reason = reason
    reservation.archived_at = timezone.now()
    reservation.full_clean()
    reservation.save()

    create_notification(
        recipient=reservation.user,
        actor=actor,
        notification_type=NotificationType.RESERVATION_CANCELLED,
        title='Бронь отменена',
        message=f'Бронь на "{reservation.equipment.name}" отменена.',
        reservation=reservation,
    )
    if actor != reservation.user:
        create_notification(
            recipient=actor,
            actor=actor,
            notification_type=NotificationType.RESERVATION_CANCELLED,
            title='Выполнена экстренная отмена',
            message=f'Вы отменили бронь пользователя {reservation.user.full_name or reservation.user.username}.',
            reservation=reservation,
        )
    log_action(
        actor=actor,
        action=AuditAction.RESERVATION_CANCELLED,
        entity=reservation,
        description=f'Бронь на {reservation.equipment.name} отменена.',
        payload={'cancellation_reason': reason},
    )
    return reservation


@transaction.atomic
def extend_reservation(*, reservation, actor, extra_minutes):
    reservation.end_at = reservation.end_at + timedelta(minutes=extra_minutes)
    reservation.full_clean()
    reservation.save()
    log_action(
        actor=actor,
        action=AuditAction.RESERVATION_CREATED,
        entity=reservation,
        description=f'Бронь на {reservation.equipment.name} продлена на {extra_minutes} минут.',
        payload={'extra_minutes': extra_minutes},
    )
    return reservation
