"""Parser tests run against a small committed JSON fixture in tests/fixtures/."""

import pytest


@pytest.mark.skip(reason="add fixtures/companyfacts_sample.json alongside src/parse.py")
def test_concept_aliasing_prefers_priority_order():
    ...


@pytest.mark.skip(reason="implement with drop_restatements()")
def test_restatement_keeps_latest_filed():
    ...
