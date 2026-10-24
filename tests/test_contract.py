from dataclasses import replace

import pytest

from sheetcheck.engine import reconcile
from sheetcheck.errors import InputError
from sheetcheck.models import FileSpec, Mapping, Rules, Side
from sheetcheck.readers import read_source
from sheetcheck.validators import validate


CONFIRMED = Rules(period="fictional", same_currency_confirmed=True, same_period_confirmed=True)


def table(side, rules=CONFIRMED):
    return validate(read_source(b"id,amount\nA,0\n", FileSpec("sample.csv", side)), Mapping(1, 2), rules)


@pytest.mark.parametrize("rules", [Rules(), replace(CONFIRMED, tolerance_minor=1), replace(CONFIRMED, version="v2"), replace(CONFIRMED, minor_digits=3), replace(CONFIRMED, currency="JPY"), replace(CONFIRMED, period=" ")])
def test_rules_must_be_explicit_and_supported(rules):
    with pytest.raises(InputError):
        table(Side.ORDER, rules)


def test_roles_and_confirmations_cannot_be_swapped_between_stages():
    order, payment = table(Side.ORDER), table(Side.PAYMENT)
    with pytest.raises(InputError):
        reconcile(payment, order, CONFIRMED)
    with pytest.raises(InputError):
        reconcile(order, payment, replace(CONFIRMED, currency="USD"))


@pytest.mark.parametrize("mapping", [Mapping(1, 1), Mapping(0, 2), Mapping(1, 3), Mapping(True, 2)])
def test_mapping_uses_distinct_in_range_one_based_integer_columns(mapping):
    source = read_source(b"id,amount\nA,0\n", FileSpec("sample.csv", Side.ORDER))
    with pytest.raises(InputError):
        validate(source, mapping, CONFIRMED)
