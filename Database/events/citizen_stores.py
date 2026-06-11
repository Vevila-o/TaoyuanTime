from datetime import date

from events.models import Store


ZHONGYUAN_CITIZEN_STORES = [
    {
        "name": "大魯閣遊戲愛樂園－中壢中原萌獸公園店",
        "district": "中壢",
        "address": "桃園市中壢區中華路二段501號B1",
        "latitude": 24.9609,
        "longitude": 121.2384,
        "discount_info": "憑桃園市民卡或桃園數位碼購票入園，贈送手作童玩區。",
        "start_date": date(2025, 7, 15),
        "end_date": date(2026, 7, 14),
    },
    {
        "name": "養鍋－中壢中原店",
        "district": "中壢",
        "address": "桃園市中壢區新中北路222號",
        "latitude": 24.9575,
        "longitude": 121.2407,
        "discount_info": "內用消費免費兌換「好養禮」一份，肉品或海鮮擇一。",
        "start_date": date(2024, 8, 29),
        "end_date": date(2026, 7, 14),
    },
    {
        "name": "必勝客－中壢新中北店",
        "district": "中壢",
        "address": "桃園市中壢區新中北路二段175號",
        "latitude": 24.9634,
        "longitude": 121.2582,
        "discount_info": "使用優惠代碼 26705，可享指定人氣饗宴餐 399 元。",
        "start_date": date(2026, 3, 10),
        "end_date": date(2026, 11, 30),
    },
    {
        "name": "肯德基－中壢環中東二店",
        "district": "中壢",
        "address": "桃園市中壢區環中東路二段150～154號",
        "latitude": 24.9585,
        "longitude": 121.2483,
        "discount_info": "使用優惠代碼 26763，可享指定雙料冠軍爭霸戰套餐 299 元。",
        "start_date": date(2026, 3, 10),
        "end_date": date(2026, 11, 30),
    },
]


def seed_zhongyuan_citizen_stores(*, dry_run=True):
    results = []
    for row in ZHONGYUAN_CITIZEN_STORES:
        lookup = {"name": row["name"], "address": row["address"]}
        defaults = {key: value for key, value in row.items() if key not in lookup}
        if dry_run:
            exists = Store.objects.filter(**lookup).exists()
            results.append({"name": row["name"], "created": not exists, "updated": exists})
            continue
        _, created = Store.objects.update_or_create(**lookup, defaults=defaults)
        results.append({"name": row["name"], "created": created, "updated": not created})
    return results


def get_zhongyuan_citizen_stores():
    names = [row["name"] for row in ZHONGYUAN_CITIZEN_STORES]
    stores_by_name = {
        store.name: store
        for store in Store.objects.filter(name__in=names)
    }
    return [stores_by_name.get(row["name"], SimpleStore(row)) for row in ZHONGYUAN_CITIZEN_STORES]


class SimpleStore:
    def __init__(self, row):
        for key, value in row.items():
            setattr(self, key, value)
