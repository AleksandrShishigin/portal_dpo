"""Temporary application fields; program-specific requirements need approval."""
from datetime import date
import re
from django.core.exceptions import ValidationError

PERSONAL_FIELDS = ['last_name', 'first_name', 'patronymic', 'email', 'birth_date', 'phone',
                   'passport_series', 'passport_number', 'passport_issued_by', 'passport_issued_on',
                   'passport_department_code', 'registration_address', 'residential_address', 'snils', 'inn', 'referral_source',
                   'institution', 'education_level', 'education_document_received',
                   'education_document_name', 'education_document_series',
                   'education_document_number', 'education_document_date']
EDUCATION_DOCUMENT_FIELDS = ['education_document_name', 'education_document_series',
                             'education_document_number', 'education_document_date']
FIELD_LABELS = {
    'passport_series': 'Серия паспорта', 'passport_number': 'Номер паспорта',
    'passport_issued_by': 'Кем выдан паспорт', 'passport_issued_on': 'Дата выдачи паспорта',
    'passport_department_code': 'Код подразделения паспорта',
    'registration_address': 'Адрес регистрации', 'residential_address': 'Адрес проживания',
    'snils': 'СНИЛС', 'inn': 'ИНН', 'referral_source': 'Кто рекомендовал обучение (необязательно)',
    'last_name': 'Фамилия', 'first_name': 'Имя', 'patronymic': 'Отчество', 'email': 'Email',
    'birth_date': 'Дата рождения', 'phone': 'Контактный телефон', 'institution': 'Учебное заведение',
    'education_level': 'Уровень образования', 'education_document_received': 'Документ об образовании получен',
    'education_document_name': 'Название документа об образовании', 'education_document_series': 'Серия документа',
    'education_document_number': 'Номер документа', 'education_document_date': 'Дата выдачи документа',
}


def default_required_fields():
    return ['last_name', 'first_name', 'email']


def validate_required_fields(value):
    if not isinstance(value, list) or any(not isinstance(v, str) or v not in PERSONAL_FIELDS or v == 'education_document_received' for v in value):
        raise ValidationError('Неизвестные поля требований программы.')


def validate_not_future(value):
    if value and value > date.today():
        raise ValidationError('Дата не может быть в будущем.')


def validate_phone(value):
    if value and (not re.fullmatch(r'\+?[\d ()-]+', value) or not 7 <= len(re.sub(r'\D', '', value)) <= 15):
        raise ValidationError('Укажите телефон: от 7 до 15 цифр, допустимы +, пробелы, скобки и дефисы.')


def required_fields(program, person):
    return [f for f in program.required_fields if f in PERSONAL_FIELDS and
            (f not in EDUCATION_DOCUMENT_FIELDS or person.education_document_received)]


def missing_fields(program, person):
    return [f for f in required_fields(program, person) if getattr(person, f) in ('', None, False)]


def personal_data(person):
    return {f: (getattr(person, f).isoformat() if hasattr(getattr(person, f), 'isoformat') else getattr(person, f))
            for f in PERSONAL_FIELDS}
