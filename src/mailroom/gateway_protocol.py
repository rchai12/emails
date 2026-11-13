"""Discord Gateway constants, from Discord's reference (Gateway; Opcodes and Status Codes).

`mailroom.gateway` speaks the protocol from these. The service asks for no intents: interactions
are not tied to an intent and always arrive.
"""

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
QUERY = "?v=10&encoding=json"
HOST_SUFFIX = ".discord.gg"

DISPATCH = 0
HEARTBEAT = 1
IDENTIFY = 2
RESUME = 6
RECONNECT = 7
INVALID_SESSION = 9
HELLO = 10
HEARTBEAT_ACK = 11

INTENTS = 0
PROPERTIES = {"os": "macos", "browser": "mailroom", "device": "mailroom"}

# Closes Discord says not to reconnect after. 1000 and 1001 end the session: identify again.
FATAL_CLOSES = frozenset({4004, 4010, 4011, 4012, 4013, 4014})
SESSION_ENDING_CLOSES = frozenset({1000, 1001})
# The code this service closes with when it means to resume (any code but 1000 or 1001).
RESUME_CLOSE = 4000

BACKOFF_SECONDS = (1, 2, 4, 8, 16, 32, 60)
POLL_SECONDS = 1.0
OPEN_TIMEOUT_SECONDS = 30.0
MAX_FRAME_BYTES = 1048576
