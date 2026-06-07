from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from events.models import Activity, Tag
from events.services import infer_taoyuan_district_from_text


REGION_TO_DISTRICT = {
    '桃園': '桃園區',
    '中壢': '中壢區',
    '平鎮': '平鎮區',
    '八德': '八德區',
    '楊梅': '楊梅區',
    '蘆竹': '蘆竹區',
    '大溪': '大溪區',
    '龍潭': '龍潭區',
    '龜山': '龜山區',
    '大園': '大園區',
    '觀音': '觀音區',
    '新屋': '新屋區',
    '復興': '復興區',
}
COST_VALUE_TAGS = {'免費', '付費', '金額未提供'}
UNKNOWN_DISCOUNT = '優惠未提供'


class Command(BaseCommand):
    help = 'Audit activity tag quality and optionally apply safe deterministic fixes.'

    def add_arguments(self, parser):
        parser.add_argument('--apply-safe', action='store_true', help='Apply only safe deterministic fixes.')
        parser.add_argument('--activity-id', type=int, help='Audit one activity only.')

    def handle(self, *args, **options):
        apply_safe = options['apply_safe']
        activity_id = options.get('activity_id')
        tag_map = {(tag.tag_type, tag.name): tag for tag in Tag.objects.filter(is_active=True)}
        qs = Activity.objects.prefetch_related('tags').order_by('id')
        if activity_id:
            qs = qs.filter(id=activity_id)

        stats = {
            'activities': 0,
            'issues': 0,
            'region_fixes': 0,
            'district_fixes': 0,
            'cost_fixes': 0,
            'discount_fixes': 0,
            'expired_fixes': 0,
        }
        lines = []

        with transaction.atomic():
            for activity in qs:
                stats['activities'] += 1
                changes = self.audit_activity(activity, tag_map)
                if not changes:
                    continue

                stats['issues'] += len(changes)
                for change in changes:
                    stats[change['stat']] += 1
                    lines.append(f"#{activity.id} {change['message']}")
                if apply_safe:
                    self.apply_changes(activity, changes)

        action = 'applied' if apply_safe else 'would_fix'
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. mode={action}, activities={stats['activities']}, issues={stats['issues']}, "
                f"region={stats['region_fixes']}, district={stats['district_fixes']}, "
                f"cost={stats['cost_fixes']}, discount={stats['discount_fixes']}, "
                f"expired={stats['expired_fixes']}"
            )
        )

    def audit_activity(self, activity, tag_map):
        changes = []
        current_tags = list(activity.tags.all())
        current_regions = [tag for tag in current_tags if tag.tag_type == 'region']
        current_cost_values = [tag for tag in current_tags if tag.tag_type == 'cost' and tag.name in COST_VALUE_TAGS]
        current_discounts = [tag for tag in current_tags if tag.tag_type == 'discount']

        district = (activity.district or '').strip()
        if district:
            region_name = district.replace('區', '')
            desired_region = tag_map.get(('region', region_name))
            if desired_region and (
                len(current_regions) != 1 or current_regions[0].id != desired_region.id
            ):
                changes.append({
                    'stat': 'region_fixes',
                    'kind': 'set_region',
                    'tag': desired_region,
                    'remove': current_regions,
                    'message': f"set region={region_name} from district={district}",
                })
        elif len(current_regions) == 1:
            district_name = REGION_TO_DISTRICT.get(current_regions[0].name)
            if district_name:
                changes.append({
                    'stat': 'district_fixes',
                    'kind': 'set_district',
                    'district': district_name,
                    'message': f"set district={district_name} from region={current_regions[0].name}",
                })
        else:
            inferred_district = infer_taoyuan_district_from_text(
                activity.location,
                activity.title,
                activity.description,
                activity.raw_content,
                activity.official_detail_url,
                activity.source_url,
                raw_html_path=activity.raw_html_path,
            )
            if inferred_district:
                changes.append({
                    'stat': 'district_fixes',
                    'kind': 'set_district',
                    'district': inferred_district,
                    'message': f"set district={inferred_district} from activity text",
                })

        desired_cost = self.desired_cost_name(activity)
        desired_cost_tag = tag_map.get(('cost', desired_cost))
        if desired_cost_tag and (
            len(current_cost_values) != 1 or current_cost_values[0].id != desired_cost_tag.id
        ):
            changes.append({
                'stat': 'cost_fixes',
                'kind': 'set_cost',
                'tag': desired_cost_tag,
                'remove': current_cost_values,
                'message': f"set cost={desired_cost} from fee_type={activity.fee_type} is_free={activity.is_free}",
            })

        discount_tag = tag_map.get(('discount', UNKNOWN_DISCOUNT))
        if not activity.has_citizen_card_discount and not current_discounts and discount_tag:
            changes.append({
                'stat': 'discount_fixes',
                'kind': 'add_tag',
                'tag': discount_tag,
                'message': f"add discount={UNKNOWN_DISCOUNT}",
            })

        if activity.status == 'active' and activity.end_date and activity.end_date.date() < timezone.localdate():
            changes.append({
                'stat': 'expired_fixes',
                'kind': 'set_status',
                'status': 'inactive',
                'message': f"set status=inactive because end_date={activity.end_date.date().isoformat()}",
            })

        return changes

    def desired_cost_name(self, activity):
        fee_type = (activity.fee_type or '').strip()
        if fee_type in {'free', 'ticket_free'} or activity.is_free is True:
            return '免費'
        if fee_type == 'paid':
            return '付費'
        return '金額未提供'

    def apply_changes(self, activity, changes):
        save_fields = []
        for change in changes:
            kind = change['kind']
            if kind == 'set_region':
                for tag in change['remove']:
                    activity.tags.remove(tag)
                activity.tags.add(change['tag'])
            elif kind == 'set_district':
                activity.district = change['district']
                save_fields.append('district')
            elif kind == 'set_cost':
                for tag in change['remove']:
                    activity.tags.remove(tag)
                activity.tags.add(change['tag'])
            elif kind == 'add_tag':
                activity.tags.add(change['tag'])
            elif kind == 'set_status':
                activity.status = change['status']
                save_fields.append('status')

        if save_fields:
            activity.save(update_fields=sorted(set(save_fields + ['updated_at'])))
