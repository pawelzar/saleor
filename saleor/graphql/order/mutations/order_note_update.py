import graphene

from ....core.tracing import traced_atomic_transaction
from ....order import OrderEvents, events, models
from ....permission.enums import OrderPermissions
from ...app.dataloaders import get_app_promise
from ...core import ResolveInfo
from ...core.doc_category import DOC_CATEGORY_ORDERS
from ...core.types import OrderError
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import OrderEvent
from .order_note_common import OrderNoteCommon
from .utils import get_webhook_handler_by_order_status


class OrderNoteUpdate(OrderNoteCommon):
    class Arguments(OrderNoteCommon.Arguments):
        id = graphene.ID(
            required=True,
            description="ID of the note.",
            name="note",
        )

    class Meta:
        description = "Updates note of an order."
        doc_category = DOC_CATEGORY_ORDERS
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, id: str, input
    ):
        qs = models.OrderEvent.objects.filter(type=OrderEvents.NOTE_ADDED)
        order_event = cls.get_node_or_error(info, id, only_type=OrderEvent, qs=qs)
        order = order_event.order
        cleaned_input = cls.clean_input(info, order, input)
        app = get_app_promise(info.context).get()
        manager = get_plugin_manager_promise(info.context).get()
        with traced_atomic_transaction():
            event = events.order_note_updated_event(
                order=order,
                user=info.context.user,
                app=app,
                message=cleaned_input["message"],
                related_event_pk=order_event.pk,
            )
            func = get_webhook_handler_by_order_status(order.status, manager)
            cls.call_event(func, order)
        return OrderNoteUpdate(order=order, event=event)
