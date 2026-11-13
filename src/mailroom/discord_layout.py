"""The checkpoint 1 message, its answered form, the replies and the title form.

`mailroom.checkpoint` builds the message from these. A button's `custom_id` is
`<PREFIX>:<action>:<item id>`; Phase 1i reads it back, so the actions and the prefix never change.
Email-derived text is shown only inside code blocks, where Discord renders no formatting, links or
mentions, with each backtick replaced so the text can't close the block.
"""

API_URL = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (mailroom, {version})"
TOKEN_NAME = "discord.bot-token"
NONCE_LENGTH = 25
LINK_LIMIT = 512

PREFIX = "mr"
# (action, label, style). Styles: 1 primary, 2 secondary, 3 success, 4 danger.
FIRST_ROW = (
    ("full", "Show full text", 2),
    ("yes", "Yes", 3),
    ("edit", "Edit title", 1),
    ("notask", "Not a task", 2),
)
SECOND_ROW = (
    ("mute", "Mute sender", 4),
    ("trust", "Trust sender", 2),
)
OPEN_LABEL = "Open email"
LINK_STYLE = 5

TITLE = "Is this a task?"
COLOR_NORMAL = 0x5865F2
COLOR_SUSPECTED = 0xED4245
COLOR_UNREAD = 0x99AAB5

FROM_NAME = "From"
SUBJECT_NAME = "Subject"
SUMMARY_NAME = "Summary"
TASK_NAME = "Proposed task"
WARNING_NAME = "Suspected spam or phishing"

NO_ADDRESS = "(no address)"
NO_SUBJECT = "(no subject)"
UNREAD_TEXT = "The model couldn't read this email ({reason})."
EXPIRED_TEXT = "The summary has expired."

PROVIDER_NAMES = {"gmail": "Gmail", "outlook": "Outlook", "yahoo": "Yahoo"}
TRUSTED_TEXT = "Trusted sender"
VERIFIED_TEXT = "Verified sender"
UNVERIFIED_TEXT = "Sender not verified"
BULK_TEXT = "Bulk mail"
FOOTER_JOIN = " · "

BACKTICK = "`"
BACKTICK_STAND_IN = "ˋ"

# Phase 1i: answering. Interaction response types and the ephemeral flag, from Discord's reference.
CHANNEL_MESSAGE = 4
DEFERRED_UPDATE = 6
UPDATE_MESSAGE = 7
MODAL = 9
EPHEMERAL = 64

ANSWER_NAME = "Your answer"
ANSWER_TEXT = {
    "yes": "Yes, it's a task",
    "edit": "Yes, with your title",
    "notask": "Not a task",
    "mute": "Not a task; sender muted",
}

FORM_ACTION = "title"
FORM_TITLE = "Edit task title"
FORM_LABEL = "Task title"
FORM_INPUT_ID = "title"
FORM_TITLE_LIMIT = 100

FULL_LIMIT = 1900
FULL_CUT_NOTE = "The email is longer than Discord allows; use Open email to read the rest."
FULL_EMPTY = "(no text)"
FULL_EXPIRED = "The email text was deleted after 24 hours; use Open email to read it."
ALREADY_TEXT = "This email is already answered."
NO_SENDER_TEXT = "This email has no sender address."
TRUSTED_REPLY = "Added to your trusted senders:"
BAD_TITLE_TEXT = "A title needs 1 to 100 characters on one line."

# Phase 1k: commands, registered in your server only and hidden from members without admin rights.
_ADDRESS = {
    "type": 3,
    "name": "address",
    "description": "The exact email address",
    "required": True,
    "min_length": 3,
    "max_length": 254,
}
COMMANDS = (
    {
        "type": 1,
        "name": "trust",
        "description": "Trust a sender's exact address",
        "options": [_ADDRESS],
        "default_member_permissions": "0",
    },
    {
        "type": 1,
        "name": "untrust",
        "description": "Remove an address from your trusted senders",
        "options": [_ADDRESS],
        "default_member_permissions": "0",
    },
    {
        "type": 1,
        "name": "trusted",
        "description": "List your trusted senders",
        "default_member_permissions": "0",
    },
    {
        "type": 1,
        "name": "unmute",
        "description": "Stop dropping a muted sender's mail",
        "options": [_ADDRESS],
        "default_member_permissions": "0",
    },
    {
        "type": 1,
        "name": "muted",
        "description": "List your muted senders",
        "default_member_permissions": "0",
    },
)
ADDRESS_OPTION = "address"

NOT_YOURS_TEXT = "Only the owner can use this here."
BAD_ADDRESS_TEXT = "That is not an email address."
UNTRUSTED_REPLY = "Removed from your trusted senders:"
NOT_TRUSTED_REPLY = "Not on your trusted senders:"
UNMUTED_REPLY = "No longer muted:"
NOT_MUTED_REPLY = "Not on your muted senders:"
TRUSTED_LIST = "Your trusted senders:"
MUTED_LIST = "Your muted senders:"
NONE_TRUSTED = "You have no trusted senders."
NONE_MUTED = "You have no muted senders."
LIST_LIMIT = 1800
MORE_TEXT = "...and {count} more."
REGISTERED_TEXT = "Registered {count} commands in your server."

# Phase 1m: alerts. Only fixed text and identifiers (account names, error messages that are
# themselves fixed text); never email text. Action alerts mention the owner.
ALERT_GMAIL_AUTH = "Gmail sign-in needed for {account}. Run: mailroom gmail-login {account}"
ALERT_GMAIL_FIXED = "Gmail {account} works again."
ALERT_GATEWAY = (
    "The Discord listener stopped: {reason}. Buttons and commands won't answer until the "
    "service is restarted."
)
ALERT_GATEWAY_FIXED = "The Discord listener is running again."
ALERT_MODEL = (
    "The local model has been unreachable for 15 minutes. New mail is waiting; nothing is lost."
)
ALERT_MODEL_FIXED = "The local model is back. Waiting mail is being triaged."
ALERT_CATCH_UP = "Gmail {account} caught up after {offline} offline: {found}."
ALERT_GAP = " It was offline for more than 14 days, so check older mail in Gmail yourself."
LESS_THAN_AN_HOUR = "less than an hour"
