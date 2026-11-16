from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from portal.models import Program, DocumentRequirement


class Command(BaseCommand):
    help = 'Create three explicitly fictional test programs (safe to repeat).'

    @transaction.atomic
    def handle(self, *args, **options):
        items = [
            ('[ТЕСТ] Аналитика данных', 72, 'Основы анализа и визуализации данных. Вымышленная программа для проверки портала.', ['Документ об образовании']),
            ('[ТЕСТ] Управление проектами', 36, 'Планирование, команда и оценка результатов. Вымышленная тестовая программа.', ['Документ об образовании', 'Заявление на обучение']),
            ('[ТЕСТ] Цифровые инструменты', 48, 'Работа с современными цифровыми инструментами. Вымышленная тестовая программа.', ['Заявление на обучение']),
        ]
        for title, hours, description, requirements in items:
            program, created = Program.objects.get_or_create(title=title, defaults={
                'hours': hours, 'description': description, 'starts_on': date(2027, 2, 1),
                'ends_on': date(2027, 3, 31), 'lms_url': 'https://example.invalid/lms',
                'program_kind': 'повышения квалификации', 'study_form': '1',
            })
            if created:
                for requirement in requirements:
                    DocumentRequirement.objects.create(program=program, title=requirement,
                        only_if_graduated=('образовании' in requirement))
        self.stdout.write(self.style.SUCCESS('Three test programs are available; existing records preserved.'))
