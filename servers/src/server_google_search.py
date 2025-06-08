from mcp.server.fastmcp import FastMCP
from googleapiclient.discovery import build
import os
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env file


API_KEY = os.getenv("GOOGLE_CSE_API_KEY")  # or paste literal string
CX_ID = os.getenv("GOOGLE_CSE_ID")  # your search-engine ID

mcp = FastMCP(
    "google_search_server",
    instructions="google the given query, and return the first 5 results. treat the user as searching from japan, and perfer Japanese-language results.",
)


@mcp.tool()
def google_search(query: str) -> list[dict]:
    """
    google the given query, and return the first 5 results. treat the user as searching from japan, and perfer Japanese-language results.

    Args:
        query (str): The search query.
    """
    service = build("customsearch", "v1", developerKey=API_KEY)
    resp = service.cse().list(q=query, cx=CX_ID, num=5, gl="jp", lr="lang_ja").execute()
    items = resp.get("items", [])
    cleaned = []

    for rank, it in enumerate(items, 1):
        meta = (it.get("pagemap", {}).get("metatags") or [{}])[0]
        published = meta.get("article:published_time") or meta.get("og:updated_time")

        cleaned.append(
            {
                "rank": rank,
                "title": it["title"],
                "snippet": it["snippet"],
                "url": it["link"],
                "domain": it.get("displayLink"),
                "published_at": published,  # may be None
            }
        )
    return str(cleaned)


if __name__ == "__main__":
    mcp.run(transport="stdio")
