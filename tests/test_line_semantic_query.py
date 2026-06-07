from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from events.models import Activity, ActivitySearchProfile, Tag
from myapp.line_services import (
    normalize_ai_conditions,
    query_activities_by_conditions,
    rule_classify_line_intent,
    rule_extract_conditions,
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
