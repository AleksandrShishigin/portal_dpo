import hashlib
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from .models import User


class RecoveryIPThrottle(SimpleRateThrottle):
    scope = 'recovery_ip'
    rate = '5/hour'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class RecoveryEmailThrottle(RecoveryIPThrottle):
    scope = 'recovery_email'

    def get_cache_key(self, request, view):
        email = str(request.data.get('email', '')).strip().casefold()
        return self.cache_format % {'scope': self.scope, 'ident': hashlib.sha256(email.encode()).hexdigest()}


class PasswordAttemptThrottle(RecoveryIPThrottle):
    scope = 'password_attempt'
    rate = '10/hour'


class PrivatePasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        # The standard form supplies the standard Django one-time token and UID.
        subject = ''.join(render_to_string(subject_template_name, context).splitlines())
        body = render_to_string(email_template_name, context)
        try:
            EmailMultiAlternatives(subject, body, from_email, [to_email]).send(fail_silently=True)
        except Exception:
            # Never log message bodies, reset tokens or SMTP credentials.
            pass


class PasswordChangeView(APIView):
    throttle_classes = [PasswordAttemptThrottle]

    def post(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            form = PasswordChangeForm(user, data=request.data)
            if not form.is_valid():
                raise ValidationError(form.errors)
            form.save()
        update_session_auth_hash(request, user)
        return Response({'detail': 'Пароль изменён. Другие сеансы завершатся при следующем запросе.', 'csrfToken': get_token(request)})


@method_decorator(csrf_protect, name='dispatch')
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RecoveryIPThrottle, RecoveryEmailThrottle]

    def post(self, request):
        email = serializers.EmailField().run_validation(request.data.get('email', ''))
        form = PrivatePasswordResetForm({'email': email.strip().lower()})
        if form.is_valid():
            form.save(from_email=settings.DEFAULT_FROM_EMAIL,
                      subject_template_name='portal/password_reset_subject.txt',
                      email_template_name='portal/password_reset_email.txt',
                      domain_override='localhost',
                      extra_email_context={'frontend_url': settings.FRONTEND_URL})
        return Response({'detail': 'Запрос принят. Если адрес зарегистрирован и отправка доступна, вы получите письмо с инструкцией.'}, status=202)


@method_decorator(csrf_protect, name='dispatch')
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordAttemptThrottle]

    def post(self, request):
        try:
            user_id = force_str(urlsafe_base64_decode(str(request.data.get('uid', ''))))
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user_id, is_active=True)
                token = str(request.data.get('token', ''))
                if not default_token_generator.check_token(user, token):
                    raise ValueError()
                form = SetPasswordForm(user, data=request.data)
                if not form.is_valid():
                    raise ValidationError(form.errors)
                form.save()
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            raise ValidationError({'detail': 'Ссылка недействительна или срок её действия истёк. Запросите новую.'})
        return Response({'detail': 'Пароль обновлён. Войдите с новым паролем.'})
