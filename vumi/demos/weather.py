# -*- test-case-name: vumi.demos.tests.test_hangman -*-

import re
import urllib
import xml.etree.ElementTree as ET
from datetime import datetime
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

from vumi.application import ApplicationWorker
from vumi.utils import http_request
from vumi.components import SessionManager
from vumi.config import ConfigText, ConfigDict

LOCATION_SLUG = "location_url"
WEATHER_SLUG = "weather_url"
USERNAME_SLUG = "geonames_username"

LOCATION_URL_DEFAULT = "http://api.geonames.org/postalCodeSearch?%s"
WEATHER_URL_DEFAULT = "http://api.yr.no/weatherapi/locationforecast/1.8/?%s"

P_LAT = re.compile('<lat>(.*)</lat>')
P_LNG = re.compile('<lng>(.*)</lng>')
P_NAME = re.compile('<name>(.*)</name>')


class WeatherConfig(ApplicationWorker.CONFIG_CLASS):
    "Hangman worker config."
    worker_name = ConfigText(
        "Name of this weather worker.", required=True, static=True)
    redis_manager = ConfigDict(
        "Redis client configuration.", default={}, static=True)

    geonames_username = ConfigText(
        "Geonames username", required=True)

    location_url = ConfigText(
        "Location API URL", default=LOCATION_URL_DEFAULT)
    weather_url = ConfigText(
        "Weather API URL", default=WEATHER_URL_DEFAULT)


class WeatherApp(object):

    UI_TEMPLATE = (
        u"Min/Max temps for %(location)s\n"
        u"%(weather)s\n"
        u"%(prompt)s:\n")

    # exit codes
    NOT_DONE, DONE = range(2)

    def __init__(self, name=None, lat=None, lng=None, config={}):
        self.lat = lat
        self.lng = lng
        self.name = name
        self.exit_code = self.NOT_DONE
        self.msg = None
        self.config = config
        self.forecast = {}
        self.msg = None

    def state(self):
        """Return the app state as a dict."""
        return {
            'lat': self.lat or '',
            'lng': self.lng or '',
            'name': self.name or ''
        }

    @classmethod
    def from_state(cls, state):
        return cls(name=state.pop('name'), lat=state.pop('lat'), lng=state.pop('lng'), config=state)

    @property
    def has_location(self):
        return self.lat and self.lng

    def render(self):
        """Return a text-based UI."""
        if  self.exit_code == self.NOT_DONE and self.has_location:
            return self.UI_TEMPLATE % {
                "location": self.name,
                "weather": self.render_forecast(),
                "prompt": "Enter a new location or 0 to quit"
            }
        else:
            return self.msg or "Enter your location"

    def render_forecast(self):
        output = ""
        for date in sorted(self.forecast.iterkeys()):
            output += date + ": %(min)s - %(max)s\n" % self.forecast[date]
        return output

    @inlineCallbacks
    def event(self, message):
        """Handle an user input string.

           Parameters
           ----------
           message : unicode
               Message received from user.
           """
        message = message.lower()
        if not message:
            self.msg = u"Some input required please."
        elif message == '0':
            self.exit_code = self.DONE
            self.msg = u"Bye."
        else:
            yield self.update_location(message)
            yield self.update_forecast()

    @inlineCallbacks
    def update_location(self, location_text):
        """
        Do a Geoname lookup with the text entered by the user.
        :param location_text:
        """
        query = {"username": self.config[USERNAME_SLUG], "maxRows": 1, "placename": location_text}
        url = self.config[LOCATION_SLUG] % (urllib.urlencode(query),)
        data = yield http_request(url.encode("UTF-8"), None, method="GET")

        self.lat = self.extract(P_LAT, data)
        self.lng = self.extract(P_LNG, data)
        self.name = self.extract(P_NAME, data)

        log.msg("location for %s: %s, %s" % (self.name, self.lat, self.lng))

    @inlineCallbacks
    def update_forecast(self):
        if self.has_location:
            yield self.get_weather()

    @inlineCallbacks
    def get_weather(self):
        """
        Using the location from Geonames get the weather forecast
        """
        query = {"lat": self.lat, "lon": self.lng}
        url = self.config[WEATHER_SLUG] % (urllib.urlencode(query),)
        data = yield http_request(url, None, method="GET")
        self.parse_weather_data(data)

    def parse_weather_data(self, data):
        weather_data = {}
        root = ET.fromstring(data)
        for time in root.iter("time"):
            date = datetime.strptime(time.get("from"), "%Y-%m-%dT%H:%M:%SZ")
            loc = time.find("location")
            temp = loc.find("temperature")
            if temp is not None:
                t = temp.get("value")
                temps = weather_data.setdefault(date.date(), [])
                temps.append(t)

        # get 5 day max and min temps
        for key in sorted(weather_data.iterkeys())[:5]:
            temps = sorted(weather_data[key], key=lambda a: map(int, a.split(".")))
            self.forecast[str(key)] = {
                "min": temps[0],
                "max": temps[len(temps) - 1]
            }

    def extract(self, pattern, data):
        m = pattern.search(data)
        if m:
            return m.group(1)
        else:
            return None


class WeatherWorker(ApplicationWorker):

    CONFIG_CLASS = WeatherConfig

    @inlineCallbacks
    def setup_application(self):
        """Start the worker"""
        config = self.get_static_config()

        # Connect to Redis
        r_prefix = "weather:%s:%s" % (
            config.transport_name, config.worker_name)
        self.session_manager = yield SessionManager.from_redis_config(
            config.redis_manager, r_prefix)

    @inlineCallbacks
    def teardown_application(self):
        yield self.session_manager.stop()

    def user_key(self, user_id):
        """Key for looking up a users data in data store."""
        return user_id.lstrip('+')

    def get_config_dict(self, config):
        return {
            USERNAME_SLUG: config.geonames_username,
            WEATHER_SLUG: config.weather_url,
            LOCATION_SLUG: config.location_url
        }

    @inlineCallbacks
    def load_weather_app(self, msisdn, config):
        """Fetch a game for the given user ID.
           """
        user_key = self.user_key(msisdn)
        state = yield self.session_manager.load_session(user_key)
        log.msg(state)
        if state:
            state.update(config)
            app = WeatherApp.from_state(state)
        else:
            app = WeatherApp(config=config)
        returnValue(app)

    def save_state(self, msisdn, app):
        """Save the game state for the given game."""
        user_key = self.user_key(msisdn)
        state = app.state()
        return self.session_manager.save_session(user_key, state)

    @inlineCallbacks
    def consume_user_message(self, msg):
        log.msg("User message: %s" % msg['content'])

        user_id = msg.user()
        config = yield self.get_config(msg)
        config_dict = self.get_config_dict(config)
        app = yield self.load_weather_app(user_id, config_dict)

        if msg['content'] is None:
            # probably new session
            yield app.update_forecast()
            self.reply_to(msg, app.render(), True)
            return

        message = msg['content'].strip()
        yield app.event(message)

        continue_session = True
        if app.exit_code == app.DONE:
            continue_session = False
        else:
            yield self.save_state(user_id, app)

        self.reply_to(msg, app.render(), continue_session)

    def close_session(self, msg):
        """We ignore session closing and wait for the user to return."""
        pass