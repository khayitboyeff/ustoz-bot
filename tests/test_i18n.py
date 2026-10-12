from services.i18n import normalize_language, t


def test_all_supported_languages_have_main_menu_and_settings_labels():
    for language in ("uz", "ru", "en"):
        assert t(language, "menu_lessons") != "menu_lessons"
        assert t(language, "menu_settings") != "menu_settings"
        assert t(language, "start_body") != "start_body"
        assert t(language, "help_body") != "help_body"


def test_language_normalization_falls_back_to_uzbek():
    assert normalize_language("ru") == "ru"
    assert normalize_language("en") == "en"
    assert normalize_language("xx") == "uz"
    assert normalize_language(None) == "uz"


def test_translated_help_contains_common_commands():
    assert "/settings" in t("uz", "help_body")
    assert "/settings" in t("ru", "help_body")
    assert "/settings" in t("en", "help_body")
