from datetime import datetime

import httpx

from app.config import FOOTBALL_API_KEY


class FootballClient:

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self):
        self.headers = {
            "x-apisports-key": FOOTBALL_API_KEY
        }

    async def fixtures(self):

        today = datetime.now().strftime("%Y-%m-%d")

        async with httpx.AsyncClient() as client:

            response = await client.get(
                f"{self.BASE_URL}/fixtures",
                headers=self.headers,
                params={
                    "date": today
                }
            )

            response.raise_for_status()

            return response.json()