"""DOCX generation from frozen application data. Never reads the live profile."""
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from xml.dom import minidom
from zipfile import ZipFile, ZIP_DEFLATED
from zipfile import BadZipFile
from contextlib import contextmanager
from django.db import transaction

from django.core.files.base import ContentFile
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .fields import FIELD_LABELS, personal_data
from .services import program_data

TEMPLATES = Path(__file__).parent / 'document_templates'
MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
FORMS = {'1': 'очной', '2': 'очно-заочной', '3': 'заочной'}
KINDS = ['повышения квалификации', 'профессиональной переподготовки']
PERSON_REQUIRED = ['last_name', 'first_name', 'email', 'birth_date', 'phone', 'passport_series',
                   'passport_number', 'passport_issued_by', 'passport_issued_on',
                   'passport_department_code', 'registration_address', 'residential_address', 'snils']
LEGACY_WARNING = ('В этой заявке нет полного исторического снимка реквизитов для DOCX. '
                  'Текущие данные профиля не используются. Заявление восстановить нельзя; '
                  'для договора оператор должен проверить и заполнить реквизиты отдельно.')


@contextmanager
def artifact_transaction():
    from .services import queue_file_deletion
    allocated = []
    try:
        with transaction.atomic():
            yield allocated
    except Exception as exc:
        for path in allocated:
            queue_file_deletion(path)
        if isinstance(exc, (OSError, ValueError, BadZipFile)):
            raise ValidationError({'detail': 'Не удалось сформировать или сохранить DOCX. Изменения не зарегистрированы. Повторите попытку.'}) from None
        raise


def source_data(app):
    if app.status == 'draft':
        return {'student': personal_data(app), 'program': program_data(app.program)}
    return {'student': dict(app.submission_snapshot.get('student', {})),
            'program': dict(app.submission_snapshot.get('program', {}))}


def historical_warning(app):
    if app.status != 'draft' and (app.submission_snapshot.get('legacy_reconstructed') or
            any(k not in app.submission_snapshot.get('student', {}) for k in PERSON_REQUIRED + ['inn'])):
        return LEGACY_WARNING
    return ''


def person_errors(person, statement=False, learner_inn=False):
    fields = PERSON_REQUIRED + (['inn', 'institution', 'education_level'] if statement else ['inn'] if learner_inn else [])
    if statement and person.get('education_document_received'):
        fields += ['education_document_name', 'education_document_number', 'education_document_date']
    errors = {k: f'Заполните поле «{FIELD_LABELS[k]}».' for k in fields if not person.get(k)}
    for k, pattern in [('passport_series', r'[0-9]{4}'), ('passport_number', r'[0-9]{6}'),
                       ('passport_department_code', r'[0-9]{3}-[0-9]{3}'),
                       ('snils', r'(?:[0-9]{11}|[0-9]{3}-[0-9]{3}-[0-9]{3} [0-9]{2})'), ('inn', r'[0-9]{12}')]:
        if person.get(k) and (k != 'inn' or statement or learner_inn) and not re.fullmatch(pattern, person[k]):
            errors[k] = f'Проверьте формат поля «{FIELD_LABELS[k]}».'
    return errors


def statement_errors(app):
    data = source_data(app)
    errors = person_errors(data['student'], statement=True)
    if historical_warning(app):
        errors['detail'] = LEGACY_WARNING
    if data['program'].get('program_kind') not in KINDS:
        errors['program_kind'] = 'Не указан вид программы. Обратитесь к оператору ДПО.'
    return errors


def template_bytes(kind):
    return (TEMPLATES / f'{kind}.docx').read_bytes()


def template_fields(template):
    with ZipFile(BytesIO(template)) as source:
        return set(re.findall(r'\{\{([a-z_]+)\}\}', source.read('word/document.xml').decode('utf-8')))


def render(template, values):
    with ZipFile(BytesIO(template)) as source:
        dom = minidom.parseString(source.read('word/document.xml'))
        for text in dom.getElementsByTagName('w:t'):
            raw = ''.join(c.data for c in text.childNodes if c.nodeType == c.TEXT_NODE)
            def substitute(match):
                key = match.group(1)
                if key not in values:
                    raise ValueError('Unsupported template field')
                return str(values[key])
            replaced = re.sub(r'\{\{([a-z_]+)\}\}', substitute, raw)
            if '{{' in replaced or '}}' in replaced:
                raise ValueError('Unresolved template field')
            if replaced != raw:
                for child in list(text.childNodes):
                    text.removeChild(child)
                text.appendChild(dom.createTextNode(replaced))
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as target:
            for info in source.infolist():
                target.writestr(info, dom.toxml(encoding='utf-8') if info.filename == 'word/document.xml' else source.read(info.filename))
        return output.getvalue()


def dot_date(value):
    return date.fromisoformat(str(value)).strftime('%d.%m.%Y') if value else ''


