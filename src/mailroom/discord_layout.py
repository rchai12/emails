"""The checkpoint 1 message: its fixed text, colors, buttons and button ids.

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
