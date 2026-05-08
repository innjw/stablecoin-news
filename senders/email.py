"""Resend API 기반 이메일 발송.

https://resend.com/docs/api-reference/emails/send-email
무료 티어: 일 100통 / 월 3,000통.
"""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.resend.com/emails"


def send_email(
    to: list[str],
    subject: str,
    html: str,
    from_name: str,
    from_email: str,
    reply_to: str | None = None,
) -> bool:
    """단일 이메일 발송. 성공 여부 반환.

    Resend는 한 번의 호출로 여러 수신자에게 보낼 수 있다.
    가족·지인 수준이면 BCC 대신 to에 다 넣어도 되지만, 
    프라이버시 차원에서 한 명씩 개별 발송이 안전하다.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.error("RESEND_API_KEY 미설정")
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    success_count = 0
    for recipient in to:
        payload = {
            "from": f"{from_name} <{from_email}>",
            "to": [recipient],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        try:
            r = requests.post(ENDPOINT, headers=headers, json=payload, timeout=15)
            r.raise_for_status()
            success_count += 1
            logger.info("발송 성공: %s", recipient)
        except Exception as e:
            logger.error("발송 실패 [%s]: %s", recipient, e)

    return success_count == len(to)
