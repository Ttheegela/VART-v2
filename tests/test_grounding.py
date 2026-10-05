from app.grounding import unsupported_numbers


def test_numbers_must_come_from_the_sources() -> None:
    assert (
        unsupported_numbers("Logs are kept for 90 days.", ["Security logs are retained for 90 days."]) == []
    )
    assert unsupported_numbers(
        "Logs are kept for 365 days.", ["Security logs are retained for 90 days."]
    ) == ["365"]


def test_small_counts_and_matching_dates_are_allowed() -> None:
    assert unsupported_numbers("Two of 3 reviews, dated 2026-09-15.", ["dated 2026-09-15"]) == []


def test_percent_and_money_must_match_their_kind() -> None:
    assert unsupported_numbers("Uptime is 99.9%.", ["99.9% availability"]) == []
    assert unsupported_numbers("A limit of $5,000,000.", ["a limit of 5,000,000 units"]) == ["5000000"]


def test_a_percent_needs_a_source_percent() -> None:
    assert unsupported_numbers("Uptime is 95%.", ["95 servers, 99.9% availability"]) == ["95"]
