from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from events.models import Activity, Tag


class AuditTagQualityCommandTests(TestCase):
    def setUp(self):
        self.region_zhongli = Tag.objects.create(name='中壢', tag_type='region')
        self.region_taoyuan = Tag.objects.create(name='桃園', tag_type='region')
        self.free = Tag.objects.create(name='免費', tag_type='cost')
        self.paid = Tag.objects.create(name='付費', tag_type='cost')
        self.unknown_amount = Tag.objects.create(name='金額未提供', tag_type='cost')
        self.registration = Tag.objects.create(name='需報名', tag_type='cost')
        self.unknown_discount = Tag.objects.create(name='優惠未提供', tag_type='discount')
        self.art = Tag.objects.create(name='藝文', tag_type='activity_type')

    def call_audit(self, *args):
        output = StringIO()
        call_command('audit_tag_quality', *args, stdout=output)
        return output.getvalue()

    def test_apply_safe_syncs_region_from_district(self):
        activity = Activity.objects.create(title='中壢活動', district='中壢區', fee_type='unknown')
        activity.tags.add(self.region_taoyuan, self.unknown_amount, self.unknown_discount)

        output = self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        activity.refresh_from_db()
        self.assertIn('set region=中壢', output)
        self.assertEqual(list(activity.tags.filter(tag_type='region')), [self.region_zhongli])

    def test_apply_safe_sets_district_from_single_region(self):
        activity = Activity.objects.create(title='桃園活動', fee_type='unknown')
        activity.tags.add(self.region_taoyuan, self.unknown_amount, self.unknown_discount)

        self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        activity.refresh_from_db()
        self.assertEqual(activity.district, '桃園區')

    def test_apply_safe_keeps_one_cost_value_tag(self):
        activity = Activity.objects.create(title='免費活動', fee_type='free', is_free=True)
        activity.tags.add(self.free, self.unknown_amount, self.registration, self.unknown_discount)

        self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        cost_names = set(activity.tags.filter(tag_type='cost').values_list('name', flat=True))
        self.assertEqual(cost_names, {'免費', '需報名'})

    def test_apply_safe_expires_active_activity(self):
        activity = Activity.objects.create(
            title='過期活動',
            status='active',
            fee_type='unknown',
            end_date=timezone.now() - timedelta(days=1),
        )
        activity.tags.add(self.unknown_amount, self.unknown_discount)

        output = self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        activity.refresh_from_db()
        self.assertIn('set status=inactive', output)
        self.assertEqual(activity.status, 'inactive')

    def test_apply_safe_adds_unknown_discount_when_missing(self):
        activity = Activity.objects.create(title='無優惠資訊活動', fee_type='unknown')
        activity.tags.add(self.unknown_amount)

        self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        self.assertTrue(activity.tags.filter(tag_type='discount', name='優惠未提供').exists())

    def test_apply_safe_does_not_remove_ambiguous_activity_type(self):
        activity = Activity.objects.create(title='一般活動', fee_type='unknown')
        activity.tags.add(self.art, self.unknown_amount, self.unknown_discount)

        self.call_audit('--apply-safe', '--activity-id', str(activity.id))

        self.assertTrue(activity.tags.filter(tag_type='activity_type', name='藝文').exists())
