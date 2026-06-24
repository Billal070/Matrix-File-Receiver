import asyncio
import logging

from database import init_db
from user_bot import create_user_app
from admin_bot import create_admin_app

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    init_db()
    logger.info("✅ Database initialized.")

    user_app  = create_user_app()
    admin_app = create_admin_app()

    await user_app.initialize()
    await admin_app.initialize()
    await user_app.start()
    await admin_app.start()
    await user_app.updater.start_polling(drop_pending_updates=True)
    await admin_app.updater.start_polling(drop_pending_updates=True)

    logger.info("🔷 Matrix File Receiver — LIVE")
    logger.info("🤖 User Bot  → running")
    logger.info("👨‍💼 Admin Bot → running")

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await user_app.updater.stop()
        await admin_app.updater.stop()
        await user_app.stop()
        await admin_app.stop()
        await user_app.shutdown()
        await admin_app.shutdown()
        logger.info("✅ Bots stopped.")


if __name__ == "__main__":
    asyncio.run(main())
