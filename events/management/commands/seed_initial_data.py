import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from events.models import Tag, SourceWebsite, Activity, UserProfile


INITIAL_TAGS = {
    'region': ['桃園','中壢','平鎮','八德','龜山','蘆竹','大溪','龍潭','楊梅','大園','新屋','觀音','復興'],
    'activity_type': ['展覽','講座','市集','表演','音樂','親子','戶外','導覽','手作','電影','動漫','運動','寵物','美食','節慶','農遊','閱讀','客家','藝文','青年'],
    'audience': ['親子','學生','青年','長輩','一般','情侶','毛孩'],
    'cost': ['免費','付費','需報名','免預約','金額未提供'],
    'discount': ['市民卡','特約優惠','無優惠','優惠未提供'],
}

INITIAL_SOURCES = [
    ('桃園市政府','https://www.tycg.gov.tw/ActiveMonthList.aspx?n=8&sms=7883','central'),
    ('經發局','https://taoyuan.94i.club','central'),
    ('農業局','https://agriculture.tycg.gov.tw/News.aspx?n=10591&sms=14301','central'),
    ('觀光旅遊局－桃園觀光導覽網','https://travel.tycg.gov.tw','central'),
    ('文化局','https://culture.tycg.gov.tw/News.aspx?n=11099&sms=14558','central'),
    ('客家事務局','https://www.hakka.tycg.gov.tw/cl.aspx?n=18974','central'),
    ('青年事務局','https://youth.tycg.gov.tw/News.aspx?n=11582&sms=14781','central'),
    ('體育局','https://www.dst.tycg.gov.tw/News.aspx?n=11694&sms=14822','central'),
    ('動保處','https://animal.tycg.gov.tw/News.aspx?n=8542&sms=12542','department'),
    ('桃園市立圖書館','https://www.typl.gov.tw/zh-tw/Activity?Filter%5B0%5D=&Filter%5B4%5D=&Filter%5B1%5D=&Filter%5B2%5D=&Filter%5B3%5D=&keyword=','department'),
    ('博物館','https://wem.tycg.gov.tw/News_Photo.aspx?n=9676&sms=13653','department'),
    ('桃園市立美術館活動','https://tmofa.tycg.gov.tw/ch/events/current-events','department'),
    ('桃園市立美術館展覽','https://tmofa.tycg.gov.tw/ch/exhibitions/current-exhibitions','department'),
]


