from datetime import datetime

from scheme_b2b.schedule import MSK, already_ran_this_slot, allowed_slots, next_run, should_run_now


def test_frequency_slots():
    assert allowed_slots("1 раз в день") == (6,)
    assert allowed_slots("2 раза в день") == (6, 14)
    assert allowed_slots("3 раза в день") == (6, 14, 22)


def test_should_run():
    now = datetime(2026, 9, 18, 6, 7, tzinfo=MSK)
    assert should_run_now("1 раз в день", now)


def test_idempotent_slot():
    now = datetime(2026, 9, 18, 14, 7, tzinfo=MSK)
    assert already_ran_this_slot("2026-09-18T14:07:00+03:00", now)


def test_next_run():
    now = datetime(2026, 9, 18, 6, 7, tzinfo=MSK)
    assert next_run("2 раза в день", now).hour == 14


def test_invalid_frequency_fails_closed():
    assert allowed_slots("invalid") == ()
