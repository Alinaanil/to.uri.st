from google.appengine.ext import db
import re

from controllers.controller import Controller
from models.attraction import Attraction

class EditPage(Controller):
    
    def get(self, attractionId = None):
        
        template_values = {}
        
        if attractionId:
            query = Attraction.all()
            query.filter("id =", attractionId)
            attraction = query.get()
            
            attraction.picture = self.convertFlickrUrl(attraction.picture, 'm')
            
            template_values['attraction'] = attraction
        
        self.output('edit', 'html', template_values)
    
    
    def post(self, attractionId):
        
        attraction = {}
        attraction['id'] = attractionId
        attraction['name'] = self.request.get('name')
        attraction['description'] = self.request.get('description')
        attraction['location'] = {}
        attraction['location']['lat'] = self.request.get('lat')
        attraction['location']['lon'] = self.request.get('lon')
        attraction['href'] = self.request.get('href')
        attraction['picture'] = self.request.get('picture')
        attraction['tags'] = self.request.get('tags').split(' ')
        
        if self.request.get('location.x') and self.request.get('location.y'):
            attraction['location']['lat'] = float(attraction['location']['lat']) - ((float(self.request.get('location.y')) - 75) / 18000) + 0.001
            attraction['location']['lon'] = float(attraction['location']['lon']) + ((float(self.request.get('location.x')) - 150) / 12000)
        
        errors = {}
        
        if len(attraction['name']) == 0:
            errors['name'] = True
            errors['name_empty'] = True
        if len(attraction['name']) > 100:
            errors['name'] = True
            errors['name_long'] = True
        
        if len(attraction['description']) > 5000:
            errors['description'] = True
        
        if not attraction['location']['lat'] or float(attraction['location']['lat']) < -90 or float(attraction['location']['lat']) > 90:
            errors['location'] = True
        
        if not attraction['location']['lon'] or float(attraction['location']['lon']) < -180 or float(attraction['location']['lon']) > 180:
            errors['location'] = True
        
        if not len(attraction['href']) == 0 and not re.match(r"^https?://.+$", attraction['href']):
            errors['href'] = True
        
        if not len(attraction['picture']) == 0 and not re.match(r"^https?://.+$", attraction['picture']):
            errors['picture'] = True
        
        for tag in attraction['tags']:
            if not re.match(r"^[a-z0-9]+$", tag):
                errors['tags'] = True
        
        if errors or (self.request.get('location.x') and self.request.get('location.y')):
            
            attraction['picture'] = self.convertFlickrUrl(attraction['picture'], 'm')
            
            template_values = {
                'attraction': attraction,
                'errors': errors
            }
            
            self.output('edit', 'html', template_values)
            
        else:
            
            next = attractionId
            while next: # walk to newest version of this attraction
                query = Attraction.all()
                query.filter("id =", next)
                latestAttraction = query.get()
                next = latestAttraction.next
            
            #try:
            newAttraction = self.saveAttraction(latestAttraction, attraction)
            
            
            user = self.getUserObject() # create user object if it doesn't exist
            
            # update stats
            self.addStat(user, 1) # new edit
            self.addStat(user, 2, newAttraction.region) # edit location
            if newAttraction.picture != '' and latestAttraction.picture == '':
                self.addStat(user, 4) # new picture
            if 'dupe' in newAttraction.tags and 'dupe' not in latestAttraction.tags:
                self.addStat(user, 5) # new dupe tag added
            if 'delete' in newAttraction.tags and 'delete' not in latestAttraction.tags:
                self.addStat(user, 12) # new delete tag added
            if newAttraction.name == latestAttraction.name \
                and newAttraction.description == latestAttraction.description \
                and newAttraction.href == latestAttraction.href \
                and newAttraction.picture == latestAttraction.picture \
                and newAttraction.tags == latestAttraction.tags:
                self.addStat(user, 8) # no change idiot
            
            # type edit
            #for badge in {50: 'beach', 51: 'forest', 52: 'castle', 53: 'church', 54: 'garden', 55: 'park', 56: 'zoo', 57: 'sport', 58: 'shop', 59: 'historic', 60: 'museum'}.items():
                #if badge[1] in newAttraction.tags:
            for badge in self.badges.items():
                try:
                    if badge[1]['tag'] and badge[1]['tag'] in newAttraction.tags:
                        self.addStat(user, 11, badge[0])
                except KeyError:
                    pass
            
            newBadges = self.updateBadges(user)
            user.put()
            
            
            if newBadges:
                self.redirect('/badges/%s.html' % newBadges.pop(0))
            else:
                self.redirect('/attractions/' + newAttraction.id + '.html')
            return
            
            #except:
            
            template_values = {
                'attraction': attraction,
                'errors': {
                    'save': True
                }
            }
            
            self.output('edit', 'html', template_values)

    def saveAttraction(self, latestAttraction, attraction):
        
        oldGeoBoxId = self.calcGeoBoxId(latestAttraction.location.lat, latestAttraction.location.lon)
        newGeoBoxId = self.calcGeoBoxId(attraction['location']['lat'], attraction['location']['lon'])
        
        from models.geobox import GeoBox
        
        geobox = GeoBox.all()
        geobox.filter("lat =", oldGeoBoxId[0])
        geobox.filter("lon =", oldGeoBoxId[1])
        oldGeoBox = geobox.get()
        
        if oldGeoBox == None:
            oldGeoBox = GeoBox(
                lat = oldGeoBoxId[0],
                lon = oldGeoBoxId[1]
            )
            oldGeoBox.put()
        
        db.run_in_transaction(self.removeFromGeoBox, oldGeoBox.key(), latestAttraction.id)
        
        try:
            newAttraction = db.run_in_transaction(self.createAttraction, latestAttraction.key(), attraction)
            
            geobox = GeoBox.all()
            geobox.filter("lat =", newGeoBoxId[0])
            geobox.filter("lon =", newGeoBoxId[1])
            newGeoBox = geobox.get()
            
            if newGeoBox == None:
                newGeoBox = GeoBox(
                    lat = newGeoBoxId[0],
                    lon = newGeoBoxId[1]
                )
                newGeoBox.put()
            
            db.run_in_transaction(self.addToGeoBox, newGeoBox.key(), newAttraction.id)
            
            return newAttraction
            
        except db.TransactionFailedError: # undo geobox update
            db.run_in_transaction(self.addToGeoBox, oldGeoBox.key(), latestAttraction.id)
    
    def calcGeoBoxId(self, lat, lon):
        return (round(float(lat), 1), round(float(lon), 1))
    
    def addToGeoBox(self, key, attractionId):
        geoBox = db.get(key)
        try:
            geoBox.attractions.append(attractionId)
            geoBox.put()
        except:
            pass
    
    def removeFromGeoBox(self, key, attractionId):
        geoBox = db.get(key)
        try:
            geoBox.attractions.remove(attractionId)
            geoBox.put()
        except:
            pass
    
    def createAttraction(self, key, attractionData):
        
        from google.appengine.api import users
        import urllib
        from django.utils import simplejson
        
        oldAttraction = db.get(key)
        
        user = users.get_current_user()
        if type(user) == users.User:
            attractionData['userid'] = self.getUserId(user.email())
            attractionData['username'] = user.nickname()
        else:
            attractionData['userid'] = self.getUserId(self.request.remote_addr)
            attractionData['username'] = self.request.remote_addr
        
        url = "http://maps.google.com/maps/geo?q=%.2f,%.2f&sensor=false" % (float(attractionData['location']['lat']), float(attractionData['location']['lon']))
        jsonString = urllib.urlopen(url).read()
        if jsonString:
            data = simplejson.loads(jsonString)
            try:
                if (
                    'Country' in data['Placemark'][0]['AddressDetails'] and 
                    'AdministrativeArea' in data['Placemark'][0]['AddressDetails']['Country'] and
                    'SubAdministrativeArea' in data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea'] and
                    'SubAdministrativeAreaName' in data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea'] and
                    'CountryName' in data['Placemark'][0]['AddressDetails']['Country']
                ):
                    region = "%s, %s" % (
                        data['Placemark'][0]['AddressDetails']['Country']['AdministrativeArea']['SubAdministrativeArea']['SubAdministrativeAreaName'],
                        data['Placemark'][0]['AddressDetails']['Country']['CountryName']
                    )
                else:
                    region = 'Unknown location'
            except KeyError:
                region = 'Unknown location'
        else:
            region = 'Unknown location'
        
        newAttraction = Attraction(
            parent = oldAttraction,
            root = oldAttraction.root,
            previous = oldAttraction.id,
            name = attractionData['name'],
            region = region,
            description = attractionData['description'],
            location = db.GeoPt(
                lat = attractionData['location']['lat'],
                lon = attractionData['location']['lon']
            ),
            href = attractionData['href'],
            picture = attractionData['picture'],
            tags = attractionData['tags'],
            free = oldAttraction.free,
            rating = oldAttraction.rating,
            userid = attractionData['userid'],
            username = attractionData['username']
        )
        
        import md5
        newAttraction.id = md5.new(unicode(newAttraction)).hexdigest()
        oldAttraction.next = newAttraction.id
        
        oldAttraction.put()
        newAttraction.put()
        
        return newAttraction
