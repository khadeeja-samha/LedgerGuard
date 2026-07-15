import os
import time
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIStatusError

# Load environment variables
load_dotenv()

class NimClient:
    def __init__(self, api_key: str = None):
        # Read NIM_API_KEY and NIM_MODEL from environment variables if not passed explicitly
        self.api_key = api_key or os.getenv("NIM_API_KEY")
        self.model = os.getenv("NIM_MODEL", "nvidia/nemotron-3-super-120b-a12b")
        
        if not self.api_key:
            raise ValueError("NIM_API_KEY environment variable or parameter is not set.")

        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=self.api_key
        )

    def generate(self, system_prompt: str, user_prompt: str, reasoning: bool = True, max_tokens: int = 4096) -> str:
        """
        Generates content from the configured NIM LLM.
        
        Uses NVIDIA's recommended defaults:
          - temperature: 1
          - top_p: 0.95
        
        Passes exact reasoning parameters in extra_body.
        Retries up to 3 attempts total with exponential backoff on HTTP 429 Rate Limit error.
        Reraises all other errors explicitly.
        """
        attempts = 3
        backoff = 2
        
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=1.0,
                    top_p=0.95,
                    max_tokens=max_tokens,
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": reasoning},
                        "reasoning_budget": 8192 if reasoning else 0
                    },
                    timeout=90.0
                )
                
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    raise RuntimeError("NIM API generation truncated due to max_tokens limit.")

                content = response.choices[0].message.content
                if content is None:
                    # In case content is null for some reason (e.g. filtered or empty response)
                    raise RuntimeError("NIM API returned an empty or null content response.")
                
                return content.strip()
                
            except RateLimitError as e:
                if attempt == attempts:
                    raise RuntimeError(f"NIM API rate limit exceeded (HTTP 429) after {attempts} attempts: {e}") from e
                
                sleep_time = backoff ** attempt
                time.sleep(sleep_time)
                
            except APIStatusError as e:
                # Any other API error status (e.g. 401, 500, etc.)
                raise RuntimeError(
                    f"NIM API Status Error: Code {e.status_code}. Response: {e.message}"
                ) from e
                
            except Exception as e:
                # Catch-all for network or local setup errors
                raise RuntimeError(f"NIM API unexpected error: {str(e)}") from e
