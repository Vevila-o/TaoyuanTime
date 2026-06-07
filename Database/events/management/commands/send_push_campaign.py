from django.core.management.base import BaseCommand, CommandError

from events.models import PushCampaign
from events.push_services import send_campaign


class Command(BaseCommand):
    help = 'Send a PushCampaign to LINE users and write PushDeliveryLog rows.'

    def add_arguments(self, parser):
        parser.add_argument('campaign_id', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        campaign = PushCampaign.objects.select_related('activity').filter(id=options['campaign_id']).first()
        if not campaign:
            raise CommandError(f'PushCampaign not found: {options["campaign_id"]}')

        result = send_campaign(campaign, dry_run=options['dry_run'])
        self.stdout.write(f'Campaign={campaign.id} users={result.users} dry_run={options["dry_run"]}')
        if result.error:
            raise CommandError(result.error)
        self.stdout.write(self.style.SUCCESS(
            f'Done. sent={result.sent}, failed={result.failed}, skipped={result.skipped}'
        ))
