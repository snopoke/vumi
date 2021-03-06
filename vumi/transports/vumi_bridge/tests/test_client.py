from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks, DeferredQueue
from twisted.web.server import NOT_DONE_YET
from twisted.web.client import ResponseDone

from vumi.tests.utils import MockHttpServer
from vumi.transports.vumi_bridge.client import StreamingClient
from vumi.message import Message


class ClientTestCase(TestCase):

    @inlineCallbacks
    def setUp(self):
        self.mock_server = MockHttpServer(self.handle_request)
        yield self.mock_server.start()
        self.url = self.mock_server.url
        self.client = StreamingClient()
        self.messages_received = DeferredQueue()
        self.errors_received = DeferredQueue()
        self.disconnects_received = DeferredQueue()

        def reason_trapper(reason):
            if reason.trap(ResponseDone):
                self.disconnects_received.put(reason.getErrorMessage())

        self.receiver = self.client.stream(
            Message,
            self.messages_received.put, self.errors_received.put,
            self.url, on_disconnect=reason_trapper)

    def tearDown(self):
        return self.mock_server.stop()

    def handle_request(self, request):
        self.mock_server.queue.put(request)
        return NOT_DONE_YET

    @inlineCallbacks
    def test_callback_on_disconnect(self):
        req = yield self.mock_server.queue.get()
        req.write(
            '%s\n' % (Message(foo='bar').to_json().encode('utf-8'),))
        req.finish()
        message = yield self.messages_received.get()
        self.assertEqual(message['foo'], 'bar')
        reason = yield self.disconnects_received.get()
        # this is the error message we get when a ResponseDone is raised
        # which happens when the remote server closes the connection.
        self.assertEqual(reason, 'Response body fully received')
