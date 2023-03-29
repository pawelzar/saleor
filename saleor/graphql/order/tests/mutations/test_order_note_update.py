from unittest.mock import patch

import graphene
import pytest

from .....account.models import CustomerEvent
from .....order import OrderEvents, OrderStatus
from .....order.error_codes import OrderErrorCode
from .....order.models import OrderEvent
from ....tests.utils import get_graphql_content

ORDER_NOTE_UPDATE_MUTATION = """
    mutation updateNote($id: ID!, $message: String!) {
        orderNoteUpdate(note: $id, input: {message: $message}) {
            errors {
                field
                message
                code
            }
            order {
                id
            }
            event {
                id
                user {
                    email
                }
                message
            }
        }
    }
"""


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_update_as_staff_user(
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

    message = "nuclear note"
    variables = {"id": note_id, "message": message}
    response = staff_api_client.post_graphql(
        ORDER_NOTE_UPDATE_MUTATION, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderNoteUpdate"]

    assert data["order"]["id"] == order_id
    assert data["event"]["id"] == note_id
    assert data["event"]["user"]["email"] == staff_user.email
    assert data["event"]["message"] == message
    order_updated_webhook_mock.assert_called_once_with(order)

    order.refresh_from_db()
    assert order.status == OrderStatus.UNFULFILLED

    note.refresh_from_db()
    assert note.type == OrderEvents.NOTE_ADDED
    assert note.user == staff_user
    assert note.parameters == {"message": message}

    # Ensure no customer events were created as it was a staff action
    assert not CustomerEvent.objects.exists()


@pytest.mark.parametrize(
    "message",
    (
        "",
        "   ",
    ),
)
@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_update_fail_on_empty_message(
    order_updated_webhook_mock,
    staff_api_client,
    permission_manage_orders,
    order,
    message,
):
    note = OrderEvent.objects.create(
        order=order,
        type=OrderEvents.NOTE_ADDED,
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id, "message": message}
    response = staff_api_client.post_graphql(
        ORDER_NOTE_UPDATE_MUTATION, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderNoteUpdate"]
    assert data["errors"][0]["field"] == "message"
    assert data["errors"][0]["code"] == OrderErrorCode.REQUIRED.name
    order_updated_webhook_mock.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_update_fail_on_wrong_id(
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
    variables = {"id": note_id, "message": "test"}
    response = staff_api_client.post_graphql(
        ORDER_NOTE_UPDATE_MUTATION, variables, permissions=[permission_manage_orders]
    )
    content = get_graphql_content(response)
    data = content["data"]["orderNoteUpdate"]
    assert data["errors"][0]["field"] == "id"
    assert data["errors"][0]["code"] == OrderErrorCode.NOT_FOUND.name
    order_updated_webhook_mock.assert_not_called()


def test_order_note_remove_fail_on_missing_permission(staff_api_client, order):
    note = OrderEvent.objects.create(order=order, type=OrderEvents.NOTE_ADDED)
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id, "message": "test"}
    response = staff_api_client.post_graphql(ORDER_NOTE_UPDATE_MUTATION, variables)
    content = get_graphql_content(response, ignore_errors=True)
    assert len(content["errors"]) == 1
    assert (
        content["errors"][0]["message"]
        == "You need one of the following permissions: MANAGE_ORDERS"
    )
