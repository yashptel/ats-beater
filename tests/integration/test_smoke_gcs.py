"""Integration smoke tests for GCS storage — requires real GCS credentials and bucket.

Run with: INTEGRATION=1 uv run pytest tests/integration/test_smoke_gcs.py -v
"""
import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION") != "1",
    reason="Integration tests require INTEGRATION=1",
)


@pytest.fixture
def gcs_client():
    from app.services.storage.gcs import GCSClient
    return GCSClient()


@pytest.fixture
def test_pdf_bytes():
    """Minimal valid-ish PDF bytes for testing."""
    return b"%PDF-1.4 test content " + uuid.uuid4().bytes


@pytest.fixture
def test_gcs_path():
    return f"test-uploads/{uuid.uuid4().hex}.pdf"


class TestGCSSmoke:
    def test_upload_and_download_roundtrip(self, gcs_client, test_pdf_bytes, test_gcs_path):
        """Upload PDF bytes, download them back, verify they match."""
        # Upload
        returned_path = gcs_client.upload_pdf(test_pdf_bytes, test_gcs_path)
        assert returned_path == test_gcs_path

        # Download
        downloaded = gcs_client.download_pdf(test_gcs_path)
        assert downloaded == test_pdf_bytes

        # Cleanup
        gcs_client.delete_pdf(test_gcs_path)

    def test_delete_removes_object(self, gcs_client, test_pdf_bytes, test_gcs_path):
        """Upload then delete, verify download fails."""
        gcs_client.upload_pdf(test_pdf_bytes, test_gcs_path)
        gcs_client.delete_pdf(test_gcs_path)

        with pytest.raises(Exception):
            gcs_client.download_pdf(test_gcs_path)

    def test_download_nonexistent_raises(self, gcs_client):
        """Downloading a non-existent path should raise."""
        with pytest.raises(Exception):
            gcs_client.download_pdf(f"nonexistent/{uuid.uuid4().hex}.pdf")
