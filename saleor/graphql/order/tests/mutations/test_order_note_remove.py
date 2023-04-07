from unittest.mock import patch

import graphene

from .....order import OrderEvents
from .....order.error_codes import OrderErrorCode
from .....order.models import OrderEvent
from ....tests.utils import assert_no_permission, get_graphql_content

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
            event {
                id
                user {
                    email
                }
                relatedOrderEvent {
                    id
                }
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
    # given
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

    # when
    response = staff_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["orderNoteRemove"]

    assert data["order"]["id"] == order_id
    assert data["event"]["user"]["email"] == staff_user.email
    assert data["event"]["relatedOrderEvent"]["id"] == note_id
    order_updated_webhook_mock.assert_called_once_with(order)

    assert OrderEvent.objects.filter(order=order).count() == 2
    new_note = OrderEvent.objects.filter(order=order).exclude(pk=note.pk).get()
    assert new_note.type == OrderEvents.NOTE_REMOVED
    assert new_note.user == staff_user


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_remove_as_app(
    order_updated_webhook_mock,
    app_api_client,
    permission_manage_orders,
    order,
    app,
):
    # given
    parameters = {"message": "a note"}
    note = OrderEvent.objects.create(
        order=order,
        type=OrderEvents.NOTE_ADDED,
        parameters=parameters,
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    order_id = graphene.Node.to_global_id("Order", order.id)

    variables = {"id": note_id}

    # when
    response = app_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["orderNoteRemove"]

    assert data["order"]["id"] == order_id
    assert data["event"]["user"] is None
    assert data["event"]["relatedOrderEvent"]["id"] == note_id
    order_updated_webhook_mock.assert_called_once_with(order)

    assert OrderEvent.objects.filter(order=order).count() == 2
    new_note = OrderEvent.objects.filter(order=order).exclude(pk=note.pk).get()
    assert new_note.type == OrderEvents.NOTE_REMOVED
    assert new_note.app == app
    assert not new_note.user


@patch("saleor.plugins.manager.PluginsManager.order_updated")
def test_order_note_remove_fail_on_wrong_id(
    order_updated_webhook_mock,
    staff_api_client,
    permission_manage_orders,
    order,
):
    # given
    note = OrderEvent.objects.create(
        order=order,
        type=OrderEvents.UPDATED_ADDRESS,  # add different event type than NOTE_ADDED
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id}

    # when
    response = staff_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["orderNoteRemove"]
    assert data["errors"][0]["field"] == "id"
    assert data["errors"][0]["code"] == OrderErrorCode.NOT_FOUND.name
    order_updated_webhook_mock.assert_not_called()

    assert OrderEvent.objects.filter(pk=note.pk).exists()


def test_order_note_remove_fail_on_missing_permission(staff_api_client, order):
    # given
    note = OrderEvent.objects.create(order=order, type=OrderEvents.NOTE_ADDED)
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id}

    # when
    response = staff_api_client.post_graphql(ORDER_NOTE_REMOVE_MUTATION, variables)

    # then
    assert_no_permission(response)


def test_order_note_remove_fail_on_note_already_removed(
    staff_api_client, permission_manage_orders, order
):
    # given
    note = OrderEvent.objects.create(order=order, type=OrderEvents.NOTE_ADDED)
    parameters = {"related_event_pk": note.pk}
    OrderEvent.objects.create(
        order=order, type=OrderEvents.NOTE_REMOVED, parameters=parameters
    )
    note_id = graphene.Node.to_global_id("OrderEvent", note.pk)
    variables = {"id": note_id}

    # when
    response = staff_api_client.post_graphql(
        ORDER_NOTE_REMOVE_MUTATION, variables, permissions=[permission_manage_orders]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    data = content["data"]["orderNoteRemove"]
    assert data["errors"][0]["field"] == "id"
    assert data["errors"][0]["code"] == OrderErrorCode.INVALID.name
    assert data["errors"][0]["message"] == "The order note was already removed."
