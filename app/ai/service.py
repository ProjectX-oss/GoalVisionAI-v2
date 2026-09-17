from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY


class AIService:

    def __init__(self):
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    async def ask(self, prompt: str) -> str:
        response = await self.client.responses.create(
            model="gpt-5",
            input=prompt
        )

        return response.output_text