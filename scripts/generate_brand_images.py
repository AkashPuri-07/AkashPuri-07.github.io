"""One-off script to generate favicon + og:image for the portfolio."""
import asyncio
import base64
import os
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage

load_dotenv("/app/backend/.env")
api_key = os.getenv("EMERGENT_LLM_KEY")
OUT = "/app/frontend/public"

FAVICON_PROMPT = (
    "Minimalist luxury brand logo. Warm ivory cream background. "
    "Centered elegant serif capital letter A in champagne gold color. "
    "Refined typography, flat vector aesthetic, editorial luxury feel, square."
)

OG_PROMPT = (
    "An elegant abstract editorial background composition, landscape orientation. "
    "Warm ivory cream color base. Soft peach and rose gold gradient blooms in "
    "opposite corners. Thin decorative concentric gold circles on the right side. "
    "Fine gold hairlines and delicate frosted glass pill shapes floating gracefully. "
    "Generous whitespace on the left side for text overlay. "
    "Luxury magazine aesthetic, refined, airy, sophisticated, no text, no letters."
)


async def gen(prompt: str, session: str, out_name: str, retries: int = 3):
    for attempt in range(1, retries + 1):
        chat = LlmChat(api_key=api_key, session_id=f"{session}-{attempt}", system_message="You are an expert visual designer.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
        try:
            text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
            print(f"[{out_name} attempt {attempt}] text: {(text or '')[:80]!r} images: {len(images) if images else 0}")
            if images:
                path = os.path.join(OUT, out_name)
                with open(path, "wb") as f:
                    f.write(base64.b64decode(images[0]["data"]))
                print(f"Saved {path} ({os.path.getsize(path)} bytes)")
                return
        except Exception as e:
            print(f"[{out_name} attempt {attempt}] ERROR: {type(e).__name__}: {e}")
        await asyncio.sleep(2)
    raise RuntimeError(f"No image returned for {out_name} after {retries} attempts")


async def main():
    await gen(FAVICON_PROMPT, "favicon-gen", "favicon-source.png")
    await gen(OG_PROMPT, "og-gen", "og-image.png")


if __name__ == "__main__":
    asyncio.run(main())
