"""
core/models.py — Abstract Base Models

All models in LUXE MEN inherit from these base classes to ensure
consistency in timestamps, UUIDs, and soft-delete behaviour.
"""
import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """
    Abstract model that provides self-managed `created_at` and `updated_at` fields.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class UUIDModel(models.Model):
    """
    Abstract model that uses UUID as the primary key.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted records by default."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that includes soft-deleted records."""

    def get_queryset(self):
        return super().get_queryset()


class SoftDeleteModel(models.Model):
    """
    Abstract model providing soft-delete functionality.
    Records are never truly deleted — they are flagged as deleted
    and excluded from default querysets.
    """
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(class)s_deleted',
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, deleted_by=None, *args, **kwargs):
        """Soft delete — flag instead of removing from database."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def restore(self):
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def hard_delete(self, *args, **kwargs):
        """Permanently delete — restricted to Super Administrator only."""
        super().delete(*args, **kwargs)


class BaseModel(UUIDModel, TimeStampedModel):
    """
    Combined base with UUID PK and timestamps.
    Use this for most domain models.
    """
    class Meta:
        abstract = True


class BaseModelWithSoftDelete(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Combined base with UUID PK, timestamps, and soft delete.
    Use for models that should never be permanently deleted in normal use.
    """
    class Meta:
        abstract = True
