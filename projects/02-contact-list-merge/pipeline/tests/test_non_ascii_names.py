"""Names with accents or non-Latin letters must not be stripped into false matches."""
from pipeline import normalize as N
from pipeline.tests.test_cluster import prep, sizes


def test_accents_are_folded_not_deleted():
    assert N.letters("Müller") == N.letters("Muller") == "muller"
    assert N.letters("Łukasz Søren Straß") == "lukaszsorenstrass"


def test_the_german_two_letter_spelling_is_not_treated_as_the_same():
    assert N.letters("Mueller") != N.letters("Müller")  # a documented limit


def test_two_different_cyrillic_surnames_stay_separate():
    assert sizes([prep("Anna", "Иванова"), prep("Anna", "Петрова")])[0] == [1, 1]


def test_the_same_cyrillic_surname_still_merges():
    assert sizes([prep("Anna", "Иванова"), prep("Anna", "Иванова")])[0] == [2]


def test_a_missing_surname_is_never_a_match():
    assert sizes([prep("Anna", ""), prep("Anna", "")])[0] == [1, 1]
