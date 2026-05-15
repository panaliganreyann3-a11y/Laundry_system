import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


CONTACT_RE = re.compile(r'^09\d{9}$')
PASSWORD_LETTER_RE = re.compile(r'[A-Za-z]')
PASSWORD_DIGIT_RE = re.compile(r'\d')
PASSWORD_SPECIAL_RE = re.compile(r'[!@#$%^&*]')
PASSWORD_LOWER_RE = re.compile(r'[a-z]')
PASSWORD_UPPER_RE = re.compile(r'[A-Z]')
DISPOSABLE_EMAIL_DOMAINS = {
    '10minutemail.com', 'guerrillamail.com', 'mailinator.com',
    'tempmail.com', 'temp-mail.org', 'yopmail.com',
}
GMAIL_DOMAINS = {'gmail.com', 'googlemail.com'}


def is_valid_contact(contact):
    return bool(CONTACT_RE.fullmatch((contact or '').strip()))


def is_allowed_email(email):
    value = (email or '').strip().lower()
    try:
        validate_email(value)
    except ValidationError:
        return False
    domain = value.rsplit('@', 1)[-1]
    return domain not in DISPOSABLE_EMAIL_DOMAINS


def is_gmail_email(email):
    value = (email or '').strip().lower()
    try:
        validate_email(value)
    except ValidationError:
        return False
    domain = value.rsplit('@', 1)[-1]
    return domain in GMAIL_DOMAINS


def is_alphanumeric_password(password):
    return bool(PASSWORD_LETTER_RE.search(password or '') and PASSWORD_DIGIT_RE.search(password or ''))


def is_strong_customer_password(password):
    value = password or ''
    return bool(
        len(value) >= 8
        and PASSWORD_LOWER_RE.search(value)
        and PASSWORD_UPPER_RE.search(value)
        and PASSWORD_DIGIT_RE.search(value)
        and PASSWORD_SPECIAL_RE.search(value)
    )
