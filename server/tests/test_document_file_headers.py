from unittest.mock import AsyncMock, patch

import pytest

from app.routers import documents


@pytest.mark.asyncio
async def test_document_file_allows_same_origin_framing():
    with (
        patch.object(documents.ObjectAuthorizer, "require_document", new=AsyncMock(return_value={"id": 1})),
        patch.object(
            documents.paperless_client,
            "get_document_preview",
            new=AsyncMock(return_value=(b"%PDF-1.4 fake", "application/pdf")),
        ),
        patch.object(documents.security_audit, "safe_record", new=AsyncMock()),
    ):
        response = await documents.get_document_file(document_id=1, principal=object())

    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp
    # A bare `sandbox` token here (no allow-* tokens) previously blocked the
    # browser's own native PDF viewer from running its own script, breaking
    # rendering and its download button even for same-origin embedding.
    assert "sandbox" not in csp
