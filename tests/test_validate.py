from diacritizer.validate import check, strip_diacritics

KTB = "كتب"                       # كتب
KTB_FULL = "كَتَبَ"  # كَتَبَ
SENT = "كتب الولد الدرس."  # كتب الولد الدرس.


def test_strip_removes_only_diacritics():
    assert strip_diacritics(KTB_FULL) == KTB
    assert strip_diacritics(SENT) == SENT


def test_accepts_diacritics_added():
    assert check(KTB, KTB_FULL).ok
    assert check(SENT, SENT.replace(KTB, KTB_FULL)).ok


def test_accepts_identical_output():
    assert check(SENT, SENT).ok


def test_rejects_changed_letter():
    bad = "كَتَتَ"   # last letter ب -> ت
    v = check(KTB, bad)
    assert not v.ok and v.position == 2 and "altered" in v.reason


def test_rejects_appended_and_removed_characters():
    assert check(KTB, KTB_FULL + "ا").reason == "characters appended"
    assert check(KTB, "كَتَ").reason == "characters removed"


def test_rejects_whitespace_and_punctuation_changes():
    assert not check(SENT, SENT.replace(" ", "  ")).ok
    assert not check(SENT, SENT.rstrip(".")).ok


def test_quranic_marks_count_as_diacritics():
    assert check(KTB, KTB + "ۖ").ok          # small high ligature sad-lam-alef-meem
    assert check(KTB, "كٰتب").ok  # superscript alef


def test_non_arabic_passes_through_unchanged():
    assert check("Hello 123", "Hello 123").ok
    assert not check("Hello", "Hallo").ok


def test_empty_output_is_rejected():
    assert not check(KTB, "").ok
