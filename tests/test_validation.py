from scheme_b2b.validation import validate_inn, validate_ogrn, validate_ogrnip, validate_requisites


def test_valid_inn_legal_entity():
    assert validate_inn("7707083893")


def test_valid_ogrn():
    assert validate_ogrn("1027700132195")


def test_valid_ogrnip():
    assert validate_ogrnip("304500116800070")


def test_bad_checksum_is_rejected():
    assert not validate_inn("7707083894")
    assert not validate_ogrn("1027700132196")
    assert not validate_ogrnip("304500116800071")


def test_requisites_require_inn_and_entity_identifier():
    result = validate_requisites("7707083893", "1027700132195", "")
    assert result.valid


def test_requisites_enforce_legal_entity_identifier_type():
    assert validate_requisites("7707083893", "1027700132195", "").valid
    assert not validate_requisites("7707083893", "", "304500116800070").valid


def test_requisites_enforce_ip_identifier_type():
    assert validate_requisites("500100000015", "", "304500116800070").valid
    assert not validate_requisites("500100000015", "1027700132195", "").valid


def test_requisites_reject_both_registry_identifiers():
    result = validate_requisites("7707083893", "1027700132195", "304500116800070")
    assert not result.valid
    assert "Одновременно" in result.reason
