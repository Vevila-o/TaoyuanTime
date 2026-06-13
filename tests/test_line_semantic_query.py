from datetime import timedelta
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.conf import settings
from django.utils import timezone

from events.models import Activity, ActivitySearchProfile, LineConversationState, Tag, UserProfile
from myapp.line_services import (
    build_activity_intro_text,
    classify_line_intent,
    db_search_terms_from_conditions,
    handle_activity_postback,
    handle_line_text_message,
    normalize_ai_conditions,
    query_activities_by_conditions,
    rule_classify_line_intent,
    rule_extract_conditions,
    search_activities_for_line,
)
from events.services import recommend_activities_for_user


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

    def write_activity_html(self, filename, body):
        path = Path(settings.BASE_DIR) / 'tmp_test_activity_html' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
        self.addCleanup(lambda: path.exists() and path.unlink())
        self.addCleanup(lambda: path.parent.exists() and not any(path.parent.iterdir()) and path.parent.rmdir())
        return str(path)

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

    def test_relaxed_keyword_result_intro_denies_exact_match_before_recommending(self):
        activity = self.make_activity('戶外親子活動', tags=[self.art], start_offset=5)
        activity._line_notice = '先推薦相近活動。'
        user = UserProfile.objects.create(line_user_id='relaxed-intro-denial-test')

        text = build_activity_intro_text([activity], '有沒有腳踏車活動', user=user)

        self.assertIn('沒有', text)
        self.assertIn('有沒有腳踏車活動', text)
        self.assertIn('相似或其他活動', text)
        self.assertNotIn('找到 1 個符合', text)

    def test_keyword_search_without_title_match_is_marked_as_alternative(self):
        outdoor = Tag.objects.create(name='戶外', tag_type='activity_type')
        activity = self.make_activity('戶外親子活動', tags=[outdoor], start_offset=5)
        user = UserProfile.objects.create(line_user_id='keyword-alternative-notice-test')
        conditions = {
            'district': '',
            'tag_names': ['戶外'],
            'is_free': None,
            'keyword': '腳踏車',
            'soft_topics': [],
            'related_terms': ['戶外'],
        }

        results = search_activities_for_line(user, '有沒有腳踏車活動', limit=1, conditions=conditions)
        text = build_activity_intro_text(results, '有沒有腳踏車活動', user=user)

        self.assertEqual(results, [activity])
        self.assertIn('沒有', text)
        self.assertIn('相似或其他活動', text)
        self.assertNotIn('目前找到', text)

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

    def test_context_router_refines_search_and_replaces_previous_activity_context(self):
        old_activity = self.make_activity('桃園親子活動', tags=[self.family], start_offset=5)
        new_activity = self.make_activity('大園親子活動', tags=[self.family], start_offset=6)
        old_activity.district = '桃園'
        old_activity.save(update_fields=['district'])
        new_activity.district = '大園'
        new_activity.save(update_fields=['district'])
        user = UserProfile.objects.create(line_user_id='context-router-refine-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='親子活動',
            conditions={'tag_names': ['親子'], 'district': '', 'is_free': None, 'soft_topics': ['親子'], 'related_terms': []},
            last_activity_ids=[old_activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'district': '大園'}},
            provider='test',
            model='mock',
        )
        with patch('myapp.line_services.call_json_with_fallback', return_value=response):
            handle_line_text_message(user, '大園的呢')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.conditions['district'], '大園')
        self.assertEqual(state.conditions['tag_names'], ['親子'])
        self.assertEqual(state.last_activity_ids, [new_activity.id])
        self.assertNotIn(old_activity.id, state.last_activity_ids)

    def test_activity_followup_uses_local_html_for_detail_answer(self):
        activity = self.make_activity('桃園海洋探索營', tags=[self.art])
        activity.description = activity.title
        activity.raw_html_path = self.write_activity_html(
            'ocean-camp.html',
            '<html><main><h1>桃園海洋探索營</h1><p>活動包含潮間帶觀察、海廢手作與海洋保育導覽。</p></main></html>',
        )
        activity.save(update_fields=['description', 'raw_html_path'])
        user = UserProfile.objects.create(line_user_id='activity-followup-html-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='親子活動',
            conditions={'tag_names': ['親子']},
            last_activity_ids=[activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        response = SimpleNamespace(
            parsed={'intent': 'activity_followup', 'target_activity_id': activity.id},
            provider='test',
            model='mock',
        )
        ai_answer = SimpleNamespace(raw_text='桃園海洋探索營會帶大家做潮間帶觀察、海廢手作與海洋保育導覽。', provider='test', model='mock')

        with patch('myapp.line_services.call_json_with_fallback', return_value=response), \
             patch('myapp.line_services.call_text_with_fallback', return_value=ai_answer):
            message = handle_line_text_message(user, '這個活動在幹嘛')

        self.assertIn('潮間帶觀察', getattr(message, 'text', ''))
        self.assertIn('海廢手作', getattr(message, 'text', ''))

    def test_more_results_control_phrase_is_not_overridden_by_context_router(self):
        first = self.make_activity('第一個親子活動', tags=[self.family], start_offset=5)
        second = self.make_activity('第二個親子活動', tags=[self.family], start_offset=6)
        user = UserProfile.objects.create(line_user_id='more-results-router-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='親子活動',
            conditions={'tag_names': ['親子'], 'district': '', 'is_free': None, 'soft_topics': ['親子'], 'related_terms': []},
            last_activity_ids=[first.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '還有'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            handle_line_text_message(user, '還有嗎')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '親子活動')
        self.assertEqual(state.conditions.get('keyword', ''), '')
        self.assertIn(second.id, state.last_activity_ids)

    def test_ordinal_followup_targets_previous_card_without_searching(self):
        first = self.make_activity('第一張展覽', tags=[self.art], start_offset=5)
        second = self.make_activity('第二張展覽', tags=[self.art], start_offset=6)
        third = self.make_activity('第三張展覽', tags=[self.art], start_offset=7)
        first.location = '第一展場'
        second.location = '第二展場'
        third.location = '第三展場'
        first.save(update_fields=['location'])
        second.save(update_fields=['location'])
        third.save(update_fields=['location'])
        user = UserProfile.objects.create(line_user_id='ordinal-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='展覽',
            conditions={'tag_names': ['藝文'], 'district': '', 'is_free': None, 'soft_topics': ['展覽'], 'related_terms': []},
            last_activity_ids=[first.id, second.id, third.id],
            offset=3,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '第二個'}},
            provider='test',
            model='mock',
        )
        with patch('myapp.line_services.call_json_with_fallback', return_value=response):
            message = handle_line_text_message(user, '第二個在哪裡')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('第二張展覽', text)
        self.assertIn('第二展場', text)
        self.assertEqual(state.last_query, '展覽')
        self.assertEqual(state.last_activity_ids, [first.id, second.id, third.id])

    def test_fee_attribute_followup_stays_on_previous_cards_without_searching(self):
        free_activity = self.make_activity('中壢免費活動', tags=[self.art], start_offset=5)
        unknown_fee_activity = self.make_activity('中壢費用未標示活動', tags=[self.art], start_offset=6)
        free_activity.district = '中壢'
        free_activity.location = '中壢展演中心'
        free_activity.is_free = True
        free_activity.fee_type = 'free'
        free_activity.fee_description = ''
        unknown_fee_activity.district = '中壢'
        unknown_fee_activity.location = '中壢故事館'
        unknown_fee_activity.is_free = False
        unknown_fee_activity.fee_type = 'unknown'
        unknown_fee_activity.fee_description = ''
        free_activity.save(update_fields=['district', 'location', 'is_free', 'fee_type', 'fee_description'])
        unknown_fee_activity.save(update_fields=['district', 'location', 'is_free', 'fee_type', 'fee_description'])
        user = UserProfile.objects.create(line_user_id='fee-attribute-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='中壢活動',
            conditions={'district': '中壢', 'tag_names': [], 'is_free': None, 'soft_topics': [], 'related_terms': []},
            last_activity_ids=[free_activity.id, unknown_fee_activity.id],
            offset=2,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'is_free': True}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            message = handle_line_text_message(user, '免費嗎')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('上一輪結果', text)
        self.assertIn('中壢免費活動', text)
        self.assertIn('中壢費用未標示活動', text)
        self.assertIn('費用未明確標示', text)
        self.assertNotIn('免費或未標示收費', text)
        self.assertEqual(state.last_query, '中壢活動')
        self.assertEqual(state.last_activity_ids, [free_activity.id, unknown_fee_activity.id])

    def test_more_after_fee_followup_returns_new_cards_without_repeating_previous_cards(self):
        first = self.make_activity('中壢第一個活動', tags=[self.art], start_offset=5)
        second = self.make_activity('中壢第二個活動', tags=[self.art], start_offset=6)
        third = self.make_activity('中壢第三個活動', tags=[self.art], start_offset=7)
        fourth = self.make_activity('中壢第四個活動', tags=[self.art], start_offset=8)
        for activity in (first, second, third, fourth):
            activity.district = '中壢'
            activity.location = '中壢'
            activity.is_free = activity in (first, second)
            activity.fee_type = 'free' if activity.is_free else 'unknown'
            activity.save(update_fields=['district', 'location', 'is_free', 'fee_type'])
        user = UserProfile.objects.create(line_user_id='more-after-fee-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='中壢活動',
            conditions={'district': '中壢', 'tag_names': [], 'is_free': None, 'soft_topics': [], 'related_terms': []},
            last_activity_ids=[first.id, second.id, third.id],
            offset=3,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        fee_message = handle_line_text_message(user, '免費嗎')
        more_message = handle_line_text_message(user, '我要更多的')

        fee_text = getattr(fee_message, 'text', '')
        items = more_message if isinstance(more_message, list) else [more_message]
        state = LineConversationState.objects.get(user=user)
        self.assertIn('上一輪結果', fee_text)
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in items))
        self.assertNotIn(first.id, state.last_activity_ids)
        self.assertNotIn(second.id, state.last_activity_ids)
        self.assertNotIn(third.id, state.last_activity_ids)
        self.assertIn(fourth.id, state.last_activity_ids)
        self.assertEqual(state.last_query, '中壢活動')

    def test_recommendation_more_does_not_repeat_previous_recommendation_cards(self):
        activities = [
            self.make_activity(f'推薦活動{i}', tags=[self.art], start_offset=i)
            for i in range(1, 7)
        ]
        user = UserProfile.objects.create(line_user_id='recommendation-more-dedupe-test')

        with patch('myapp.line_services.recommend_activities_for_user', return_value=activities), \
             patch('myapp.line_services.rerank_activities_with_ai', side_effect=lambda _user, _query, items, limit=3: items[:limit]):
            first_message = handle_line_text_message(user, '推薦活動')
            first_state = LineConversationState.objects.get(user=user)
            more_message = handle_line_text_message(user, '更多')
            second_state = LineConversationState.objects.get(user=user)

        first_items = first_message if isinstance(first_message, list) else [first_message]
        more_items = more_message if isinstance(more_message, list) else [more_message]
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in first_items))
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in more_items))
        self.assertEqual(first_state.last_activity_ids, [activity.id for activity in activities[:3]])
        self.assertEqual(second_state.last_activity_ids, [activity.id for activity in activities[3:6]])
        self.assertTrue(set(first_state.last_activity_ids).isdisjoint(second_state.last_activity_ids))

    def test_repeated_recommendation_command_rotates_to_next_cards(self):
        activities = [
            self.make_activity(f'連按推薦活動{i}', tags=[self.art], start_offset=i)
            for i in range(1, 7)
        ]
        user = UserProfile.objects.create(line_user_id='repeat-recommendation-command-test')

        def fake_recommend(_user, limit=3, offset=0, **_kwargs):
            return activities[offset:offset + limit]

        with patch('myapp.line_services.recommend_activities_for_user', side_effect=fake_recommend), \
             patch('myapp.line_services.rerank_activities_with_ai', side_effect=lambda _user, _query, items, limit=3: items[:limit]):
            first_message = handle_line_text_message(user, '推薦活動')
            first_ids = list(LineConversationState.objects.get(user=user).last_activity_ids)
            second_message = handle_line_text_message(user, '推薦活動')
            second_ids = list(LineConversationState.objects.get(user=user).last_activity_ids)

        first_items = first_message if isinstance(first_message, list) else [first_message]
        second_items = second_message if isinstance(second_message, list) else [second_message]
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in first_items))
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in second_items))
        self.assertEqual(first_ids, [activity.id for activity in activities[:3]])
        self.assertEqual(second_ids, [activity.id for activity in activities[3:6]])
        self.assertTrue(set(first_ids).isdisjoint(second_ids))

    def test_recommendation_candidates_expand_beyond_repeated_user_tags(self):
        preferred = Tag.objects.create(name='手作', tag_type='activity_type')
        preferred_activity = self.make_activity('偏好手作活動', tags=[preferred], start_offset=1)
        exploration_activity = self.make_activity('探索型活動', tags=[self.art], start_offset=2)
        user = UserProfile.objects.create(line_user_id='recommendation-expanded-tags-test')
        user.preferred_tags.add(preferred)

        results = recommend_activities_for_user(user, limit=3)

        self.assertIn(preferred_activity.id, [activity.id for activity in results])
        self.assertIn(exploration_activity.id, [activity.id for activity in results])

    def test_view_more_postback_updates_context_for_followup(self):
        activities = [
            self.make_activity(f'推薦活動{i}', tags=[self.art], start_offset=i)
            for i in range(1, 7)
        ]
        user = UserProfile.objects.create(line_user_id='view-more-postback-context-test')
        LineConversationState.objects.create(
            user=user,
            intent='recommendation',
            last_query='推薦活動',
            conditions={'mode': 'recommendation'},
            last_activity_ids=[activity.id for activity in activities[:3]],
            offset=3,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        with patch('myapp.line_services.get_recommended_activities', return_value=activities[3:6]):
            handle_activity_postback(user, 'view_more', {'query': '推薦活動', 'offset': '3'})

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '推薦活動')
        self.assertEqual(state.last_activity_ids, [activity.id for activity in activities[3:6]])
        self.assertEqual(state.offset, 6)

    def test_large_activity_query_is_search_not_recommendation_mode(self):
        activity = self.make_activity('大型親子市集活動', tags=[self.art], search_text='大型 大活動 市集 熱鬧')
        user = UserProfile.objects.create(line_user_id='large-activity-query-test')

        message = handle_line_text_message(user, '有沒有大活動')

        items = message if isinstance(message, list) else [message]
        state = LineConversationState.objects.get(user=user)
        self.assertTrue(any(item.__class__.__name__ == 'FlexSendMessage' for item in items))
        self.assertEqual(state.intent, 'activity_search')
        self.assertNotEqual(state.conditions.get('mode'), 'recommendation')
        self.assertIn(activity.id, state.last_activity_ids)

    def test_search_after_recommendation_mode_does_not_prefix_recommendation_query(self):
        previous = self.make_activity('上一輪推薦活動', tags=[self.art], start_offset=5)
        target = self.make_activity('大型活動', tags=[self.art], search_text='大型 大活動 熱鬧', start_offset=6)
        user = UserProfile.objects.create(line_user_id='search-after-recommendation-test')
        LineConversationState.objects.create(
            user=user,
            intent='recommendation',
            last_query='推薦活動',
            conditions={'mode': 'recommendation'},
            last_activity_ids=[previous.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        route_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '大活動', 'soft_topics': ['大型']}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=route_response):
            handle_line_text_message(user, '有沒有大活動')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.intent, 'activity_search')
        self.assertEqual(state.last_query, '有沒有大活動')
        self.assertNotIn('推薦活動', state.last_query)
        self.assertIn(target.id, state.last_activity_ids)

    def test_out_of_taoyuan_activity_query_does_not_send_taoyuan_cards(self):
        self.make_activity('桃園展覽活動', tags=[self.art], search_text='展覽 藝文')
        user = UserProfile.objects.create(line_user_id='out-of-taoyuan-query-test')

        message = handle_line_text_message(user, '台北有什麼展覽')

        items = message if isinstance(message, list) else [message]
        self.assertFalse(any(item.__class__.__name__ == 'FlexSendMessage' for item in items))
        self.assertIn('桃園', getattr(items[0], 'text', ''))
        self.assertFalse(LineConversationState.objects.filter(user=user).exists())

    def test_context_router_can_exclude_tags_when_user_says_not_that_type(self):
        outdoor = Tag.objects.create(name='戶外', tag_type='activity_type')
        family = self.family
        family_activity = self.make_activity('戶外親子活動', tags=[outdoor, family], search_text='戶外 親子')
        non_family_activity = self.make_activity('戶外音樂活動', tags=[outdoor, self.art], search_text='戶外 音樂')
        user = UserProfile.objects.create(line_user_id='exclude-tag-refine-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='有什麼戶外活動',
            conditions={'tag_names': ['戶外'], 'soft_topics': ['戶外'], 'related_terms': [], 'is_free': None},
            last_activity_ids=[family_activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        route_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'exclude_tag_names': ['親子']}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=route_response):
            handle_line_text_message(user, '不要親子的')

        state = LineConversationState.objects.get(user=user)
        self.assertIn(non_family_activity.id, state.last_activity_ids)
        self.assertNotIn(family_activity.id, state.last_activity_ids)
        self.assertEqual(state.conditions.get('exclude_tag_names'), ['親子'])

    def test_context_router_target_activity_index_answers_second_card(self):
        first = self.make_activity('第一張活動', tags=[self.art], start_offset=5)
        second = self.make_activity('第二張活動', tags=[self.art], start_offset=6)
        second.location = '第二活動地點'
        second.save(update_fields=['location'])
        user = UserProfile.objects.create(line_user_id='target-index-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='藝文活動',
            conditions={'tag_names': ['藝文']},
            last_activity_ids=[first.id, second.id],
            offset=2,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        route_response = SimpleNamespace(
            parsed={'intent': 'activity_followup', 'target_activity_index': 2, 'followup_field': 'location'},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=route_response):
            message = handle_line_text_message(user, '啊第二個呢')

        text = getattr(message, 'text', '')
        self.assertIn('第二張活動', text)
        self.assertIn('第二活動地點', text)

    def test_distance_followup_answers_previous_card_without_searching(self):
        activity = self.make_activity('親子戶外活動', tags=[self.family], start_offset=5)
        activity.district = '大溪'
        activity.location = '大溪河濱公園'
        activity.save(update_fields=['district', 'location'])
        user = UserProfile.objects.create(line_user_id='distance-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='親子活動',
            conditions={'tag_names': ['親子']},
            last_activity_ids=[activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        route_response = SimpleNamespace(
            parsed={'intent': 'activity_followup', 'target_activity_index': 1, 'followup_field': 'distance'},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=route_response):
            message = handle_line_text_message(user, '這個會不會很遠')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('親子戶外活動', text)
        self.assertIn('大溪', text)
        self.assertEqual(state.last_query, '親子活動')
        self.assertEqual(state.last_activity_ids, [activity.id])

    def test_replace_previous_query_resets_dirty_context(self):
        target = self.make_activity('小孩浴場', tags=[self.family], search_text='小孩浴場 親子')
        old = self.make_activity('大溪展館', tags=[self.art], search_text='大溪 展館')
        user = UserProfile.objects.create(line_user_id='replace-previous-query-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='有沒有大一點的，開箱大溪展館是啥',
            conditions={'keyword': '開箱', 'district': '大溪'},
            last_activity_ids=[old.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        route_response = SimpleNamespace(
            parsed={'intent': 'new_search', 'replace_previous_query': True, 'refine_patch': {'keyword': '小孩浴場'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=route_response):
            handle_line_text_message(user, '那小孩浴場呢')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '那小孩浴場呢')
        self.assertNotIn('大溪展館', state.last_query)
        self.assertIn(target.id, state.last_activity_ids)

    def test_distance_phrase_stays_followup_even_if_router_says_refine(self):
        activity = self.make_activity('大溪親子活動', tags=[self.family], start_offset=5)
        activity.district = '大溪'
        activity.location = '大溪河濱公園'
        activity.save(update_fields=['district', 'location'])
        user = UserProfile.objects.create(line_user_id='distance-router-misroute-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='親子活動',
            conditions={'tag_names': ['親子']},
            last_activity_ids=[activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '遠'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            message = handle_line_text_message(user, '這個會不會很遠')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('大溪親子活動', text)
        self.assertIn('大溪', text)
        self.assertEqual(state.last_query, '親子活動')
        self.assertEqual(state.last_activity_ids, [activity.id])

    def test_bare_ordinal_followup_does_not_trigger_more_results(self):
        first = self.make_activity('第一張卡片活動', tags=[self.art], start_offset=5)
        second = self.make_activity('第二張卡片活動', tags=[self.art], start_offset=6)
        second.description = '第二張卡片活動介紹'
        second.save(update_fields=['description'])
        user = UserProfile.objects.create(line_user_id='bare-ordinal-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='藝文活動',
            conditions={'tag_names': ['藝文']},
            last_activity_ids=[first.id, second.id],
            offset=2,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'more_results', 'refine_patch': {}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            message = handle_line_text_message(user, '啊第二個呢')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('第二張卡片活動', text)
        self.assertEqual(state.last_query, '藝文活動')
        self.assertEqual(state.last_activity_ids, [first.id, second.id])

    def test_new_named_short_query_replaces_dirty_keyword_context_even_when_router_refines(self):
        target = self.make_activity('小孩浴場', tags=[self.family], search_text='小孩浴場 親子')
        old = self.make_activity('大溪展館', tags=[self.art], search_text='大溪 展館')
        user = UserProfile.objects.create(line_user_id='refine-replace-dirty-context-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='開箱大溪展館是啥',
            conditions={'keyword': '展館'},
            last_activity_ids=[old.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '小孩浴場'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=router_response):
            handle_line_text_message(user, '那小孩浴場呢')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '那小孩浴場呢')
        self.assertNotIn('大溪展館', state.last_query)
        self.assertIn(target.id, state.last_activity_ids)

    def test_exact_keyword_title_match_survives_bad_ai_rerank(self):
        target = self.make_activity('小孩浴場', tags=[self.family], search_text='小孩浴場 親子', start_offset=20)
        distractors = [
            self.make_activity(f'相近活動{i}', tags=[self.art], search_text='小孩浴場 展覽 藝文', start_offset=i)
            for i in range(1, 8)
        ]
        user = UserProfile.objects.create(line_user_id='exact-keyword-rerank-test')

        with patch('myapp.line_services.rerank_activities_with_ai', side_effect=lambda _user, _query, items, limit=3: [item for item in items if item.id != target.id][:limit]):
            activities, conditions = search_activities_for_line(
                user,
                '那小孩浴場呢',
                limit=3,
                conditions={
                    'keyword': '小孩浴場',
                    'tag_names': ['展覽', '藝文'],
                    'soft_topics': [],
                    'related_terms': ['展覽', '藝文'],
                    'is_free': None,
                },
                return_conditions=True,
            )

        self.assertIn(target.id, [activity.id for activity in activities])

    def test_ticket_fee_phrase_stays_on_previous_activity(self):
        activity = self.make_activity('室內舞台劇', tags=[self.art], start_offset=5)
        activity.is_free = False
        activity.fee_type = 'paid'
        activity.fee_description = '需購票入場'
        activity.save(update_fields=['is_free', 'fee_type', 'fee_description'])
        user = UserProfile.objects.create(line_user_id='ticket-fee-followup-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='室內活動',
            conditions={'tag_names': ['藝文']},
            last_activity_ids=[activity.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '買票'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            message = handle_line_text_message(user, '要買票嗎')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('室內舞台劇', text)
        self.assertIn('需購票入場', text)
        self.assertEqual(state.last_query, '室內活動')
        self.assertEqual(state.last_activity_ids, [activity.id])

    def test_casual_more_phrases_keep_query_and_advance_cards(self):
        activities = [self.make_activity(f'約會活動{i}', tags=[self.art], start_offset=i) for i in range(1, 5)]
        user = UserProfile.objects.create(line_user_id='casual-more-phrase-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='週末約會',
            conditions={'tag_names': ['藝文']},
            last_activity_ids=[activity.id for activity in activities[:3]],
            offset=3,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        handle_line_text_message(user, '還有別的嗎')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '週末約會')
        self.assertIn(activities[3].id, state.last_activity_ids)
        self.assertNotIn(activities[0].id, state.last_activity_ids)

    def test_ordinal_out_of_range_does_not_fall_back_to_first_card(self):
        first = self.make_activity('第一張活動', tags=[self.art], start_offset=5)
        second = self.make_activity('第二張活動', tags=[self.art], start_offset=6)
        user = UserProfile.objects.create(line_user_id='ordinal-out-of-range-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='藝文活動',
            conditions={'tag_names': ['藝文']},
            last_activity_ids=[first.id, second.id],
            offset=2,
            expires_at=timezone.now() + timedelta(minutes=30),
        )

        message = handle_line_text_message(user, '第三個地址')

        text = getattr(message, 'text', '')
        state = LineConversationState.objects.get(user=user)
        self.assertIn('上一輪只有 2 個活動', text)
        self.assertNotIn('第一張活動：地點', text)
        self.assertEqual(state.last_activity_ids, [first.id, second.id])

    def test_short_new_tag_query_replaces_previous_tag_context_when_router_misses_it(self):
        music = Tag.objects.create(name='音樂', tag_type='activity_type')
        market = Tag.objects.create(name='市集', tag_type='activity_type')
        old = self.make_activity('音樂表演', tags=[music], search_text='音樂 表演')
        target = self.make_activity('週末市集', tags=[market], search_text='市集 攤位')
        user = UserProfile.objects.create(line_user_id='short-new-tag-query-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='桃園有音樂表演嗎',
            conditions={'tag_names': ['音樂'], 'soft_topics': ['音樂'], 'related_terms': []},
            last_activity_ids=[old.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'tag_names': ['音樂'], 'soft_topics': ['音樂']}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            handle_line_text_message(user, '那市集呢')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '那市集呢')
        self.assertIn('市集', state.conditions.get('tag_names', []))
        self.assertNotIn('音樂', state.conditions.get('tag_names', []))
        self.assertFalse(state.conditions.get('keyword'))
        self.assertIn(target.id, state.last_activity_ids)

    def test_generic_activity_request_resets_previous_location_context(self):
        old = self.make_activity('中原活動', search_text='中原 中壢')
        old.district = '中壢'
        old.save(update_fields=['district'])
        general = self.make_activity('桃園一般活動', tags=[self.art], search_text='桃園 活動', start_offset=12)
        user = UserProfile.objects.create(line_user_id='generic-activity-reset-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='幫我找中原的活動，中壢的',
            conditions={'keyword': '中原', 'district': '中壢'},
            last_activity_ids=[old.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            handle_line_text_message(user, '幫我找活動')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '幫我找活動')
        self.assertNotIn('中原', state.last_query)
        self.assertNotEqual(state.conditions.get('district'), '中壢')
        self.assertIn(general.id, state.last_activity_ids)

    def test_new_subject_with_description_phrase_replaces_previous_context(self):
        old = self.make_activity('中原文創園區《即刻救原3-珍綜再見》', search_text='中原 戶外 節慶')
        old.district = '中壢'
        old.save(update_fields=['district'])
        calligraphy = self.make_activity('躲貓貓：王意淳書法創作展', tags=[self.art], search_text='書法 展覽 藝文')
        calligraphy.district = '中壢'
        calligraphy.save(update_fields=['district'])
        user = UserProfile.objects.create(line_user_id='new-subject-description-reset-test')
        LineConversationState.objects.create(
            user=user,
            intent='activity_search',
            last_query='幫我找中原的活動，中壢的',
            conditions={'keyword': '中原', 'district': '中壢'},
            last_activity_ids=[old.id],
            offset=1,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        bad_router_response = SimpleNamespace(
            parsed={'intent': 'refine_search', 'refine_patch': {'keyword': '書法展'}},
            provider='test',
            model='mock',
        )

        with patch('myapp.line_services.call_json_with_fallback', return_value=bad_router_response):
            handle_line_text_message(user, '書法展在幹嘛')

        state = LineConversationState.objects.get(user=user)
        self.assertEqual(state.last_query, '書法展在幹嘛')
        self.assertNotIn('中原', state.last_query)
        self.assertIn(calligraphy.id, state.last_activity_ids)
        self.assertNotIn(old.id, state.last_activity_ids)
