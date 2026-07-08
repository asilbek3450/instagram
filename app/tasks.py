import time
from datetime import datetime, timedelta

from app import celery
from app.models.instagram import InstagramAccount
from app.services.report_service import ReportService
from app.services.instagram_service import InstagramService


@celery.task(name='app.tasks.generate_report_task')
def generate_report_task(report_id):
    """
    Celery task to compile the analytics report in the background.
    """
    print(f"[CELERY] Starting report compilation for report ID: {report_id}")

    # Simulate processing time for demonstration
    time.sleep(3)

    success = ReportService.generate_report_file(report_id)
    if success:
        print(f"[CELERY] Report ID {report_id} completed successfully.")
    else:
        print(f"[CELERY] Report ID {report_id} failed.")
    return success


@celery.task(name='app.tasks.refresh_expiring_tokens')
def refresh_expiring_tokens():
    """
    Refresh long-lived Instagram tokens that expire within the next 7 days.
    Scheduled daily via Celery beat (see app/__init__.py).
    """
    threshold = datetime.utcnow() + timedelta(days=7)
    accounts = InstagramAccount.query.filter(
        InstagramAccount.is_simulated.is_(False),
        InstagramAccount.access_token.isnot(None),
        InstagramAccount.token_expires_at.isnot(None),
        InstagramAccount.token_expires_at <= threshold,
    ).all()

    refreshed = 0
    for acc in accounts:
        if InstagramService.refresh_access_token(acc.id):
            refreshed += 1
    print(f"[CELERY] Refreshed {refreshed}/{len(accounts)} expiring tokens.")
    return refreshed


@celery.task(name='app.tasks.sync_all_real_accounts')
def sync_all_real_accounts():
    """
    Pull fresh data from the Instagram Graph API for every connected real
    account. Scheduled daily via Celery beat.
    """
    accounts = InstagramAccount.query.filter(
        InstagramAccount.is_simulated.is_(False),
        InstagramAccount.access_token.isnot(None),
    ).all()

    synced = 0
    for acc in accounts:
        try:
            if InstagramService.sync_real_account_data(acc.id):
                synced += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[CELERY] Sync failed for account {acc.id}: {exc}")
    print(f"[CELERY] Synced {synced}/{len(accounts)} real accounts.")
    return synced
