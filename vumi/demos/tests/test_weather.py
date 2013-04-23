# -*- encoding: utf-8 -*-

"""Tests for vumi.demos.hangman."""

import unittest
from twisted.trial import unittest
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.web.static import Data
from vumi.demos.weather import WeatherApp, USERNAME_SLUG, WEATHER_SLUG, LOCATION_SLUG


class TestWeatherApp(unittest.TestCase):

    @inlineCallbacks
    def setUp(self):
        root = Resource()
        # data is elephant with a UTF-8 encoded BOM
        # it is a sad elephant (as seen in the wild)
        root.putChild("location", Data(self._location_xml(), 'text/html'))
        root.putChild("weather", Data(self._weather_xml(), 'text/html'))
        site_factory = Site(root)
        self.webserver = yield reactor.listenTCP(0, site_factory)
        addr = self.webserver.getHost()
        self.weather_url = "http://127.0.0.1:%s/weather" % addr.port
        self.location_url = "http://127.0.0.1:%s/location" % addr.port

    @inlineCallbacks
    def tearDown(self):
        yield self.webserver.loseConnection()

    @inlineCallbacks
    def test_basic(self):
        app = WeatherApp(config={USERNAME_SLUG: "dimagi",
                                 WEATHER_SLUG: self.weather_url + "?%s",
                                 LOCATION_SLUG: self.location_url + "?%s"})
        yield app.event('cape town')
        self.assertEqual(app.state(), {'lat': '-33.9', 'lng': '18.63333', 'name': 'Cape Town'})
        self.assertEqual(app.forecast['2013-04-21']["min"], '9.9')
        self.assertEqual(app.forecast['2013-04-21']["max"], '11.1')
        self.assertEqual(app.forecast['2013-04-22']["min"], '10.9')
        self.assertEqual(app.forecast['2013-04-22']["max"], '22')

    def test_parse_weather_data(self):
        data = self._weather_xml()

        app = WeatherApp()
        app.parse_weather_data(data)
        self.assertEqual(app.forecast['2013-04-21']["min"], '9.9')
        self.assertEqual(app.forecast['2013-04-21']["max"], '11.1')
        self.assertEqual(app.forecast['2013-04-22']["min"], '10.9')
        self.assertEqual(app.forecast['2013-04-22']["max"], '22')

    def _location_xml(self):
        return """<geonames>
            <totalResultsCount>97</totalResultsCount>
            <code>
            <postalcode>7530</postalcode>
            <name>Cape Town</name>
            <countryCode>ZA</countryCode>
            <lat>-33.9</lat>
            <lng>18.63333</lng>
            <adminCode1/>
            <adminName1/>
            <adminCode2/>
            <adminName2/>
            <adminCode3/>
            <adminName3/>
            </code>
            </geonames>"""

    def _weather_xml(self):
        return """<weatherdata xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://api.met.no/weatherapi/locationforecast/1.8/schema" created="2013-04-20T18:51:01Z">
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
        """