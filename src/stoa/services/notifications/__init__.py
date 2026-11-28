"""Notifications: one package with two doors (#638, #686).

**The "something happened" door.** A caller builds one happening and hands it to
`happened`:

    notifications.happened(notifications.TeacherReplied(conversation=..., teacher_id=..., reply_id=...))

It says only what happened. The package decides the rest from the happening's
kind: what the bell row says and in whose language, its category, which
channels it goes out on (bell, realtime, push, email), which of those the
reader can switch off, and the one fixed id the happening has. The same
happening told twice is stored and sent once, on every channel. `happened`
never raises; building a happening raises only for what the caller got wrong.

Two kinds go out by email (#687): an offer to a teacher (beside its bell row)
and a parent's weekly report (by email only). The package reads the reader's
switch, adds the unsubscribe line and headers, and sends once; for a weekly
report `happened` says what became of the email (`EmailResult`), which the
report service records.

**The reader door.** The bell list and its marks, the preferences and the
unsubscribe link, the push devices, the admin list and delivery status, the one
rule for who may see a notification, and the few rows authorization and
account deletion load.

Nothing outside this package imports `notification_repo` or a module of this
package other than the package itself (`tests/test_notification_package_boundary.py`).
`websocket_service` keeps the connections and never imports this package;
realtime is a channel in here (`_realtime`).
"""

from stoa.services.notifications._account_data import (
    DELIVERY_INTENT_ENTITY,
    get_event,
    get_push_token,
    scan_notification_private_rows,
    scrub_notification_identity_references,
    scrub_notification_private_row,
)
from stoa.services.notifications._bell import (
    delivery_status,
    list_admin_events,
    list_user_events,
    mark_authorized_event,
)
from stoa.services.notifications._common import visible_to_user
from stoa.services.notifications._email import EmailOutcome, EmailResult
from stoa.services.notifications._happenings import (
    OFFER_STATES,
    Happening,
    HelpOfferClosed,
    HelpOffered,
    HelpRequestExpired,
    ModerationCaseOpened,
    ModerationCaseUpdated,
    SubscriptionRequestChanged,
    TeacherPausedAfterLapse,
    TeacherReplied,
    TeacherTookHelpRequest,
    WeeklyReportReady,
)
from stoa.services.notifications._preferences import (
    preferences_response,
    set_email_subscription,
    update_preferences,
)
from stoa.services.notifications._push import register_push_token, revoke_authorized_push_token
from stoa.services.notifications._tell import happened

__all__ = [
    # "something happened"
    "happened",
    "Happening",
    "HelpOfferClosed",
    "HelpOffered",
    "HelpRequestExpired",
    "ModerationCaseOpened",
    "ModerationCaseUpdated",
    "OFFER_STATES",
    "SubscriptionRequestChanged",
    "TeacherPausedAfterLapse",
    "TeacherReplied",
    "TeacherTookHelpRequest",
    "WeeklyReportReady",
    "EmailOutcome",
    "EmailResult",
    # the reader
    "delivery_status",
    "list_admin_events",
    "list_user_events",
    "mark_authorized_event",
    "preferences_response",
    "register_push_token",
    "revoke_authorized_push_token",
    "set_email_subscription",
    "update_preferences",
    "visible_to_user",
    # authorization and account deletion
    "DELIVERY_INTENT_ENTITY",
    "get_event",
    "get_push_token",
    "scan_notification_private_rows",
    "scrub_notification_identity_references",
    "scrub_notification_private_row",
]
