from scheme_b2b.outbox import OutboxDispatcher


def test_unknown_channel_fails_fast():
    class FakeSettings:
        outbox_max_attempts = 5
        outbox_backoff_base_seconds = 10

    dispatcher = OutboxDispatcher(None, FakeSettings())
    try:
        dispatcher._deliver("UNKNOWN", "x", "m", "s")
    except ValueError as exc:
        assert "Неизвестный канал" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
