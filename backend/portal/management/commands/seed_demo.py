"""Idempotent synthetic records; never fabricate a person's confirmation."""
from io import BytesIO
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw
from portal.models import User, Program, Application, Document, Event
from portal.services import program_data
from portal.fields import personal_data

class Command(BaseCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != 'config.demo_settings':
            raise CommandError('Only the isolated demonstration environment is supported.')
        user, created = User.objects.get_or_create(email='fictional-student@example.invalid', defaults={
            'first_name': 'Demo', 'last_name': 'Fictional', 'is_active': False})
        if created:
            user.set_unusable_password()
            user.save()
        program = Program.objects.first()
        app, _ = Application.objects.get_or_create(student=user, program=program,
            defaults={'first_name': 'Demo', 'last_name': 'Fictional', 'email': user.email})
        requirement = program.requirements.first()
        if not app.documents.exists():
            image = Image.new('RGB', (640, 320), 'white')
            ImageDraw.Draw(image).text((30, 130), 'FICTIONAL DEMO FILE - NO PERSONAL DATA', fill='black')
            output = BytesIO()
            image.save(output, 'PNG')
            data = output.getvalue()
            import hashlib
            doc = Document(application=app, requirement=requirement, original_name='fictional-demo.png',
                mime_type='image/png', size=len(data), sha256=hashlib.sha256(data).hexdigest())
            doc.file.save('fictional-demo.png', ContentFile(data), save=True)
        operator, created = User.objects.get_or_create(email='fixture-operator@example.invalid', defaults={
            'first_name': 'Тестовый', 'last_name': 'Оператор', 'role': 'operator', 'is_active': False})
        if created:
            operator.set_unusable_password()
            operator.save()
        for status, name in [('review', 'Проверка'), ('accepted', 'Принятие'), ('rejected', 'Отклонение')]:
            student, created = User.objects.get_or_create(email=f'fixture-{status}@example.invalid', defaults={
                'first_name': 'Вымышленный', 'last_name': name, 'is_active': False})
            if created:
                student.set_unusable_password()
                student.save()
            app, created = Application.objects.get_or_create(student=student, program=program, defaults={
                'first_name': student.first_name, 'last_name': student.last_name, 'email': student.email,
                'status': status, 'submitted_at': timezone.now(),
                'decision_reason': 'Вымышленная запись для демонстрации списка заявок.',
                'decided_by': operator if status != 'review' else None,
                'decided_at': timezone.now() if status != 'review' else None})
            if not created:
                continue  # Preserve operator changes and existing records.
            for requirement in program.requirements.all():
                image = Image.new('RGB', (640, 320), 'white')
                ImageDraw.Draw(image).text((30, 130), 'SYNTHETIC DEMO FIXTURE - NO PERSONAL DATA', fill='black')
                output = BytesIO()
                image.save(output, 'PNG')
                data = output.getvalue()
                import hashlib
                document = Document(application=app, requirement=requirement,
                    original_name=f'fictional-{status}.png', mime_type='image/png', size=len(data),
                    sha256=hashlib.sha256(data).hexdigest())
                document.file.save(document.original_name, ContentFile(data), save=True)
            # Fixtures are explicitly synthetic. No consent timestamp/version or
            # pretend user confirmation is assigned to these historical examples.
            app.submission_snapshot = {'demo_fixture': True, 'student': personal_data(app),
                'program': program_data(program), 'documents': list(app.documents.values(
                    'id', 'original_name', 'mime_type', 'size', 'sha256'))}
            app.save(update_fields=['submission_snapshot'])
            Event.objects.create(application=app, actor=operator, action='demo_fixture',
                reason='Синтетическая запись. Подтверждение пользователем не совершалось.')
        self.stdout.write('Fictional draft, review, accepted and rejected fixtures ready; existing records preserved. No user confirmations fabricated.')
