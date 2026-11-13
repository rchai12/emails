from dataclasses import replace

from mailroom.checkpoint import approved_message
from mailroom.store import Approval
from tests.unit.test_checkpoint_second import DECIDED, DUE, FULL, ITEM, PROPOSED, RECORD, TITLE


def test_a_decided_card_drops_a_link_too_long_for_a_button() -> None:
    long_link = "https://mail.google.com/mail/#all/" + "a" * 479
    approval = Approval(ITEM, "approve", TITLE, DUE, DECIDED)
    card = approved_message(replace(RECORD, link=long_link), PROPOSED, ITEM, approval)
    assert card["components"] == [{"type": 1, "components": [FULL]}]