def values_for(data):
    p, program = data['student'], data['program']
    from .models import User
    education_labels = dict(User._meta.get_field('education_level').choices)
    education = ', '.join(filter(None, [education_labels.get(p.get('education_level'), ''), p.get('institution')]))
    if p.get('education_document_received'):
        education += ', ' + ' '.join(filter(None, [p.get('education_document_name'), p.get('education_document_series'),
                                                    p.get('education_document_number'), dot_date(p.get('education_document_date'))]))
    else:
        education += ', обучение продолжается'
    return {**p, 'full_name': ' '.join(p.get(k, '') for k in ['last_name', 'first_name', 'patronymic']).strip(),
            'birth_date': dot_date(p.get('birth_date')), 'passport': f"{p.get('passport_series', '')} {p.get('passport_number', '')}",
            'passport_issue': f"{p.get('passport_issued_by', '')}, {dot_date(p.get('passport_issued_on'))}, код {p.get('passport_department_code', '')}",
            'education': education, 'referral_source': p.get('referral_source') or 'Не указан',
            'program_title': program.get('title', ''), 'program_kind': program.get('program_kind', ''),
            'hours': program.get('hours', ''), 'study_form_text': FORMS.get(program.get('study_form'), ''),
            'starts_on': dot_date(program.get('starts_on')), 'ends_on': dot_date(program.get('ends_on'))}


def build_statement(app):
    errors = statement_errors(app)
    if errors:
        raise ValidationError(errors)
    data = source_data(app)
    template = template_bytes('statement')
    return data, template, render(template, values_for(data))


def save_artifact(instance, data, template, content, allocated):
    instance.snapshot = data
    instance.template_version = 'sha256:' + sha256(template).hexdigest()
    instance.sha256 = sha256(content).hexdigest()
    for field, value in [(instance.template_file, template), (instance.file, content)]:
        field.save('document.docx', ContentFile(value), save=False)
        allocated.append(field.name)
        # A failed/partial storage write must never commit a registration.
        with field.open('rb') as saved:
            if sha256(saved.read()).digest() != sha256(value).digest():
                raise OSError('Storage verification failed')
    instance.save()


class ContractInput(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0, max_value=2147483647)
    number_code = serializers.ChoiceField(choices=['О', 'Р'])
    realization_year = serializers.RegexField(r'^[0-9]{2}/[0-9]{2}$')
    department = serializers.CharField(max_length=20)
    contract_date = serializers.DateField()
    university_representative = serializers.CharField(max_length=500)
    authority_basis = serializers.CharField(max_length=500)
    university_email = serializers.EmailField()


def contract_number(data):
    # Exact HTML rule: prepend zero only when the serial has three digits.
    serial = str(serializers.IntegerField().run_validation(data['sequence']))
    if len(serial) == 3:
        serial = '0' + serial
    department = re.sub(r'\s+', '', data['department'])
    return f"{serial}-2{data['number_code']}10/{data['program']['study_form']}-{data['realization_year']}-{department}"


def contract_defaults(app):
    from django.utils import timezone
    return {**source_data(app), 'sequence': '', 'number_code': '', 'realization_year': '', 'department': '',
            'contract_date': timezone.localdate().isoformat(), 'university_representative': '',
            'authority_basis': '', 'university_email': ''}


def validate_contract(data, template):
    s = ContractInput(data=data)
    s.is_valid()
    errors = dict(s.errors)
    errors.update(person_errors(data.get('student', {}), learner_inn='inn' in template_fields(template)))
    program = data.get('program', {})
    from .serializers import ApplicationEditSerializer
    person = ApplicationEditSerializer(data=data.get('student', {}))
    if not person.is_valid():
        errors.update(person.errors)
    for key, field in [('title', serializers.CharField(max_length=250)), ('hours', serializers.IntegerField(min_value=1)),
                       ('program_kind', serializers.ChoiceField(choices=KINDS)), ('study_form', serializers.ChoiceField(choices=list(FORMS))),
                       ('starts_on', serializers.DateField()), ('ends_on', serializers.DateField())]:
        try:
            field.run_validation(program.get(key))
        except ValidationError as exc:
            errors['program_' + key] = exc.detail
    if program.get('starts_on') and program.get('ends_on') and program['starts_on'] > program['ends_on']:
        errors['program_ends_on'] = 'Окончание обучения раньше начала.'
    if data.get('student', {}).get('birth_date') and data.get('contract_date') and data['student']['birth_date'] > data['contract_date']:
        errors['contract_date'] = 'Дата договора раньше даты рождения.'
    return errors


def contract_preview(data):
    number_fields = ['sequence', 'number_code', 'realization_year', 'department']
    fields = ContractInput().fields
    try:
        for k in number_fields:
            fields[k].run_validation(data.get(k))
    except ValidationError:
        return ''
    if data.get('program', {}).get('study_form') in FORMS:
        return contract_number(data)
    return ''


def build_contract(data, template):
    errors = validate_contract(data, template)
    if errors:
        raise ValidationError(errors)
    number = contract_number(data)
    values = {**values_for(data), **{k: data[k] for k in ContractInput().fields},
              'contract_date': dot_date(data['contract_date']), 'number': number}
    return number, render(template, values)
