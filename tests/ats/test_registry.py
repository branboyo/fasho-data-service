import httpx
import pytest

from app.ats.greenhouse import GreenhouseClient
from app.ats.icims import ICIMSClient
from app.ats.registry import UnknownATSError, get_client
from app.ats.workday import WorkdayClient
from app.models.company import ATSType


async def test_returns_greenhouse_client():
    async with httpx.AsyncClient() as http:
        client = get_client(ATSType.GREENHOUSE, {"board_token": "acme"}, http)
    assert isinstance(client, GreenhouseClient)


async def test_returns_workday_client():
    async with httpx.AsyncClient() as http:
        client = get_client(ATSType.WORKDAY, {"tenant": "t", "wd_number": 5, "site": "s"}, http)
    assert isinstance(client, WorkdayClient)


async def test_returns_icims_client():
    async with httpx.AsyncClient() as http:
        client = get_client(ATSType.ICIMS, {"company_slug": "walgreens"}, http)
    assert isinstance(client, ICIMSClient)


def test_raises_for_unknown_ats():
    with pytest.raises(UnknownATSError):
        get_client("carrier_pigeon", {}, None)
