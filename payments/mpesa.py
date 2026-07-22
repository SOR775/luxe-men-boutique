"""
payments/mpesa.py — Safaricom Daraja API v3 Integration Service

Supports:
  - OAuth2 token generation
  - STK Push (Lipa na M-Pesa Online)
  - STK Push Query (status check)
  - Callback processing
  - Sandbox & Production environments
"""
import base64
import json
import logging
from datetime import datetime

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class MpesaClient:
    """
    Client for the Safaricom Daraja API.
    Configure via environment variables (see .env).
    """

    SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
    PRODUCTION_BASE = "https://api.safaricom.co.ke"

    def __init__(self):
        self.consumer_key     = settings.MPESA_CONSUMER_KEY
        self.consumer_secret  = settings.MPESA_CONSUMER_SECRET
        self.business_shortcode = settings.MPESA_SHORTCODE
        self.passkey          = settings.MPESA_PASSKEY
        self.callback_url     = settings.MPESA_CALLBACK_URL
        self.environment      = getattr(settings, 'MPESA_ENVIRONMENT', 'sandbox')
        self.base_url         = self.SANDBOX_BASE if self.environment == 'sandbox' else self.PRODUCTION_BASE

    # ── Authentication ────────────────────────────────────────────────────────

    def get_access_token(self) -> str | None:
        """
        Obtain a short-lived OAuth2 access token from Daraja.
        Returns the token string or None on failure. Caches the token to avoid rate limits.
        """
        import time
        from django.core.cache import cache

        cache_key = f"mpesa_access_token_{self.environment}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        for attempt in range(3):
            try:
                response = requests.get(
                    url,
                    headers={"Authorization": f"Basic {encoded}"},
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()
                token = data.get("access_token")
                if token:
                    expires_in = int(data.get("expires_in", 3500)) - 60
                    cache.set(cache_key, token, timeout=max(60, expires_in))
                    return token
            except Exception as e:
                logger.warning(f"[M-Pesa] OAuth token attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(1)

        logger.error("[M-Pesa] Failed to get access token after 3 retries.")
        return None

    # ── STK Push ──────────────────────────────────────────────────────────────

    def get_password(self) -> tuple[str, str]:
        """Generate the Base64-encoded password and timestamp for STK Push."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{self.business_shortcode}{self.passkey}{timestamp}"
        password = base64.b64encode(raw.encode()).decode()
        return password, timestamp

    def stk_push(self, phone_number: str, amount: int, account_reference: str, transaction_desc: str) -> dict:
        """
        Initiate an STK Push payment request.

        Args:
            phone_number: Customer phone in 254XXXXXXXXX format
            amount: Amount in whole KES (no decimals)
            account_reference: Short order reference (max 12 chars)
            transaction_desc: Description (max 13 chars)

        Returns:
            Daraja API response dict or {'error': str} on failure.
        """
        token = self.get_access_token()
        if not token:
            return {"error": "Could not obtain M-Pesa access token."}

        password, timestamp = self.get_password()

        payload = {
            "BusinessShortCode": self.business_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": self.business_shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": self.callback_url,
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:13],
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15
            )
            try:
                data = response.json()
            except Exception as parse_err:
                logger.error(f"[M-Pesa STK Push] Invalid JSON response: {parse_err}")
                return {"error": f"Invalid response from Safaricom: HTTP {response.status_code}"}
            logger.info(f"[M-Pesa STK Push] Response: {data}")
            return data
        except Exception as e:
            logger.error(f"[M-Pesa STK Push] Request failed: {e}")
            return {"error": str(e)}

    # ── STK Query ─────────────────────────────────────────────────────────────

    def stk_query(self, checkout_request_id: str) -> dict:
        """Query the status of an existing STK Push transaction."""
        token = self.get_access_token()
        if not token:
            return {"error": "Could not obtain M-Pesa access token."}

        password, timestamp = self.get_password()

        payload = {
            "BusinessShortCode": self.business_shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15
            )
            try:
                data = response.json()
            except Exception as parse_err:
                logger.error(f"[M-Pesa Query] Failed to parse JSON response: {parse_err}")
                return {"error": f"Invalid response from Safaricom: HTTP {response.status_code}"}

            # Detect Safaricom rate-limit (SpikeArrestViolation)
            if 'fault' in data:
                fault_str = str(data.get('fault', {}).get('faultstring', '')).lower()
                if 'spike arrest' in fault_str or 'ratelimit' in fault_str.replace(' ', ''):
                    logger.warning("[M-Pesa Query] Rate limited by Safaricom — backing off.")
                    return {'rate_limited': True}
                return {'error': data['fault'].get('faultstring', 'Safaricom API error.')}
            return data
        except Exception as e:
            logger.error(f"[M-Pesa Query] Failed: {e}")
            return {"error": str(e)}

    # ── Callback Processor ────────────────────────────────────────────────────

    @staticmethod
    def process_callback(callback_data: dict) -> dict:
        """
        Parse a Daraja STK Push callback payload.
        Returns a normalized dict with keys:
          result_code, result_desc, receipt, phone, amount, date, checkout_request_id
        """
        try:
            body = callback_data.get("Body", {})
            stkCallback = body.get("stkCallback", {})
            result_code = str(stkCallback.get("ResultCode", "1"))
            result_desc = stkCallback.get("ResultDesc", "")
            checkout_request_id = stkCallback.get("CheckoutRequestID", "")
            receipt = phone = amount = date = None

            if result_code == "0":
                items = stkCallback.get("CallbackMetadata", {}).get("Item", [])
                for item in items:
                    name = item.get("Name")
                    value = item.get("Value")
                    if name == "MpesaReceiptNumber":
                        receipt = value
                    elif name == "PhoneNumber":
                        phone = str(value)
                    elif name == "Amount":
                        amount = value
                    elif name == "TransactionDate":
                        date = str(value)

            return {
                "result_code": result_code,
                "result_desc": result_desc,
                "checkout_request_id": checkout_request_id,
                "receipt": receipt,
                "phone": phone,
                "amount": amount,
                "date": date,
            }
        except Exception as e:
            logger.error(f"[M-Pesa Callback] Parse error: {e}")
            return {"error": str(e)}


# Module-level singleton client
mpesa_client = MpesaClient()
