"""Web extraction must tolerate the oversized headers real sites send."""

import pytest
from aiohttp import web

from landppt.services.research import content_extractor
from landppt.services.research.content_extractor import WEB_FETCH_USER_AGENT, WebContentExtractor

ARTICLE = "<html><head><title>Long header page</title></head><body><article>" + (
    "<p>" + "Realtime voice agents keep conversations responsive. " * 20 + "</p>"
) * 5 + "</article></body></html>"


@pytest.mark.asyncio
async def test_extractor_reads_pages_with_headers_longer_than_aiohttp_default():
    seen_agents = []

    async def page(request):
        seen_agents.append(request.headers.get("User-Agent"))
        # GitHub's Content-Security-Policy is ~9 KB; aiohttp rejects anything over 8190 bytes by default.
        return web.Response(text=ARTICLE, content_type="text/html", headers={"Content-Security-Policy": "a" * 9300})

    app = web.Application()
    app.router.add_get("/", page)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        results = await WebContentExtractor().extract_multiple([f"http://127.0.0.1:{port}/"], max_concurrent=1, delay_between_requests=0)
    finally:
        await runner.cleanup()

    assert len(results) == 1
    assert "Realtime voice agents" in results[0].content
    assert seen_agents == [WEB_FETCH_USER_AGENT]
    assert "+https://" in content_extractor.WEB_FETCH_USER_AGENT
