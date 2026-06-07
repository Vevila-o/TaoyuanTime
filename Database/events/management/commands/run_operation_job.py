from django.core.management.base import BaseCommand, CommandError

from events.operation_jobs import run_operation_job


class Command(BaseCommand):
    help = 'Run one queued OperationJob and update progress counters.'

    def add_arguments(self, parser):
        parser.add_argument('job_id', type=int)

    def handle(self, *args, **options):
        try:
            job = run_operation_job(options['job_id'])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f'OperationJob #{job.id} {job.job_type} status={job.status} '
            f'processed={job.processed_count}/{job.total_count} '
            f'success={job.success_count} failed={job.failed_count} skipped={job.skipped_count}'
        ))
