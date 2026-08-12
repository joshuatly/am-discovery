"""Tests for storefronts.py + storefront_locales.py."""

import contextlib
import os
import tempfile
import unittest

import config
from storefront_locales import STOREFRONT_LOCALES
from storefronts import DEFAULT_LOCALE, discovery_names_for, fallback_titles, locale_for


class TestLocaleFor(unittest.TestCase):
    def test_asian_storefronts(self):
        self.assertEqual(locale_for("hk"), "zh-Hant-HK")
        self.assertEqual(locale_for("mo"), "zh-Hant-HK")
        self.assertEqual(locale_for("tw"), "zh-Hant-TW")
        self.assertEqual(locale_for("jp"), "ja")
        self.assertEqual(locale_for("kr"), "ko")
        self.assertEqual(locale_for("cn"), "zh-Hans-CN")

    def test_english_storefronts_use_api_defaults(self):
        # Per /v1/storefronts: SG and MY default to en-GB (not en-SG/en-MY).
        self.assertEqual(locale_for("sg"), "en-GB")
        self.assertEqual(locale_for("my"), "en-GB")
        self.assertEqual(locale_for("us"), "en-US")
        self.assertEqual(locale_for("gb"), "en-GB")
        self.assertEqual(locale_for("ca"), "en-CA")
        self.assertEqual(locale_for("au"), "en-AU")

    def test_european_storefronts(self):
        self.assertEqual(locale_for("de"), "de-DE")
        self.assertEqual(locale_for("fr"), "fr-FR")
        self.assertEqual(locale_for("es"), "es-ES")
        self.assertEqual(locale_for("it"), "it")
        self.assertEqual(locale_for("ch"), "de-CH")
        self.assertEqual(locale_for("se"), "sv")

    def test_unknown_storefront_returns_default(self):
        self.assertEqual(locale_for("zz"), DEFAULT_LOCALE)


class TestStorefrontLocalesCoverage(unittest.TestCase):
    def test_is_populated(self):
        # Sanity check that the full Apple storefront list is present.
        self.assertGreater(len(STOREFRONT_LOCALES), 150)

    def test_all_values_are_bcp47_like(self):
        for code, locale in STOREFRONT_LOCALES.items():
            self.assertRegex(locale, r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$", msg=f"bad locale for {code}: {locale}")


# ---------------------------------------------------------------------------
# discovery_names_for / fallback_titles — sourced from config.json, editable
# at runtime via the Settings page (PUT /api/system/config), no restart.
# ---------------------------------------------------------------------------


class DiscoveryConfigTestCase(unittest.TestCase):
    """Isolates config.CONFIG_PATH so these tests don't depend on (or
    mutate) the real config.json on disk."""

    def setUp(self):
        self._cfg_fd, self._cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(self._cfg_fd)
        os.unlink(self._cfg_path)
        self._orig_config_path = config.CONFIG_PATH
        config.CONFIG_PATH = self._cfg_path

    def tearDown(self):
        config.CONFIG_PATH = self._orig_config_path
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._cfg_path)


class TestDiscoveryNamesFor(DiscoveryConfigTestCase):
    def test_known_storefront_returns_single_name_from_defaults(self):
        # discovery_names ships empty by default (config._DEFAULTS) — every
        # storefront falls back to substring-matching discovery_fallback_titles
        # until a per-storefront override is configured via the Settings page.
        self.assertEqual(discovery_names_for("hk"), config._DEFAULTS["discovery_fallback_titles"])
        self.assertEqual(discovery_names_for("jp"), config._DEFAULTS["discovery_fallback_titles"])
        self.assertEqual(discovery_names_for("us"), config._DEFAULTS["discovery_fallback_titles"])

    def test_unknown_storefront_returns_default_fallback_list(self):
        names = discovery_names_for("zz")
        self.assertEqual(names, config._DEFAULTS["discovery_fallback_titles"])
        names.append("mutated")
        self.assertNotIn("mutated", fallback_titles())

    def test_configured_name_overrides_default(self):
        # Simulates editing the Settings page after a storefront's room
        # title changes on Apple's side — no code change, no restart.
        cfg = config.load_config()
        cfg["discovery_names"]["hk"] = "本週新發行"
        config.save_config(cfg)

        self.assertEqual(discovery_names_for("hk"), ["本週新發行"])

    def test_configured_fallback_titles_override_default(self):
        cfg = config.load_config()
        cfg["discovery_fallback_titles"] = ["custom new release title"]
        config.save_config(cfg)

        self.assertEqual(fallback_titles(), ["custom new release title"])
        self.assertEqual(discovery_names_for("zz"), ["custom new release title"])


if __name__ == "__main__":
    unittest.main()
