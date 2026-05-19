from abc import ABC, abstractmethod

import httpx

from app.schemas.job import RawJob


class ATSClient(ABC):
    def __init__(self, http_client: httpx.AsyncClient, config: dict):
        self.http = http_client
        self.config = config

    @abstractmethod
    async def fetch_jobs(self) -> list[RawJob]:
        ...
