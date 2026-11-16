from django.core.management.base import BaseCommand
from portal.models import PendingFileDeletion
from portal.services import cleanup_file


class Command(BaseCommand):
    help = 'Retry committed file cleanup jobs; never delete referenced files.'

    def handle(self, *args, **options):
        for pk in list(PendingFileDeletion.objects.values_list('pk', flat=True)):
            cleanup_file(pk)
        self.stdout.write(f'Remaining cleanup jobs: {PendingFileDeletion.objects.count()}')
