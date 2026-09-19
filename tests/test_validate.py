from scheme_b2b.validate import validate_requisites


def test_valid_company_pair():
    ok, reason, inn, ogrn, ogrnip = validate_requisites("7707083893", "1027700132195")
    assert ok and reason == "OK"
    assert inn == "7707083893"
    assert ogrn == "1027700132195"
    assert not ogrnip


def test_reject_wrong_pair_type():
    ok, *_ = validate_requisites("7707083893", "", "304540100000001")
    assert not ok
