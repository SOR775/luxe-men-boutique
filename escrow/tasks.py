"""
escrow/tasks.py — Celery periodic tasks for escrow auto-release.

Add to your Celery beat schedule in settings:

    CELERY_BEAT_SCHEDULE = {
        'auto-release-escrows': {
            'task': 'escrow.tasks.auto_release_expired_escrows',
            'schedule': crontab(minute=0, hour='*/1'),  # every hour
        },
    }
"""
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def auto_release_expired_escrows():
    """
    Release escrow funds for all shipments where the buyer has not
    confirmed receipt and the auto-release timer has expired.

    Safe to call multiple times (idempotent).
    """
    try:
        from celery import shared_task  # noqa – only needed at runtime
    except ImportError:
        pass  # Celery not installed; this is fine for tests

    from escrow.models import EscrowTransaction

    candidates = EscrowTransaction.objects.filter(
        status=EscrowTransaction.Status.SHIPPED,
        release_after__lte=timezone.now(),
    ).select_related('order', 'payment')

    released_count = 0
    for escrow in candidates:
        try:
            escrow.release_funds(
                actor=None,
                notes=f'Auto-released after {escrow.AUTO_RELEASE_DAYS} days with no buyer confirmation.',
            )
            released_count += 1
            logger.info(f'[Escrow] Auto-released escrow {escrow.id} for order {escrow.order.order_number}')
        except Exception as exc:
            logger.error(f'[Escrow] Failed to auto-release {escrow.id}: {exc}')

    logger.info(f'[Escrow] Auto-release task complete. {released_count} escrow(s) released.')
    return released_count


# Register as Celery task if Celery is available
try:
    from celery import shared_task
    auto_release_expired_escrows = shared_task(
        name='escrow.tasks.auto_release_expired_escrows'
    )(auto_release_expired_escrows)
except ImportError:
    pass
