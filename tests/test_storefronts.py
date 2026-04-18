"""Tests for storefronts.py constants helpers."""

import unittest

from storefronts import DEFAULT_DISCOVERY_NAMES, DEFAULT_LOCALE, discovery_names_for, locale_for


class TestLocaleFor(unittest.TestCase):
    def test_known_storefronts(self):
        self.assertEqual(locale_for("hk"), "zh-Hant-HK")
        self.assertEqual(locale_for("mo"), "zh-Hant-HK")
        self.assertEqual(locale_for("tw"), "zh-Hant-TW")
        self.assertEqual(locale_for("jp"), "ja-JP")
        self.assertEqual(locale_for("sg"), "en-SG")
        self.assertEqual(locale_for("my"), "en-MY")
        self.assertEqual(locale_for("us"), "en-US")

    def test_unknown_storefront_returns_default(self):
        self.assertEqual(locale_for("zz"), DEFAULT_LOCALE)


class TestDiscoveryNamesFor(unittest.TestCase):
    def test_known_storefront_returns_single_name(self):
        self.assertEqual(discovery_names_for("hk"), ["新發行"])
        self.assertEqual(discovery_names_for("jp"), ["ニューリリース"])
        self.assertEqual(discovery_names_for("us"), ["New Releases"])

    def test_unknown_storefront_returns_default_list(self):
        names = discovery_names_for("zz")
        self.assertEqual(names, DEFAULT_DISCOVERY_NAMES)
        names.append("mutated")
        self.assertNotIn("mutated", DEFAULT_DISCOVERY_NAMES)


if __name__ == "__main__":
    unittest.main()
