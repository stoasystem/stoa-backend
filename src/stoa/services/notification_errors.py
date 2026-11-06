"""Notification refusals, from the inbox to the WebSocket channel (#211).

Raised by `stoa.services.notification_service` and
`stoa.services.websocket_service`. A caller who is not signed in, or who asks
for something that is not theirs, is refused with the security codes
(`authentication_required`, `action_not_allowed`), as everywhere else.
"""

from enum import StrEnum

from stoa.rule_violation import RuleContract, RuleViolation, register_codes


class NotificationErrorCode(StrEnum):
    NOTIFICATION_EVENT_TYPE_UNSUPPORTED = "notification_event_type_unsupported"
    NOTIFICATION_STATUS_UNSUPPORTED = "notification_status_unsupported"
    NOTIFICATION_RECIPIENT_ROLE_REQUIRED = "notification_recipient_role_required"
    NOTIFICATION_OWNER_REQUIRED = "notification_owner_required"
    NOTIFICATION_PREFERENCE_CATEGORY_UNSUPPORTED = "notification_preference_category_unsupported"
    NOTIFICATION_PREFERENCE_CHANNELS_INVALID = "notification_preference_channels_invalid"
    NOTIFICATION_PREFERENCE_CHANNEL_UNSUPPORTED = "notification_preference_channel_unsupported"
    NOTIFICATION_PREFERENCE_VALUE_INVALID = "notification_preference_value_invalid"
    PUSH_PLATFORM_UNSUPPORTED = "push_platform_unsupported"
    PUSH_TOKEN_REQUIRED = "push_token_required"
    PUSH_TOKEN_NOT_FOUND = "push_token_not_found"
    NOTIFICATION_TRANSITION_UNSUPPORTED = "notification_transition_unsupported"
    NOTIFICATION_NOT_FOUND = "notification_not_found"
    # The WebSocket channel the notifications are pushed on.
    WEBSOCKET_CONNECTION_ID_REQUIRED = "websocket_connection_id_required"
    WEBSOCKET_CHANNEL_REQUIRED = "websocket_channel_required"
    WEBSOCKET_CONNECTION_NOT_FOUND = "websocket_connection_not_found"
    NOTIFICATION_EVENT_ID_REQUIRED = "notification_event_id_required"

    @property
    def contract(self) -> RuleContract:
        return NOTIFICATION_ERROR_REGISTRY[self]


_C = NotificationErrorCode
_INPUT = RuleContract(400, "correct_input")

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.notification`).
NOTIFICATION_ERROR_REGISTRY: dict[NotificationErrorCode, RuleContract] = {
    _C.NOTIFICATION_EVENT_TYPE_UNSUPPORTED: _INPUT,
    _C.NOTIFICATION_STATUS_UNSUPPORTED: _INPUT,
    _C.NOTIFICATION_RECIPIENT_ROLE_REQUIRED: _INPUT,
    # An event about private content is stored only with the owner it belongs to.
    _C.NOTIFICATION_OWNER_REQUIRED: RuleContract(409),
    _C.NOTIFICATION_PREFERENCE_CATEGORY_UNSUPPORTED: _INPUT,
    _C.NOTIFICATION_PREFERENCE_CHANNELS_INVALID: _INPUT,
    _C.NOTIFICATION_PREFERENCE_CHANNEL_UNSUPPORTED: _INPUT,
    _C.NOTIFICATION_PREFERENCE_VALUE_INVALID: _INPUT,
    _C.PUSH_PLATFORM_UNSUPPORTED: _INPUT,
    _C.PUSH_TOKEN_REQUIRED: _INPUT,
    _C.PUSH_TOKEN_NOT_FOUND: RuleContract(404),
    _C.NOTIFICATION_TRANSITION_UNSUPPORTED: _INPUT,
    _C.NOTIFICATION_NOT_FOUND: RuleContract(404),
    _C.WEBSOCKET_CONNECTION_ID_REQUIRED: _INPUT,
    _C.WEBSOCKET_CHANNEL_REQUIRED: _INPUT,
    _C.WEBSOCKET_CONNECTION_NOT_FOUND: RuleContract(404),
    _C.NOTIFICATION_EVENT_ID_REQUIRED: _INPUT,
}

register_codes("notification", NotificationErrorCode, NOTIFICATION_ERROR_REGISTRY)


class NotificationViolation(RuleViolation):
    """A notification, preference, push token or WebSocket request was refused."""

    code: NotificationErrorCode
