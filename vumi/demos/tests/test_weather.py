# -*- encoding: utf-8 -*-

"""Tests for vumi.demos.hangman."""

import unittest
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
from vumi.demos.weather import WeatherApp, USERNAME_SLUG, WEATHER_SLUG, LOCATION_SLUG, WeatherWorker

from vumi.application.tests.utils import ApplicationTestCase
from vumi.message import TransportUserMessage


class WebserverMixin(object):
    @inlineCallbacks
    def setupWebserver(self):
        root = Resource()
        root.putChild("location", LocationResource())
        root.putChild("weather", WeatherResource())
        site_factory = Site(root)
        self.webserver = yield reactor.listenTCP(0, site_factory)
        addr = self.webserver.getHost()
        self.weather_url = "http://127.0.0.1:%s/weather" % addr.port
        self.location_url = "http://127.0.0.1:%s/location" % addr.port


class TestWeatherApp(unittest.TestCase, WebserverMixin):
    @inlineCallbacks
    def setUp(self):
        yield self.setupWebserver()
        self.config = {USERNAME_SLUG: "dimagi", WEATHER_SLUG: self.weather_url + "?%s",
                       LOCATION_SLUG: self.location_url + "?%s"}
        self.app = WeatherApp(config=self.config)

    @inlineCallbacks
    def tearDown(self):
        yield self.webserver.loseConnection()

    @inlineCallbacks
    def test_basic(self):
        yield self.app.event('cape town')
        self.assertEqual(self.app.state(), {'lat': '-33.9', 'lng': '18.63333', 'name': 'Cape Town'})
        forecast = self.app.forecast
        self._assert_forecast(forecast)

    def test_initial_state(self):
        state = {"lat": -33, "lng": 18, "name": "Cape Town"}
        app = WeatherApp.from_state(state)
        self.assertEqual(app.state(), state)

    def test_exit(self):
        self.app.event("0")
        output = self.app.render()
        self.assertEqual(output, u"Bye.")

    @inlineCallbacks
    def test_update_forecast(self):
        state = {"lat": '-33.9', "lng": '18.63333', "name": "Cape Town"}
        state.update(self.config)
        app = WeatherApp.from_state(state)
        yield app.update_forecast()
        self._assert_forecast(app.forecast)

    @inlineCallbacks
    def test_update_location(self):
        yield self.app.update_location("boston")
        self.assertEqual(self.app.state(), {'lat': '42', 'lng': '-71', 'name': 'Boston'})

    def test_parse_weather_data(self):
        self.app.parse_weather_data(weather_xml[('-33.9', '18.63333')])
        self._assert_forecast(self.app.forecast)

    def test_render_forecast(self):
        self.app.forecast = {"2013-04-21": {"max": 10, "min": 5},
                             "2013-04-22": {"max": 15, "min": 8}}
        render = self.app.render_forecast()
        self.assertEqual(render, "Sun 21 Apr: 5 - 10\nMon 22 Apr: 8 - 15\n")

    def _assert_forecast(self, forecast):
        self.assertEqual(forecast['2013-04-21']["min"], '9.9')
        self.assertEqual(forecast['2013-04-21']["max"], '11.1')
        self.assertEqual(forecast['2013-04-22']["min"], '10.9')
        self.assertEqual(forecast['2013-04-22']["max"], '22')


