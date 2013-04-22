import re
from xml.dom import minidom
import xml.etree.ElementTree as ET

data = """<geonames>
<totalResultsCount>97</totalResultsCount><code>
<lat>-33.9</lat>
<lng>18.63333</lng>
<adminCode1/>"""

p = re.compile(r'<lat>(.*)</lat><lng>(.*)</lng>')
print p.findall(data)
m = p.search(data)
if m:
    lat = m.groups()
    print lat



def get_weather_data():
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

data = get_weather_data()

xmldoc = minidom.parseString(data)
itemlist = xmldoc.getElementsByTagName('time')
print len(itemlist)
print itemlist[0].attributes['from'].value

import datetime
print "-------------------"
forecast = {}
root = ET.fromstring(data)
for time in root.iter("time"):
    date = datetime.datetime.strptime(time.get("from"), "%Y-%m-%dT%H:%M:%SZ")
    loc = time.find("location")
    temp = loc.find("temperature")
    if temp is not None:
        t = temp.get("value")
        temps = forecast.setdefault(date.date(), [])
        temps.append(t)

for key in sorted(forecast.iterkeys())[:5]:
    temps = sorted(forecast[key], key=lambda a: map(int, a.split(".")))
    print "%s: %s - %s" % (key, temps[0], temps[len(temps)-1])