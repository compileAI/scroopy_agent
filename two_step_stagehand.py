import asyncio, os, sys, json, aiofiles
from typing import Optional, Dict, Any
from datetime import date
from dotenv import load_dotenv; load_dotenv()

from pydantic import BaseModel, Field, field_validator, HttpUrl
import dateparser

from stagehand import Stagehand, StagehandConfig


# ---------- 1️⃣  small schemas ----------------------------------------------
class LinkList(BaseModel):
    link: HttpUrl = Field(..., min_length=1)   # enforce full URLs

class Article(BaseModel):
    title: str
    author: str
    date_published: date | None = None
    content: list[str]

    # lenient natural-language date → ISO date
    @field_validator("date_published", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not v:
            return None
        parsed = dateparser.parse(v)
        if not parsed:
            raise ValueError("unparseable date")
        return parsed.date()

# ---------- 2️⃣  Stagehand client (local, Gemini) ---------------------------
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    sys.exit("❌  Put GEMINI_API_KEY in your .env")

CFG = StagehandConfig(
    env="LOCAL",
    model_name="gemini/gemini-2.0-flash",
    enable_caching=True,
    cache_dir="stagehand-cache",
)

# ---------- 3️⃣  logic -------------------------------------------------------
async def extract_article(sh: Stagehand, url: str) -> Article:
    await sh.page.goto(url, timeout=45_000)
    rec: Article | dict = await sh.page.extract(
        instruction=(
            "Extract the article title, author, ISO publication date "
            "(YYYY-MM-DD) and every body paragraph as an array named content. "
            "Ignore ads, nav, footer, sidebar."
        ),
        schema=Article,
    )
    return rec if isinstance(rec, Article) else Article(**rec)

# Get the cached value (None if it doesn't exist)
async def get_cache(key: str) -> Optional[Dict[str, Any]]:
    try:
        async with aiofiles.open("cache.json", 'r') as f:
            cache_content = await f.read()
            parsed = json.loads(cache_content)
            return parsed.get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

# Set the cache value
async def set_cache(key: str, value: Dict[str, Any]) -> None:
    try:
        async with aiofiles.open("cache.json", 'r') as f:
            cache_content = await f.read()
            parsed = json.loads(cache_content)
    except (FileNotFoundError, json.JSONDecodeError):
        parsed = {}
    
    parsed[key] = value
    
    async with aiofiles.open("cache.json", 'w') as f:
        await f.write(json.dumps(parsed))

# Check the cache, get the action, and run it
# If self_heal is true, we'll attempt to self-heal if the action fails
async def act_with_cache(page, key: str, prompt: str, self_heal: bool = False):
    try:
        cache_exists = await get_cache(key)

        if cache_exists:
            # Get the cached action
            action = await get_cache(prompt)
        else:
            # Get the observe result (the action)
            actions = await page.observe(prompt)
            action = actions[0]

            # Cache the action
            await set_cache(prompt, action)

        # Run the action (no LLM inference)
        await page.act(action)
    except Exception as e:
        print(f"Error: {e}")
        # in self_heal mode, we'll retry the action
        if self_heal:
            print("Attempting to self-heal...")
            await page.act(prompt)
        else:
            raise e

async def main(list_page: str):
    sh = Stagehand(CFG)
    await sh.init()

    # -- step 1: get first article link(s) -----------------------------------
    await sh.page.goto(list_page, timeout=45_000)
    link_result = await sh.page.extract(
        instruction=("extract the link to the most recent blog post."),
        schema=LinkList,
    )
    link = link_result.link
    print(f"🔗: {link}")

    # -- step 2: visit each link & extract article ---------------------------
    records = []
    try:
        art = await extract_article(sh, str(link))
        records.append(art.model_dump())
        print(f"✅ extracted {link}")
    except Exception as e:
        print(f"⚠️  {link} failed → {e}")

    await sh.close()
    print(json.dumps(records, indent=2, default=str))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python two_step_stagehand.py <blog home/list URL>")
    asyncio.run(main(sys.argv[1]))