class TestWeatherWorker(ApplicationTestCase, WebserverMixin):
    application_class = WeatherWorker

    @inlineCallbacks
    def setUp(self):
        super(TestWeatherWorker, self).setUp()
        yield self.setupWebserver()

        self.worker = yield self.get_application({USERNAME_SLUG: "dimagi",
                                                  WEATHER_SLUG: self.weather_url + "?%s",
                                                  LOCATION_SLUG: self.location_url + "?%s"})
        yield self.worker.session_manager.redis._purge_all()  # just in case

    @inlineCallbacks
    def send(self, content, session_event=None):
        msg = self.mkmsg_in(content=content, session_event=session_event)
        yield self.dispatch(msg)

    @inlineCallbacks
    def recv(self, n=0):
        msgs = yield self.wait_for_dispatched_messages(n)

        def reply_code(msg):
            if msg['session_event'] == TransportUserMessage.SESSION_CLOSE:
                return 'end'
            return 'reply'

        returnValue([(reply_code(msg), msg['content']) for msg in msgs])

    @inlineCallbacks
    def tearDown(self):
        yield super(TestWeatherWorker, self).tearDown()
        yield self.webserver.loseConnection()

    @inlineCallbacks
    def test_new_session(self):
        yield self.send(None, TransportUserMessage.SESSION_NEW)
        replies = yield self.recv(1)
        self.assertEqual(len(replies), 1)

        reply = replies[0]
        self.assertEqual(reply[0], 'reply')
        self.assertEqual(reply[1], 'Enter your location')

    @inlineCallbacks
    def test_full_session(self):
        yield self.send(None, TransportUserMessage.SESSION_NEW)
        yield self.send("cape town", TransportUserMessage.SESSION_RESUME)

        replies = yield self.recv(2)
        self.assertEqual(len(replies), 2)

        first_reply = replies[0]
        self.assertEqual(first_reply[0], 'reply')
        self.assertEqual(first_reply[1], 'Enter your location')

        last_reply = replies[-1]
        self.assertEqual(last_reply[0], 'reply')
        self.assertEqual(last_reply[1],
                         'Min/Max temps for Cape Town\n'
                         'Sun 21 Apr: 9.9 - 11.1\n'
                         'Mon 22 Apr: 10.9 - 22\n\n'
                         'Enter a new location\n'
                         'or 0 to quit:\n')

        yield self.send('boston')
        replies = yield self.recv(3)
        last_reply = replies[-1]
        self.assertEqual(last_reply[0], 'reply')
        self.assertEqual(last_reply[1],
                         'Min/Max temps for Boston\n'
                         'Sun 21 Apr: 5 - 10\n'
                         'Mon 22 Apr: 8 - 13\n\n'
                         'Enter a new location\n'
                         'or 0 to quit:\n')

        yield self.send('0')
        replies = yield self.recv(4)
        last_reply = replies[-1]
        self.assertEqual(last_reply[0], 'end')
        self.assertEqual(last_reply[1], "Bye.")

    @inlineCallbacks
    def test_close_session(self):
        yield self.send(None, TransportUserMessage.SESSION_CLOSE)
        replies = yield self.recv()
        self.assertEqual(replies, [])


class LocationResource(Resource):
    def render_GET(self, request):
        place = request.args['placename'][0]
        return location_xml[place]


class WeatherResource(Resource):
    def render_GET(self, request):
        lat = request.args['lat'][0]
        lng = request.args['lon'][0]
        return weather_xml[(lat, lng)]


location_xml = {"cape town": """<geonames>
        <totalResultsCount>97</totalResultsCount>
        <code>
        <postalcode>7530</postalcode>
        <name>Cape Town</name>
        <countryCode>ZA</countryCode>
        <lat>-33.9</lat>
        <lng>18.63333</lng>
        </code>
        </geonames>""",
                "boston": """<geonames>
        <totalResultsCount>2808</totalResultsCount>
        <code>
        <postalcode>02101</postalcode>
        <name>Boston</name>
        <countryCode>US</countryCode>
        <lat>42</lat>
        <lng>-71</lng>
        </code>
        </geonames>"""
}

weather_xml = {('-33.9', '18.63333'): """<weatherdata xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://api.met.no/weatherapi/locationforecast/1.8/schema" created="2013-04-20T18:51:01Z">
       <product class="pointData">
          <time datatype="forecast" from="2013-04-21T00:00:00Z" to="2013-04-21T00:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="11.1"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-20T21:00:00Z" to="2013-04-21T00:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <precipitation unit="mm" value="0.0"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-21T03:00:00Z" to="2013-04-21T03:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="9.9"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-22T06:00:00Z" to="2013-04-21T06:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="10.9"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-22T12:00:00Z" to="2013-04-21T06:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="22"/>
             </location>
          </time>
       </product>
    </weatherdata>
    """,
               ('42', '-71'): """<weatherdata xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://api.met.no/weatherapi/locationforecast/1.8/schema" created="2013-04-20T18:51:01Z">
       <product class="pointData">
          <time datatype="forecast" from="2013-04-21T00:00:00Z" to="2013-04-21T00:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="5"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-20T21:00:00Z" to="2013-04-21T00:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <precipitation unit="mm" value="0.0"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-21T03:00:00Z" to="2013-04-21T03:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="10"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-22T06:00:00Z" to="2013-04-21T06:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="13"/>
             </location>
          </time>
          <time datatype="forecast" from="2013-04-22T12:00:00Z" to="2013-04-21T06:00:00Z">
             <location altitude="101" latitude="-33.9000" longitude="18.6333">
                <temperature id="TTT" unit="celcius" value="8"/>
             </location>
          </time>
       </product>
    </weatherdata>
    """
}