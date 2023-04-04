import graphene
from django.core.exceptions import ValidationError

from ....core.tracing import traced_atomic_transaction
from ....order import OrderEvents, events, models
from ....order.error_codes import OrderErrorCode
from ....permission.enums import OrderPermissions
from ...app.dataloaders import get_app_promise
from ...core import ResolveInfo
from ...core.doc_category import DOC_CATEGORY_ORDERS
from ...core.types import OrderError
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import OrderEvent
from .order_note_common import OrderNoteCommon
from .utils import get_webhook_handler_by_order_status


class OrderNoteRemove(OrderNoteCommon):
    class Arguments:
        id = graphene.ID(
            required=True,
            description="ID of the note.",
            name="note",
        )

    class Meta:
        description = "Removes note from an order."
        doc_category = DOC_CATEGORY_ORDERS
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError

    @classmethod
    def validate_event_not_removed(cls, order_event_id: int):
        if models.OrderEvent.objects.filter(
            type=OrderEvents.NOTE_REMOVED, parameters__related_event_pk=order_event_id
        ).exists():
            raise ValidationError(
                {
                    "id": ValidationError(
                        "The order note was already removed.",
                        code=OrderErrorCode.INVALID.value,
                    )
                }
            )

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, id: str
    ):
        qs = models.OrderEvent.objects.filter(type=OrderEvents.NOTE_ADDED)
        order_event = cls.get_node_or_error(info, id, only_type=OrderEvent, qs=qs)
        cls.validate_event_not_removed(order_event.pk)
        order = order_event.order
        app = get_app_promise(info.context).get()
        manager = get_plugin_manager_promise(info.context).get()
        with traced_atomic_transaction():
            event = events.order_note_removed_event(
                order=order,
                user=info.context.user,
                app=app,
                related_event_pk=order_event.pk,
            )
            func = get_webhook_handler_by_order_status(order.status, manager)
            cls.call_event(func, order)
        return OrderNoteRemove(order=order, event=event)
