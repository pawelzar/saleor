from unittest.mock import patch

import graphene

from .....order import OrderEvents
from .....order.error_codes import OrderErrorCode
from .....order.models import OrderEvent
from ....tests.utils import get_graphql_content

ORDER_NOTE_REMOVE_MUTATION = """
    mutation removeNote($id: ID!) {
        orderNoteRemove(note: $id) {
            errors {
                field
                message
                code
            }
            order {
                id
            }
        }
    }
"""


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_remove_as_staff_user(
    order_updated_webhook_mock,
    staff_api_client,
    permission_manage_orders,
    order,
    staff_user,
):
    parameters = {"message": "a note"}
    note = OrderEvent.objects.create(
        order=order,
        type=OrderEvents.NOTE_ADDED,
        user=staff_user,
        parameters=parameters,
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    order_id = graphene.Node.to_global_id("Order", order.id)

    variables = {"id": note_id}
    response = staff_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderNoteRemove"]

    assert data["order"]["id"] == order_id
    order_updated_webhook_mock.assert_called_once_with(order)

    assert not OrderEvent.objects.filter(pk=note.pk).exists()


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_remove_fail_on_wrong_id(
    order_updated_webhook_mock,
    staff_api_client,
    permission_manage_orders,
    order,
):
    note = OrderEvent.objects.create(
        order=order,
        type=OrderEvents.UPDATED_ADDRESS,  # add different event type than NOTE_ADDED
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id}
    response = staff_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderNoteRemove"]
    assert data["errors"][0]["field"] == "id"
    assert data["errors"][0]["code"] == OrderErrorCode.NOT_FOUND.name
    order_updated_webhook_mock.assert_not_called()

    assert OrderEvent.objects.filter(pk=note.pk).exists()
