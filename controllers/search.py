import urllib, datetime, re
from django.utils import simplejson
from google.appengine.ext import db

from controllers.controller import Controller
from models.attraction import Attraction

class SearchPage(Controller):
    
    def getAttractions(self, lat = None, lon = None, type = 'html', tag = '', bounds = {}):
        
        attractions = []
        updated = None
        
        boxLat = round(lat, 1)
        boxLon = round(lon, 1)
        
        defaultAccuracy = 1
        
        try:
            boundsLat = bounds['north'] - bounds['south']
            boundsLon = bounds['east'] - bounds['west']
            if boundsLat < boundsLon:
                accuracy = boundsLat
            else:
                accuracy = boundsLon
        except KeyError:
            accuracy = defaultAccuracy
        
        if type == 'js' or accuracy < defaultAccuracy:
            lats = [boxLat]
            lons = [boxLon]
        else:
            lats = [boxLat - 0.1, boxLat, boxLat + 0.1]
            lons = [boxLon - 0.1, boxLon, boxLon + 0.1]
        
        for latitude in lats:
            for longitude in lons:
                
                query = Attraction.all()
                query.filter("next =", None)
                query.filter("geobox =", '%s,%s' % (latitude, longitude))
                if tag:
                    query.filter("tags =", tag)
                query.order("name")
                
                try:
                    for attraction in query:
                        if accuracy >= defaultAccuracy or (\
                            attraction.location.lat > lat - accuracy and \
                            attraction.location.lat < lat + accuracy and \
                            attraction.location.lon > lon - accuracy and \
                            attraction.location.lon < lon + accuracy
                        ):
                            attractions.append(attraction)
                except (IndexError, db.BadRequestError):
                    pass
        
        attractions.sort(lambda x, y: cmp(x.name, y.name))
        
        attractionCount = 64
        for attraction in attractions:
            attractionCount = attractionCount + 1
            if attractionCount < 91:
                attraction.label = chr(attractionCount)
            if attraction.picture:
                attraction.thumbnail = self.convertFlickrUrl(attraction.picture, "s")
            if updated == None or attraction.datetime > updated:
                updated = attraction.datetime
            
        return (attractions, updated, accuracy)
    
    def getLocationName(self, data):
        try:
            if data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['AddressLine'] == data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['AdministrativeAreaName']:
                raise KeyError
            return (
                data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['AddressLine'],
                data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['AdministrativeAreaName'],
                data['Placemark'][0]['AddressDetails']['Country']['CountryName']
            )
        except KeyError:
            try:
                if data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['SubAdministrativeAreaName'] == data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['AdministrativeAreaName']:
                    raise KeyError
                return (
                    data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['SubAdministrativeAreaName'],
                    data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['AdministrativeAreaName'],
                    data['Placemark'][0]['AddressDetails']['Country']['CountryName']
                )
            except KeyError:
                try:
                    return (
                        data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['AddressLine'],
                        data['Placemark'][0]['AddressDetails']['Country']['CountryName']
                    )
                except KeyError:
                    try:
                        return (
                            data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['SubAdministrativeAreaName'],
                            data['Placemark'][0]['AddressDetails']['Country']['CountryName']
                        )
                    except KeyError:
                        return ()
    
    def get(self, type):
        
        search = self.request.get("q")
        coords = self.request.get("c")
        tag = self.request.get("t")
        attractions = self.request.get("a")
        
        template_values = {}
        
        template_values['q'] = search
        
        # special search strings
        if search[0:10] == "tagged as ":
            if " in " not in search:
                tag = search[10:].strip(" ")
                if tag in self.tags:
                    tag = self.tags[tag]
            search = search[10:]
        elif search[0:12] == "tagged with ":
            if " in " not in search:
                tag = search[12:].strip(" ")
                if tag in self.tags:
                    tag = self.tags[tag]
            search = search[12:]
        
        if search[-11:] == " everywhere":
            tag = search[0:-11].strip(" ")
            if tag in self.tags:
                tag = self.tags[tag]
        elif search[-9:] == " anywhere":
            tag = search[0:-9].strip(" ")
            if tag in self.tags:
                tag = self.tags[tag]
        
        if coords:
            
            coords = coords.split(',')
            try:
                template_values['coords'] = "%.2f,%.2f" % (float(coords[0]), float(coords[1]))
            except ValueError:
                self.send404()
                return
            
            if type != 'js':
                
                url = "http://maps.google.com/maps/geo?q=%.2f,%.2f&sensor=false" % (float(coords[0]), float(coords[1]))
                
                jsonString = urllib.urlopen(url).read()
                if jsonString:
                    data = simplejson.loads(jsonString)
                    try:
                        lat = data['Placemark'][0]['Point']['coordinates'][1]
                        lon = data['Placemark'][0]['Point']['coordinates'][0]
                        (template_values['attractions'], template_values['updated'], accuracy) = self.getAttractions(lat, lon, type)
                        template_values['search'] = ', '.join(self.getLocationName(data))
                    except KeyError:
                        pass
                else:
                    lat = float(coords[0])
                    lon = float(coords[1])
                    (template_values['attractions'], template_values['updated'], accuracy) = self.getAttractions(lat, lon, type)
            else:
                lat = float(coords[0])
                lon = float(coords[1])
                (template_values['attractions'], template_values['updated'], accuracy) = self.getAttractions(lat, lon, type)
            
        elif tag:
            page = int(self.request.get("page", 1));
                        
            attractionQuery = Attraction.all()
            attractionQuery.filter("tags =", tag)
            attractionQuery.filter("next =", None)
            try:
                template_values['attractions'] = attractionQuery.fetch(26, (page - 1) * 26)
            except:
                template_values['attractions'] = []
            
            if page > 1:
                template_values['previous'] = self.request.path + '?t=' + tag + '&page=' + str(page - 1)
            if len(template_values['attractions']) == 26:
                template_values['next'] = self.request.path + '?t=' + tag + '&page=' + str(page + 1)
            
            template_values['updated'] = None
            attractionCount = 64
            for attraction in template_values['attractions']:
                attractionCount = attractionCount + 1
                if attractionCount < 91:
                    attraction.label = chr(attractionCount)
                if attraction.picture:
                    attraction.thumbnail = self.convertFlickrUrl(attraction.picture, "s")
                if template_values['updated'] == None or attraction.datetime > template_values['updated']:
                    template_values['updated'] = attraction.datetime
            
            template_values['tag'] = tag
        
        elif search:
            
            if " in " in search:
                pos = search.find(' in ')
                tag = search[0:pos].replace(' ', '')
                search = search[pos + 4:]
                
                if tag in self.tags:
                    tag = self.tags[tag]
                    
                template_values['tag'] = tag
            
            search = search.strip(" ")
            
            url = "http://maps.google.com/maps/geo?q=%s&sensor=false" % urllib.quote(search)
            
            template_values['search'] = search
            
            jsonString = urllib.urlopen(url).read()
            if jsonString:
                data = simplejson.loads(jsonString)
                try:
                    bounds = data['Placemark'][0]['ExtendedData']['LatLonBox']
                    lat = data['Placemark'][0]['Point']['coordinates'][1]
                    lon = data['Placemark'][0]['Point']['coordinates'][0]
                    template_values['coords'] = "%.1f,%.1f" % (lat, lon)
                    (template_values['attractions'], template_values['updated'], accuracy) = self.getAttractions(lat, lon, type, tag, bounds)
                    template_values['search'] = ', '.join(self.getLocationName(data))
                except KeyError:
                    pass
                
        elif attractions:
            
            template_values['attractions'] = []
            
            for attractionId in attractions.split(","):
                
                query = Attraction.all()
                query.filter("id =", attractionId)
                
                attraction = query.get()
                if attraction:
                    template_values['attractions'].append(attraction)
        
        template_values['otherPlaces'] = []
        if lat and lon:
            if accuracy:
                size = accuracy
            else:
                size = 0.05
            coords = [
                "%.2f,%.2f" % (lat + size, lon - size),
                "%.2f,%.2f" % (lat + size, lon),
                "%.2f,%.2f" % (lat + size, lon + size),
                "%.2f,%.2f" % (lat - size, lon - size),
                "%.2f,%.2f" % (lat - size, lon),
                "%.2f,%.2f" % (lat - size, lon + size),
                "%.2f,%.2f" % (lat, lon - size),
                "%.2f,%.2f" % (lat, lon + size)
            ]
            for coord in coords:
                url = "http://maps.google.com/maps/geo?q=%s&sensor=false" % coord
                jsonString = urllib.urlopen(url).read()
                if jsonString:
                    data = simplejson.loads(jsonString)
                    name = ', '.join(self.getLocationName(data))
                    if name is not None and name != template_values['search'] and name not in template_values['otherPlaces']:
                        template_values['otherPlaces'].append(name)
            
        template_values['manyResults'] = len(template_values['attractions']) > 5
        
        template_values['url'] = self.request.url
        template_values['atomtag'] = self.request.path
        
        template_values['atom'] = self.request.url.replace('.html', '.atom')
        template_values['html'] = self.request.url
        template_values['json'] = self.request.url.replace('.html', '.json')
        template_values['gpx'] = self.request.url.replace('.html', '.gpx')

        self.output('search', type, template_values)

