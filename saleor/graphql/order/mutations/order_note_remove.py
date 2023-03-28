import graphene

from ....core.tracing import traced_atomic_transaction
from ....order import OrderEvents
from ....permission.enums import OrderPermissions
from ...core import ResolveInfo
from ...core.doc_category import DOC_CATEGORY_ORDERS
from ...core.mutations import BaseMutation
from ...core.types import OrderError
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import Order, OrderEvent
from .utils import get_webhook_handler_by_order_status


class OrderNoteRemove(BaseMutation):
    order = graphene.Field(Order, description="Order with the note removed.")

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
        error_type_field = "order_errors"

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, id: str
    ):
        qs = OrderEvent.get_model().objects.filter(type=OrderEvents.NOTE_ADDED)
        order_event = cls.get_node_or_error(info, id, only_type=OrderEvent, qs=qs)
        order = order_event.order
        manager = get_plugin_manager_promise(info.context).get()
        with traced_atomic_transaction():
            order_event.delete()
            func = get_webhook_handler_by_order_status(order.status, manager)
            cls.call_event(func, order)
        return OrderNoteRemove(order=order)
