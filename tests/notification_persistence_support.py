"""Original all-category loopback with bounded read-once and ordinary responses."""

from aiohttp import web

from tests.notifications_support import NotificationsFixture
from tests.reads_support import ReadsFixture


class NotificationWorkflowFixture(ReadsFixture, NotificationsFixture):
    def app(self) -> web.Application:
        app = ReadsFixture.app(self)
        app.router.add_get("/terminarz/dodane_od_ostatniego_logowania", self.consume)
        return app
