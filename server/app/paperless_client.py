import httpx

from .config import settings


class PaperlessClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.paperless_base_url,
            headers={"Authorization": f"Token {settings.paperless_api_token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_documents(
        self,
        query: str | None = None,
        tags__id__in: str | None = None,
        correspondent__id: int | None = None,
        created__date__gte: str | None = None,
        created__date__lte: str | None = None,
        ordering: str | None = None,
        page_size: int = 25,
    ) -> dict:
        params: dict[str, str | int] = {"page_size": page_size}
        if query:
            params["query"] = query
        if tags__id__in:
            params["tags__id__in"] = tags__id__in
        if correspondent__id is not None:
            params["correspondent__id"] = correspondent__id
        if created__date__gte:
            params["created__date__gte"] = created__date__gte
        if created__date__lte:
            params["created__date__lte"] = created__date__lte
        if ordering:
            params["ordering"] = ordering
        resp = await self._client.get("/api/documents/", params=params)
        resp.raise_for_status()
        return resp.json()

    async def list_all_documents(
        self,
        query: str | None = None,
        tags__id__in: str | None = None,
        correspondent__id: int | None = None,
        created__date__gte: str | None = None,
        created__date__lte: str | None = None,
        ordering: str | None = None,
        max_results: int = 500,
        max_pages: int = 20,
    ) -> dict:
        page = await self.list_documents(
            query=query,
            tags__id__in=tags__id__in,
            correspondent__id=correspondent__id,
            created__date__gte=created__date__gte,
            created__date__lte=created__date__lte,
            ordering=ordering,
            page_size=min(max_results, 100),
        )
        results = list(page.get("results", []))
        next_url = page.get("next")
        pages_fetched = 1
        truncated = False

        while next_url and pages_fetched < max_pages and len(results) < max_results:
            resp = await self._client.get(next_url)
            resp.raise_for_status()
            page = resp.json()
            results.extend(page.get("results", []))
            next_url = page.get("next")
            pages_fetched += 1

        if len(results) > max_results:
            results = results[:max_results]
            truncated = True
        elif next_url:
            truncated = True

        return {"count": page.get("count", len(results)), "results": results, "truncated": truncated}

    async def get_document(self, document_id: int) -> dict:
        resp = await self._client.get(f"/api/documents/{document_id}/")
        resp.raise_for_status()
        return resp.json()

    async def list_correspondents(self) -> dict:
        resp = await self._client.get("/api/correspondents/", params={"page_size": 100})
        resp.raise_for_status()
        return resp.json()

    async def list_document_types(self) -> dict:
        resp = await self._client.get("/api/document_types/", params={"page_size": 100})
        resp.raise_for_status()
        return resp.json()

    async def list_tags(self) -> dict:
        resp = await self._client.get("/api/tags/", params={"page_size": 100})
        resp.raise_for_status()
        return resp.json()

    async def get_document_preview(self, document_id: int) -> tuple[bytes, str]:
        resp = await self._client.get(f"/api/documents/{document_id}/preview/")
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "application/pdf")
        return resp.content, content_type

    async def create_tag(self, name: str, color: str | None = None) -> dict:
        payload: dict = {"name": name, "matching_algorithm": 0}
        if color:
            payload["color"] = color
        resp = await self._client.post("/api/tags/", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def create_correspondent(self, name: str) -> dict:
        resp = await self._client.post(
            "/api/correspondents/", json={"name": name, "matching_algorithm": 0}
        )
        resp.raise_for_status()
        return resp.json()

    async def create_document_type(self, name: str) -> dict:
        resp = await self._client.post(
            "/api/document_types/", json={"name": name, "matching_algorithm": 0}
        )
        resp.raise_for_status()
        return resp.json()

    async def update_document(self, document_id: int, **fields) -> dict:
        payload = {k: v for k, v in fields.items() if v is not None}
        resp = await self._client.patch(f"/api/documents/{document_id}/", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def delete_tag(self, tag_id: int) -> None:
        resp = await self._client.delete(f"/api/tags/{tag_id}/")
        resp.raise_for_status()

    async def delete_correspondent(self, correspondent_id: int) -> None:
        resp = await self._client.delete(f"/api/correspondents/{correspondent_id}/")
        resp.raise_for_status()

    async def delete_document_type(self, document_type_id: int) -> None:
        resp = await self._client.delete(f"/api/document_types/{document_type_id}/")
        resp.raise_for_status()

    async def bulk_edit(self, document_ids: list[int], method: str, parameters: dict | None = None) -> dict:
        resp = await self._client.post(
            "/api/documents/bulk_edit/",
            json={"documents": document_ids, "method": method, "parameters": parameters or {}},
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}


paperless_client = PaperlessClient()
