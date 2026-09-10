import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.orchestrator import Orchestrator
from providers.openai_compatible import OpenAICompatibleProvider


load_dotenv()

router = APIRouter(prefix="/api", tags=["Chat"])

orchestrator = Orchestrator()


# NVIDIA configuration
nvidia_api_key = os.getenv("NVIDIA_API_KEY")

nvidia_base_url = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1"
)

nvidia_model = os.getenv(
    "NVIDIA_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b"
)

# Register NVIDIA DeepSeek
orchestrator.register_provider(
    "nemotron",
    OpenAICompatibleProvider(
        name="nemotron",
        base_url=nvidia_base_url,
        api_key=nvidia_api_key
    )
)


class ChatRequest(BaseModel):
    message: str
    provider: str = "nemotron"
    model: str | None = None


@router.post("/chat")
async def chat(request: ChatRequest):

    provider = orchestrator.get_provider(request.provider)

    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{request.provider}' is not configured"
        )

    try:
        response = await provider.generate(
            messages=[
                {
                    "role": "user",
                    "content": request.message
                }
            ],
            model=request.model or nvidia_model
        )

        return {
            "provider": request.provider,
            "model": request.model or nvidia_model,
            "response": response
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )