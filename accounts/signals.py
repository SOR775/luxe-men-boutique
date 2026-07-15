"""accounts/signals.py"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile_defaults(sender, instance, created, **kwargs):
    """Set up any defaults when a new user is created."""
    if created:
        pass  # Extended profile setup can be added here
