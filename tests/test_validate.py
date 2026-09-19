from scheme_b2b.validate import validate_requisites


def test_valid_company_pair():
    ok, reason, inn, ogrn, ogrnip = validate_requisites("7707083893", "1027700132195")
    assert ok
    assert reason == "OK"
    assert inn == "7707083893"
    assert ogrn == "1027700132195"
    assert not ogrnip


def test_valid_ip_pair():
    ok, reason, inn, ogrn, ogrnip = validate_requisites("540100000099", "", "304540100000002")
    assert ok
    assert reason == "OK"
    assert inn == "540100000099"
    assert not ogrn
    assert ogrnip == "304540100000002"


def test_reject_wrong_pair_type():
    ok, *_ = validate_requisites("7707083893", "", "304540100000002")
    assert not ok


def test_reject_both_registry_types():
    ok, *_ = validate_requisites("7707083893", "1027700132195", "304540100000002")
    assert not ok


def test_reject_bad_inn():
    ok, *_ = validate_requisites("7707083894", "1027700132195")
    assert not ok


def test_reject_bad_ogrn():
    ok, *_ = validate_requisites("7707083893", "1027700132194")
    assert not ok