class Command(BaseCommand):
    help = 'Seed initial tags, source websites and mock activities (100)'

    def handle(self, *args, **options):
        created_tags = 0
        for ttype, names in INITIAL_TAGS.items():
            for name in names:
                obj, created = Tag.objects.get_or_create(name=name, tag_type=ttype, defaults={'is_active': True})
                if created:
                    created_tags += 1

        created_sources = 0
        source_objs = []
        for name, url, stype in INITIAL_SOURCES:
            obj, created = SourceWebsite.objects.get_or_create(name=name, defaults={'url': url, 'source_type': stype, 'is_active': True})
            source_objs.append(obj)
            if created:
                created_sources += 1

        user, _ = UserProfile.objects.get_or_create(line_user_id='U_sample_01', defaults={'display_name': '測試使用者'})

        # prepare tag pools
        regions = list(Tag.objects.filter(tag_type='region'))
        types = list(Tag.objects.filter(tag_type='activity_type'))
        audiences = list(Tag.objects.filter(tag_type='audience'))
        costs = list(Tag.objects.filter(tag_type='cost'))
        discounts = list(Tag.objects.filter(tag_type='discount'))

        # sample titles and templates
        title_templates = [
            '桃園市{place}文化節：{topic}展覽',
            '{place}社區親子市集',
            '{place}青年創意工作坊：{topic}',
            '{place}戶外音樂會 - {topic}',
            '{place}運動嘉年華',
            '{place}導覽活動：{topic}',
            '{place}圖書館閱讀講座',
            '{place}美術館特展：{topic}',
            '{place}農遊體驗',
            '{place}寵物友善市集',
        ]
        topics = ['傳統工藝','現代藝術','環境教育','街頭音樂','親子互動','青年創業','地方史蹟','美食文化','運動健康','書籍分享']
        places = ['中壢','桃園','平鎮','八德','龜山','蘆竹','大溪','龍潭','楊梅','大園']

        now = timezone.now()
        created_acts = 0
        for i in range(100):
            tpl = random.choice(title_templates)
            topic = random.choice(topics)
            place = random.choice(places)
            title = tpl.format(place=place, topic=topic)
            start_offset_days = random.choice([0, random.randint(1,6), random.randint(7,20), random.randint(21,60)])
            start = now + timedelta(days=start_offset_days, hours=random.randint(8,20))
            end = start + timedelta(hours=random.choice([2,3,4,6]))
            source = random.choice(source_objs)
            district_tag = random.choice(regions) if regions else None
            type_tag = random.choice(types) if types else None
            audience_tag = random.choice(audiences) if audiences else None
            cost_tag = random.choice(costs) if costs else None
            discount_tag = random.choice(discounts) if discounts and random.random() < 0.3 else None

            act = Activity.objects.create(
                title=title,
                description=f'{title} 的詳細內容，主題為{topic}。',
                raw_content=f'<p>原始內容示範 {i+1} - {topic}</p>',
                source_agency=source.name,
                source_website=source,
                source_url=f'{source.url.rstrip("/")}/sample/{i+1}',
                official_detail_url=f'{source.url.rstrip("/")}/sample/{i+1}',
                source_key=(('travel' if 'travel' in source.url else
                             'culture' if 'culture' in source.url else
                             'library' if 'typl' in source.url else
                             'museum' if 'tmofa' in source.url else
                             'youth' if 'youth' in source.url else
                             'agriculture' if 'agriculture' in source.url else
                             'other')),
                location=f'{place}文化廣場',
                district=district_tag.name if district_tag else place,
                start_date=start,
                end_date=end,
                image_url=f'https://placehold.co/600x400?text={i+1}',
                is_free=(random.random() < 0.5),
                requires_registration=(random.random() < 0.3),
                fee_description=('免費' if random.random() < 0.5 else '票價：200'),
                registration_info=('請線上報名' if random.random() < 0.5 else ''),
                has_citizen_card_discount=(random.random() < 0.2),
                citizen_card_note=('持市民卡享9折' if random.random() < 0.2 else ''),
                status='active',
                # new fields
                item_type='activity',
                is_activity=True,
                is_public_item=True,
                line_ready=True,
                ai_ready=True,
                recommendation_ready=True,
                fee_type=('free' if random.random() < 0.5 else 'paid'),
                quality_score=random.uniform(75, 100),
                quality_level=('high' if random.random() < 0.6 else 'medium'),
            )
            # ensure tags: region, activity_type, audience, cost
            attach = []
            if district_tag:
                attach.append(district_tag)
            if type_tag:
                attach.append(type_tag)
            if audience_tag:
                attach.append(audience_tag)
            if cost_tag:
                attach.append(cost_tag)
            if discount_tag:
                attach.append(discount_tag)
            act.tags.set(attach)
            created_acts += 1

        # create 10 non-activity items for testing filtering (announcement/recap/place_or_resource)
        non_types = ['announcement', 'recap', 'place_or_resource']
        created_non = 0
        for j in range(10):
            nt = random.choice(non_types)
            idx = 100 + j + 1
            title = f'測試非活動 {nt} 範例 {idx}'
            src = random.choice(source_objs)
            na = Activity.objects.create(
                title=title,
                description=f'{title} 的說明（非活動測試）',
                raw_content=f'<p>非活動內容示範 {idx}</p>',
                source_agency=src.name,
                source_website=src,
                source_url=f'{src.url.rstrip("/")}/sample_non/{idx}',
                official_detail_url=f'{src.url.rstrip("/")}/sample_non/{idx}',
                location='',
                district='',
                start_date=None,
                end_date=None,
                image_url='',
                is_free=True,
                requires_registration=False,
                fee_description='',
                registration_info='',
                has_citizen_card_discount=False,
                citizen_card_note='',
                status='active',
                item_type=nt,
                is_activity=False,
                is_public_item=False,
                line_ready=False,
                ai_ready=False,
                recommendation_ready=False,
                fee_type='unknown',
                quality_score=random.uniform(10, 40),
                quality_level=( 'rejected' if random.random() < 0.5 else 'low'),
                quality_warnings='缺少時間/地點或判定為非活動',
                exclude_from_recommendation_reason='非活動類型或品質低',
            )
            created_non += 1

        self.stdout.write(self.style.SUCCESS(f'Seeded tags={created_tags}, sources={created_sources}, sample_activities={created_acts}'))
