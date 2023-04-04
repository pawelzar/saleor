import graphene

from ....core.tracing import traced_atomic_transaction
from ....order import events
from ....permission.enums import OrderPermissions
from ...app.dataloaders import get_app_promise
from ...core import ResolveInfo
from ...core.descriptions import ADDED_IN_313, PREVIEW_FEATURE
from ...core.doc_category import DOC_CATEGORY_ORDERS
from ...core.types import OrderError
from ...plugins.dataloaders import get_plugin_manager_promise
from ..types import Order
from .order_note_common import OrderNoteCommon
from .utils import get_webhook_handler_by_order_status


class OrderNoteAdd(OrderNoteCommon):
    class Arguments(OrderNoteCommon.Arguments):
        id = graphene.ID(
            required=True,
            description="ID of the order to add a note for.",
            name="order",
        )

    class Meta:
        description = "Adds note to the order." + ADDED_IN_313 + PREVIEW_FEATURE
        doc_category = DOC_CATEGORY_ORDERS
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError

    @classmethod
    def perform_mutation(  # type: ignore[override]
        cls, _root, info: ResolveInfo, /, *, id: str, input
    ):
        order = cls.get_node_or_error(info, id, only_type=Order)
        cls.check_channel_permissions(info, [order.channel_id])
        cleaned_input = cls.clean_input(info, order, input)
        app = get_app_promise(info.context).get()
        manager = get_plugin_manager_promise(info.context).get()
        with traced_atomic_transaction():
            event = events.order_note_added_event(
                order=order,
                user=info.context.user,
                app=app,
                message=cleaned_input["message"],
            )
            func = get_webhook_handler_by_order_status(order.status, manager)
            cls.call_event(func, order)
        return OrderNoteAdd(order=order, event=event)


class OrderAddNote(OrderNoteAdd):
    class Meta:
        description = "Adds note to the order."
        doc_category = DOC_CATEGORY_ORDERS
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"
