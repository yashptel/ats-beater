import importlib
from unittest.mock import patch


def test_database_engine_enables_pool_pre_ping():
    import app.database.session as session_module

    fake_engine = object()
    fake_session_factory = object()

    try:
        with (
            patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine) as create_engine_mock,
            patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=fake_session_factory) as sessionmaker_mock,
        ):
            reloaded_module = importlib.reload(session_module)

        create_engine_mock.assert_called_once_with(
            reloaded_module.settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        sessionmaker_mock.assert_called_once_with(
            fake_engine,
            class_=reloaded_module.AsyncSession,
            expire_on_commit=False,
        )
        assert reloaded_module.engine is fake_engine
        assert reloaded_module.async_session_factory is fake_session_factory
    finally:
        importlib.reload(session_module)
