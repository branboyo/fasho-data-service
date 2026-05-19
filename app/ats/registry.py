import httpx

from app.ats.base import ATSClient
from app.ats.greenhouse import GreenhouseClient
from app.ats.icims import ICIMSClient
from app.ats.workday import WorkdayClient
from app.models.company import ATSType

_REGISTRY: dict[ATSType, type[ATSClient]] = {
    ATSType.GREENHOUSE: GreenhouseClient,
    ATSType.WORKDAY: WorkdayClient,
    ATSType.ICIMS: ICIMSClient,
}


class UnknownATSError(ValueError):
    pass


def get_client(ats_type: ATSType | str, config: dict, http_client: httpx.AsyncClient) -> ATSClient:
    cls = _REGISTRY.get(ats_type)
    if cls is None:
        raise UnknownATSError(f"No client registered for ATS type: {ats_type}")
    return cls(http_client=http_client, config=config)
