from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from events.models import Activity, ActivitySearchProfile, LineConversationState, Tag, UserProfile
from myapp.line_services import (
    build_activity_intro_text,
    classify_line_intent,
    db_search_terms_from_conditions,
    handle_line_text_message,
    normalize_ai_conditions,
    query_activities_by_conditions,
    rule_classify_line_intent,
    rule_extract_conditions,
    search_activities_for_line,
)


class LineSemanticQueryTests(TestCase):
    def setUp(self):
        self.family = Tag.objects.create(name='親子', tag_type='audience')
        self.art = Tag.objects.create(name='藝文', tag_type='activity_type')

    def make_activity(self, title, *, tags=None, search_text='', start_offset=10):
        activity = Activity.objects.create(
            title=title,
            description='活動內容',
            status='active',
            is_activity=True,
            recommendation_ready=True,
            official_detail_url=f'https://example.com/{title}',
            source_url=f'https://example.com/{title}',
            start_date=timezone.now() + timedelta(days=start_offset),
            end_date=timezone.now() + timedelta(days=start_offset + 1),
        )
        if tags:
            activity.tags.add(*tags)
        if search_text:
            ActivitySearchProfile.objects.create(
                activity=activity,
                search_text=search_text,
                keywords=['兒童', '小朋友'],
                topics=['親子'],
                synonyms=['家庭', '放電'],
                status='success',
            )
        return activity

    def test_lifestyle_activity_intents_are_activity_search(self):
        for text in ['我想帶小孩玩', '想讓小孩放電', '下雨天去哪', '情侶約會']:
            self.assertEqual(rule_classify_line_intent(text), 'activity_search')

    def test_non_activity_chat_is_rejected(self):
        self.assertEqual(rule_classify_line_intent('心情好差'), 'unsupported_chat')

    def test_contextual_new_search_reaches_llm_instead_of_refinement_rule(self):
        state = SimpleNamespace(intent='activity_search', last_query='想騎腳踏車')
        response = SimpleNamespace(parsed={'intent': 'activity_search'}, provider='test', model='mock')

        with patch('myapp.line_services.call_json_with_fallback', return_value=response) as mocked_call:
            intent = classify_line_intent(None, '想爬山', state=state)

        self.assertEqual(intent, 'activity_search')
        mocked_call.assert_called_once()

    def test_child_lifestyle_query_uses_family_tag_and_semantic_terms(self):
        conditions = rule_extract_conditions('我想帶小孩玩')

        self.assertEqual(conditions['tag_names'], ['親子'])
        self.assertEqual(conditions['keyword'], '')
        self.assertIn('親子', conditions['soft_topics'])
        self.assertIn('兒童', conditions['related_terms'])
        self.assertIn('放電', conditions['related_terms'])

    def test_structured_family_query_keeps_formal_conditions(self):
        conditions = rule_extract_conditions('週末中壢免費親子活動')

        self.assertEqual(conditions['district'], '中壢')
        self.assertTrue(conditions['is_free'])
        self.assertEqual(conditions['tag_names'], ['親子'])
        self.assertIn('start_date', conditions)
        self.assertIn('end_date', conditions)

    def test_normalize_ai_conditions_filters_unknown_tags_and_cleans_lifestyle_keyword(self):
        conditions = normalize_ai_conditions(
            {
                'tag_names': ['親子', '不存在標籤'],
                'keyword': '帶小孩玩',
                'soft_topics': ['親子', '體驗'],
                'related_terms': ['兒童', '小朋友'],
            },
            query='我想帶小孩玩',
        )

        self.assertEqual(conditions['tag_names'], ['親子'])
        self.assertEqual(conditions['keyword'], '')
        self.assertIn('體驗', conditions['soft_topics'])
        self.assertIn('兒童', conditions['related_terms'])

    def test_search_profile_can_supply_semantic_matches_when_tag_is_missing(self):
        self.make_activity('一般藝文活動', tags=[self.art], start_offset=20)
        semantic_match = self.make_activity(
            '兒童探索活動',
            search_text='適合兒童 小朋友 家庭 體驗 放電',
            start_offset=5,
        )

        results = query_activities_by_conditions(rule_extract_conditions('我想帶小孩玩'), limit=3)

        self.assertIn(semantic_match, results)

    def test_publicly_excluded_activity_is_not_returned(self):
        excluded = self.make_activity('裁罰名單活動字樣', tags=[self.art], start_offset=5)
        excluded.excluded_from_public = True
        excluded.is_public_item = False
        excluded.is_activity = False
        excluded.exclude_reason = 'penalty_list'
        excluded.final_state = 'non_activity'
        excluded.save(update_fields=[
            'excluded_from_public',
            'is_public_item',
            'is_activity',
            'exclude_reason',
            'final_state',
        ])

        results = query_activities_by_conditions({'tag_names': ['藝文']}, limit=3)

        self.assertNotIn(excluded, results)

    def test_keyword_expands_with_database_vocabulary_and_prefers_title_match(self):
        profile_only = self.make_activity('一般兒童劇', start_offset=5)
        ActivitySearchProfile.objects.create(
            activity=profile_only,
            search_text='頁面側欄提到文化幣',
            keywords=[],
            topics=[],
            synonyms=[],
            status='success',
        )
        title_match = self.make_activity('【本節目適用文化幣】西遊記誤闖黑家店', start_offset=20)
        ActivitySearchProfile.objects.create(
            activity=title_match,
            search_text='文化幣 歌仔戲',
            keywords=['文化幣'],
            topics=[],
            synonyms=['文化幣'],
            status='success',
        )
        conditions = {
            'district': '',
            'tag_names': [],
            'is_free': None,
            'keyword': '要文化幣',
            'soft_topics': [],
            'related_terms': [],
        }

        self.assertIn('文化幣', db_search_terms_from_conditions(conditions))
        results = query_activities_by_conditions(conditions, limit=2)

        self.assertEqual(results, [title_match])
        self.assertEqual(results[0], title_match)

        user = UserProfile.objects.create(line_user_id='semantic-rank-test')
        line_results = search_activities_for_line(user, '我想要文化幣的活動', limit=2, conditions=conditions)

        self.assertEqual(line_results, [title_match])
        self.assertEqual(line_results[0], title_match)
        self.assertIn('1 個符合', build_activity_intro_text(line_results, '我想要文化幣的活動', user=user))

    def test_named_activity_followup_describes_previous_result_instead_of_searching(self):
        activity = self.make_activity('桃園珍珠海岸主題遊程', tags=[self.art])
        activity.description = activity.title
        activity.location = '桃園濱海地區'
        activity.save(update_fields=['description', 'location'])
        user = UserProfile.objects.create(line_user_id='activity-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='運動活動',
            conditions={},
            last_activity_ids=[activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = handle_line_text_message(user, '桃園珍珠海岸主題遊程在幹嘛在幹嘛')
        text = getattr(response, 'text', '')

        self.assertIn('桃園珍珠海岸主題遊程', text)
        self.assertIn('目前資料庫沒有更完整的活動內容摘要', text)
        self.assertNotIn('目前沒有找到符合', text)
