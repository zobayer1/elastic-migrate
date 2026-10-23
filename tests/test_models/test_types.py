from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql, postgresql, sqlite

from esmigrate.models.types import UTCDateTime

PLUS_SIX = timezone(timedelta(hours=6))


def test_utc_datetime_uses_microsecond_datetime_on_mysql():
    """Test fails if UTCDateTime does not use DATETIME(6) on MySQL"""
    impl = UTCDateTime().load_dialect_impl(mysql.dialect())
    assert isinstance(impl, mysql.DATETIME)
    assert impl.fsp == 6


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect()])
def test_utc_datetime_uses_timezone_aware_type_elsewhere(dialect):
    """Test fails if UTCDateTime does not request a timezone-aware type on PostgreSQL and SQLite"""
    impl = UTCDateTime().load_dialect_impl(dialect)
    assert isinstance(impl, DateTime)
    assert impl.timezone is True


def test_utc_datetime_rejects_naive_values():
    """Test fails if UTCDateTime accepts naive datetimes on write"""
    with pytest.raises(ValueError, match="timezone-aware"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1), sqlite.dialect())


def test_utc_datetime_keeps_timezone_on_postgresql():
    """Test fails if UTCDateTime does not bind UTC-aware datetimes on PostgreSQL"""
    value = UTCDateTime().process_bind_param(datetime(2026, 1, 1, 6, tzinfo=PLUS_SIX), postgresql.dialect())
    assert value == datetime(2026, 1, 1, tzinfo=UTC)
    assert value is not None
    assert value.tzinfo == UTC


@pytest.mark.parametrize("dialect", [sqlite.dialect(), mysql.dialect()])
def test_utc_datetime_stores_naive_utc_without_timezone_support(dialect):
    """Test fails if UTCDateTime does not convert to UTC and drop tzinfo on SQLite and MySQL"""
    value = UTCDateTime().process_bind_param(datetime(2026, 1, 1, 6, 0, 0, 123456, tzinfo=PLUS_SIX), dialect)
    assert value == datetime(2026, 1, 1, 0, 0, 0, 123456)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=UTC)),
        (datetime(2026, 1, 1, 6, tzinfo=PLUS_SIX), datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
def test_utc_datetime_returns_utc_aware_values(stored, expected):
    """Test fails if UTCDateTime does not return UTC-aware datetimes on read"""
    value = UTCDateTime().process_result_value(stored, sqlite.dialect())
    assert value == expected
    assert value is not None
    assert value.tzinfo == UTC


def test_utc_datetime_passes_none_through():
    """Test fails if UTCDateTime does not keep NULL values"""
    assert UTCDateTime().process_bind_param(None, sqlite.dialect()) is None
    assert UTCDateTime().process_result_value(None, sqlite.dialect()) is None
