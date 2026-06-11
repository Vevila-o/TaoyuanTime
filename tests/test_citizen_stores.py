from django.test import TestCase

from events.citizen_stores import ZHONGYUAN_CITIZEN_STORES, seed_zhongyuan_citizen_stores
from events.models import Store


class ZhongyuanCitizenStoreSeedTests(TestCase):
    def test_seed_creates_four_fixed_demo_stores(self):
        results = seed_zhongyuan_citizen_stores(dry_run=False)

        self.assertEqual(len(results), 4)
        self.assertEqual(Store.objects.count(), 4)
        self.assertEqual(
            set(Store.objects.values_list("name", flat=True)),
            {row["name"] for row in ZHONGYUAN_CITIZEN_STORES},
        )

    def test_seed_is_idempotent_and_updates_existing_store(self):
        seed_zhongyuan_citizen_stores(dry_run=False)
        store = Store.objects.get(name="必勝客－中壢新中北店")
        store.discount_info = "舊優惠"
        store.save()

        results = seed_zhongyuan_citizen_stores(dry_run=False)

        self.assertEqual(Store.objects.count(), 4)
        self.assertEqual(Store.objects.get(name="必勝客－中壢新中北店").discount_info, "使用優惠代碼 26705，可享指定人氣饗宴餐 399 元。")
        self.assertEqual(sum(1 for item in results if item["updated"]), 4)
