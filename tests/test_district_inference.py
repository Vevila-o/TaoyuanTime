from django.test import SimpleTestCase

from events.services import infer_taoyuan_district_from_text


class DistrictInferenceTests(SimpleTestCase):
    def test_known_venue_aliases_infer_district(self):
        cases = [
            ("桃園展演中心-展演廳", "桃園區"),
            ("木育教室(武德殿旁小屋)", "大溪區"),
            ("大古山休閒農業區、坑子溪休閒農業區", "蘆竹區"),
            ("石門水庫阿姆坪生態公園", "大溪區"),
        ]

        for location, district in cases:
            with self.subTest(location=location):
                self.assertEqual(infer_taoyuan_district_from_text(location, "活動"), district)

    def test_cross_district_aliases_do_not_force_single_district(self):
        location = "桃園展演中心、石門水庫阿姆坪生態公園"

        self.assertEqual(infer_taoyuan_district_from_text(location, "活動"), "")
