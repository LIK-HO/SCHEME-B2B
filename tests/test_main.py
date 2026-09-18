from fastapi import HTTPException

from scheme_b2b import main


def test_write_api_fails_closed_without_api_key():
    original = main.settings.api_key
    main.settings.api_key = ""
    try:
        try:
            main._authorize(None)
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("Expected missing API key to block access")
    finally:
        main.settings.api_key = original


def test_write_api_rejects_wrong_api_key():
    original = main.settings.api_key
    main.settings.api_key = "secret"
    try:
        try:
            main._authorize("wrong")
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("Expected wrong API key to be rejected")
    finally:
        main.settings.api_key = original


def test_write_api_accepts_correct_api_key():
    original = main.settings.api_key
    main.settings.api_key = "secret"
    try:
        main._authorize("secret")
    finally:
        main.settings.api_key = original
