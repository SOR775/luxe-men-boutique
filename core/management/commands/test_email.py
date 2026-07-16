from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Test sending an email. It will NOT fail silently and will output the exact error.'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The email address to send the test email to.')

    def handle(self, *args, **options):
        email = options['email']
        
        self.stdout.write(self.style.WARNING(f"Current Settings Module: {settings.SETTINGS_MODULE if hasattr(settings, 'SETTINGS_MODULE') else 'Unknown'}"))
        self.stdout.write(self.style.WARNING(f"Using EMAIL_BACKEND: {settings.EMAIL_BACKEND}"))
        self.stdout.write(self.style.WARNING(f"Using EMAIL_HOST: {settings.EMAIL_HOST}"))
        self.stdout.write(self.style.WARNING(f"Using EMAIL_PORT: {settings.EMAIL_PORT}"))
        self.stdout.write(self.style.WARNING(f"Using EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}"))
        self.stdout.write(self.style.WARNING(f"Using DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}"))

        self.stdout.write(self.style.NOTICE(f'\nAttempting to send test email to {email}...'))
        
        try:
            send_mail(
                subject='LUXE MEN - Test Email',
                message='This is a test email to verify that the SMTP configuration is working perfectly.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully sent test email to {email}!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nFailed to send email. Exact Error:\n{e}'))
