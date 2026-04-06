"""Unit tests for GCSClient — all GCS calls are mocked."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


@pytest.fixture
def mock_settings():
    with patch("app.services.storage.gcs.get_settings") as mock:
        settings = MagicMock()
        settings.GCS_BUCKET = "test-bucket"
        settings.GCS_CREDENTIALS_PATH = "credentials/fake.json"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_storage_client():
    with patch("app.services.storage.gcs.storage") as mock_storage:
        mock_client = MagicMock()
        mock_storage.Client.from_service_account_json.return_value = mock_client
        yield mock_client, mock_storage


@pytest.fixture
def gcs_client(mock_settings, mock_storage_client):
    mock_client, mock_storage = mock_storage_client
    with patch("pathlib.Path.exists", return_value=True):
        from app.services.storage.gcs import GCSClient
        client = GCSClient()
        # Force the property to initialize
        _ = client.client
    return client, mock_client


class TestGCSClientUpload:
    def test_upload_pdf_calls_gcs(self, gcs_client):
        client, mock_gcs = gcs_client
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_gcs.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        pdf_bytes = b"%PDF-1.4 fake pdf content"
        result = client.upload_pdf(pdf_bytes, "resumes/user1/job1.pdf")

        mock_gcs.bucket.assert_called_once_with("test-bucket")
        mock_bucket.blob.assert_called_once_with("resumes/user1/job1.pdf")
        mock_blob.upload_from_string.assert_called_once_with(
            pdf_bytes, content_type="application/pdf"
        )
        assert result == "resumes/user1/job1.pdf"

    def test_upload_returns_gcs_path(self, gcs_client):
        client, mock_gcs = gcs_client
        mock_gcs.bucket.return_value.blob.return_value = MagicMock()

        path = client.upload_pdf(b"data", "some/path.pdf")
        assert path == "some/path.pdf"


class TestGCSClientDownload:
    def test_download_pdf_returns_bytes(self, gcs_client):
        client, mock_gcs = gcs_client
        mock_blob = MagicMock()
        mock_blob.download_as_bytes.return_value = b"%PDF-1.4 content"
        mock_gcs.bucket.return_value.blob.return_value = mock_blob

        result = client.download_pdf("resumes/user1/job1.pdf")

        assert result == b"%PDF-1.4 content"
        mock_gcs.bucket.assert_called_with("test-bucket")
        mock_blob.download_as_bytes.assert_called_once()

    def test_download_uses_correct_path(self, gcs_client):
        client, mock_gcs = gcs_client
        mock_bucket = MagicMock()
        mock_gcs.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value.download_as_bytes.return_value = b"data"

        client.download_pdf("my/custom/path.pdf")
        mock_bucket.blob.assert_called_with("my/custom/path.pdf")


class TestGCSClientDelete:
    def test_delete_pdf_calls_blob_delete(self, gcs_client):
        client, mock_gcs = gcs_client
        mock_blob = MagicMock()
        mock_gcs.bucket.return_value.blob.return_value = mock_blob

        client.delete_pdf("resumes/user1/job1.pdf")

        mock_blob.delete.assert_called_once()


class TestGCSClientInit:
    def test_uses_service_account_when_file_exists(self, mock_settings):
        with patch("app.services.storage.gcs.storage") as mock_storage, \
             patch("pathlib.Path.exists", return_value=True):
            from app.services.storage.gcs import GCSClient
            client = GCSClient()
            _ = client.client
            mock_storage.Client.from_service_account_json.assert_called_once()

    def test_falls_back_to_default_credentials(self, mock_settings):
        with patch("app.services.storage.gcs.storage") as mock_storage, \
             patch("pathlib.Path.exists", return_value=False):
            from app.services.storage.gcs import GCSClient
            client = GCSClient()
            _ = client.client
            mock_storage.Client.assert_called_once_with()
