from reservations.models import Reservation


def can_view_schedule(user):
    return bool(user and user.is_authenticated and user.can_view_schedule())


def can_view_reservation_owner(user, reservation):
    return bool(user and user.is_authenticated and user.can_view_reservation_owner(reservation))


def can_review_reservation(user, reservation=None):
    return bool(user and user.is_authenticated and user.can_review_reservations)


def can_force_cancel_reservation(user, reservation):
    return bool(user and user.is_authenticated and user.can_force_cancel_reservations)


def can_cancel_reservation(user, reservation):
    if not user or not user.is_authenticated:
        return False
    if reservation.user_id == user.pk:
        return reservation.status in Reservation.ACTIVE_STATUSES
    return can_force_cancel_reservation(user, reservation)


def can_manage_user_role(actor, target=None):
    return bool(actor and actor.is_authenticated and actor.can_manage_users)


def can_manage_training_status(actor, target=None):
    return bool(actor and actor.is_authenticated and actor.can_manage_training)


def reservation_requires_manual_approval(user):
    if not user or not user.is_authenticated:
        return True
    return not user.can_book_without_approval


def get_reservation_owner_label(viewer, reservation):
    if can_view_reservation_owner(viewer, reservation):
        return reservation.user.full_name or reservation.user.username
    return 'Скрыто'
