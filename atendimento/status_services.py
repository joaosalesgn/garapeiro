from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Produto, StatusAuditEvent


@transaction.atomic
def set_product_active(*, product_id, active, actor):
    product = Produto.objects.select_for_update().get(pk=product_id)
    return _change_status(
        target=product,
        field="ativo",
        active=active,
        actor=actor,
        target_field="target_product",
    )


@transaction.atomic
def set_user_active(*, user_id, active, actor):
    User = get_user_model()
    user = User.objects.select_for_update().get(pk=user_id)

    if user.pk == actor.pk and not active:
        raise ValidationError("Você não pode inativar sua própria conta.")

    return _change_status(
        target=user,
        field="is_active",
        active=active,
        actor=actor,
        target_field="target_user",
    )


def _change_status(*, target, field, active, actor, target_field):
    if getattr(target, field) == active:
        return False

    setattr(target, field, active)
    target.save(update_fields=[field])

    StatusAuditEvent.objects.create(
        action=(
            StatusAuditEvent.Action.ACTIVATED
            if active
            else StatusAuditEvent.Action.DEACTIVATED
        ),
        actor=actor,
        **{target_field: target},
    )
    return True