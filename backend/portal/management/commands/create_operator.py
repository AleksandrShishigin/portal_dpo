from getpass import getpass
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import IntegrityError
from portal.models import User


class Command(BaseCommand):
    help = 'Create an operator using interactive hidden password input.'

    def handle(self, *args, **options):
        email = input('Email: ').strip().lower()
        first_name = input('First name: ').strip()
        last_name = input('Last name: ').strip()
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError('Invalid email.')
        if not first_name or not last_name:
            raise CommandError('First and last name are required.')
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError('Account already exists; it will not be modified.')
        password = getpass('Password: ')
        if password != getpass('Confirm password: '):
            raise CommandError('Passwords do not match.')
        try:
            validate_password(password, User(email=email, first_name=first_name, last_name=last_name))
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        try:
            User.objects.create_user(email, password, first_name=first_name, last_name=last_name,
                                     role='operator', is_staff=False, is_superuser=False)
        except IntegrityError:
            raise CommandError('Account already exists; it will not be modified.')
        self.stdout.write(self.style.SUCCESS('Operator created without Django administrator privileges.'))
