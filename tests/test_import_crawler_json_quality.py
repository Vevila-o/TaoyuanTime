from django.test import TestCase

from events.management.commands.import_crawler_json import activity_values, infer_tags
from events.models import SourceWebsite, Tag


class ImportCrawlerJsonQualityTests(TestCase):
    def test_common_registration_page_is_cleared_on_import(self):
        source = SourceWebsite.objects.create(name='文化局')
        item = {
            'title': '文化局活動',
            'description': '活動日期：115-06-01 活動地址：桃園展演中心。',
            'registration_method': 'online',
            'registration_url': 'https://culture.tycg.gov.tw/ActiveList.aspx?n=23648&sms=20299',
            'fee_type': 'unknown',
        }

        values = activity_values(item, source)

        self.assertFalse(values['requires_registration'])
        self.assertEqual(values['registration_url'], '')
        self.assertEqual(values['registration_info'], '')

    def test_common_registration_page_does_not_add_registration_tag(self):
        registration = Tag.objects.create(name='需報名', tag_type='cost')
        unknown_amount = Tag.objects.create(name='金額未提供', tag_type='cost')
        item = {
            'title': '文化局活動',
            'description': '活動日期：115-06-01 活動地址：桃園展演中心。',
            'registration_method': 'online',
            'registration_url': 'https://culture.tycg.gov.tw/ActiveList.aspx?n=23648&sms=20299',
            'fee_type': 'unknown',
        }

        tags = infer_tags(item, {
            ('cost', '需報名'): registration,
            ('cost', '金額未提供'): unknown_amount,
        })

        self.assertNotIn(registration, tags)
        self.assertIn(unknown_amount, tags)
