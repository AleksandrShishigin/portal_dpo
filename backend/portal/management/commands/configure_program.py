import json
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from portal.models import Program, DocumentRequirement
from portal.fields import validate_required_fields


class Command(BaseCommand):
    help = 'Configure provisional requirements locally, without changing user roles.'

    def add_arguments(self, parser):
        parser.add_argument('program_id', type=int)
        parser.add_argument('--required-fields', nargs='*')
        parser.add_argument('--program-kind', choices=['повышения квалификации', 'профессиональной переподготовки'])
        parser.add_argument('--study-form', choices=['1', '2', '3'])
        parser.add_argument('--documents-file', help='UTF-8 JSON array: title, required, only_if_graduated')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            program = Program.objects.select_for_update().get(pk=options['program_id'])
            if options['required_fields'] is not None:
                validate_required_fields(options['required_fields'])
        except (Program.DoesNotExist, ValidationError):
            raise CommandError('Program or field requirements are invalid.')
        if options['documents_file']:
            try:
                items = json.loads(Path(options['documents_file']).read_text(encoding='utf-8-sig'))
                if not isinstance(items, list):
                    raise ValueError()
                for item in items:
                    if not isinstance(item, dict) or not isinstance(item.get('title'), str) or not item['title'].strip():
                        raise ValueError()
                    for flag in ['required', 'only_if_graduated']:
                        if flag in item and not isinstance(item[flag], bool):
                            raise ValueError()
                    document, _ = DocumentRequirement.objects.get_or_create(program=program, title=item['title'].strip())
                    document.required = item.get('required', True)
                    document.only_if_graduated = item.get('only_if_graduated', False)
                    document.full_clean()
                    document.save()
            except (OSError, ValueError, ValidationError):
                raise CommandError('Invalid documents file. No requirements were changed.')
        if options['required_fields'] is not None:
            program.required_fields = options['required_fields']
        if options['program_kind'] is not None:
            program.program_kind = options['program_kind']
        if options['study_form'] is not None:
            program.study_form = options['study_form']
        program.full_clean()
        program.save(update_fields=['required_fields', 'program_kind', 'study_form'])
        self.stdout.write('Program requirements saved; existing document requirements were not deleted.')
