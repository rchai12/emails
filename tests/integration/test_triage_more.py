from mailroom.triage import rank


def test_an_empty_list_ranks_as_an_empty_list() -> None:
    assert rank([]) == []
