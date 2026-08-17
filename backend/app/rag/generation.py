from app.config import Settings
from app.ingestion.embeddings import EmbeddingConfigurationError
from app.rag.prompting import SYSTEM_PROMPT, build_user_prompt


class AnswerGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, question: str, context: str) -> str:
        from openai import AsyncOpenAI

        if self.settings.openai_api_key is None:
            raise EmbeddingConfigurationError("OpenAI answer generation is not configured.")

        client = AsyncOpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        try:
            response = await client.responses.create(
                model=self.settings.openai_chat_model,
                instructions=SYSTEM_PROMPT,
                input=build_user_prompt(question, context),
                temperature=0.1,
                max_output_tokens=self.settings.rag_max_answer_tokens,
                store=False,
            )
            answer = str(response.output_text).strip()
            if not answer:
                raise RuntimeError("OpenAI returned an empty answer.")
            return answer
        finally:
            await client.close()
