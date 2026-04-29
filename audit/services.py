from .models import AuditLog


def log_action(*, actor, action, entity, description, payload=None):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        entity_type=entity.__class__.__name__.lower(),
        entity_id=entity.pk,
        entity_label=str(entity),
        description=description,
        payload=payload or {},
    )
