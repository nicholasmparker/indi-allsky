import math
import socket
import ssl
import json
import requests
import logging

from threading import Thread

requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)


logger = logging.getLogger('indi_allsky')


class AdsbAircraftHttpWorker(Thread):
    def __init__(
        self,
        idx,
        config,
        adsb_aircraft_q,
        latitude,
        longitude,
        elevation,
    ):
        super(AdsbAircraftHttpWorker, self).__init__()

        self.name = 'AdsbHttp-{0:d}'.format(idx)

        self.config = config
        self.adsb_aircraft_q = adsb_aircraft_q

        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation


    def run(self):
        url = self.config.get('ADSB', {}).get('DUMP1090_URL')

        username = self.config.get('ADSB', {}).get('USERNAME')
        password = self.config.get('ADSB', {}).get('PASSWORD')

        cert_bypass = self.config.get('ADSB', {}).get('CERT_BYPASS', True)


        if username:
            basic_auth = requests.auth.HTTPBasicAuth(username, password)
        else:
            basic_auth = None


        if cert_bypass:
            verify = False
        else:
            verify = True


        try:
            r = requests.get(
                url,
                allow_redirects=True,
                verify=verify,
                auth=basic_auth,
                timeout=(4.0, 2.0),
            )
        except socket.gaierror as e:
            logger.error('Socket error: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except socket.timeout as e:
            logger.error('Socket timeout: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except requests.exceptions.ConnectTimeout as e:
            logger.error('Connect timeout: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except requests.exceptions.ConnectionError as e:
            logger.error('Connect error: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except requests.exceptions.ReadTimeout as e:
            logger.error('Read timeout: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except ssl.SSLCertVerificationError as e:
            logger.error('SSL Certificate Validation failed: %s', str(e))
            self.adsb_aircraft_q.put([])
            return
        except requests.exceptions.SSLError as e:
            logger.error('SSL Error: %s', str(e))
            self.adsb_aircraft_q.put([])
            return



        if r.status_code >= 400:
            logger.error('URL returned %d', r.status_code)
            self.adsb_aircraft_q.put([])
            return


        try:
            r_data = r.json()
        except json.JSONDecodeError as e:
            logger.error('JSON decode error: %s', str(e))
            self.adsb_aircraft_q.put([])
            return


        aircraft_data = self.adsb_calculate(r_data)


        self.adsb_aircraft_q.put(aircraft_data)


    def adsb_calculate(self, adsb_data):
        alt_min_deg = self.config.get('ADSB', {}).get('ALT_DEG_MIN', 20.0)


        aircraft_list = []

        for aircraft in adsb_data.get('aircraft', []):
            if isinstance(aircraft.get('altitude'), str):
                # value might be 'ground' if landed
                continue
            elif isinstance(aircraft.get('altitude'), type(None)):
                #logger.warning('Aircraft without altitude')
                continue

            try:
                aircraft_lat = float(aircraft['lat'])
                aircraft_lon = float(aircraft['lon'])
                aircraft_altitude_m = int(aircraft['altitude']) * 0.3048  # convert to meters
            except KeyError as e:  # noqa: F841
                #logger.error('KeyError: %s', str(e))
                continue


            aircraft_flight = aircraft.get('flight')
            aircraft_squawk = aircraft.get('squawk')
            aircraft_hex = aircraft.get('hex')


            if aircraft_flight:
                aircraft_flight = aircraft_flight.rstrip()


            if aircraft_flight:
                aircraft_id = str(aircraft_flight)
            elif aircraft_squawk:
                aircraft_id = str(aircraft_squawk)
            elif aircraft_hex:
                aircraft_id = str(aircraft_hex)
            else:
                aircraft_id = 'Unknown'


            aircraft_distance_m = self.haversine(self.longitude, self.latitude, aircraft_lon, aircraft_lat)


            # calculate observer info (alt/az astronomy terms)
            aircraft_alt = math.degrees(math.atan(aircraft_altitude_m / aircraft_distance_m))  # not offsetting by local elevation


            lat_dist_m = self.haversine(self.longitude, self.latitude, self.longitude, aircraft_lat)
            long_dist_m = self.haversine(self.longitude, self.latitude, aircraft_lon, self.latitude)

            if self.latitude > aircraft_lat:
                lat_dist_m *= -1

            if self.longitude > aircraft_lon:
                long_dist_m *= -1


            aircraft_angle = math.degrees(math.atan2(lat_dist_m, long_dist_m))


            if aircraft_angle > 90:
                aircraft_az = 450 - aircraft_angle
            else:
                aircraft_az = 90 - aircraft_angle


            if aircraft_distance_m > 75000:
                logger.warning('Aircraft more than 75km away, geographic lat/long may be wrong')


            #aircraft_distance_nmi = aircraft_distance_m * 0.0005399568
            aircraft_altitude_km = aircraft_altitude_m / 1000
            aircraft_distance_km = aircraft_distance_m / 1000


            if aircraft_alt < alt_min_deg:
                logger.info('Aircraft below minimum visual altitude: %s %0.1f alt / %0.1f az (%0.1fkm)', aircraft_id, aircraft_alt, aircraft_az, aircraft_distance_km)
                continue


            logger.info(
                'Aircraft: %s, altitude: %0.1fkm, distance: %0.1fkm, alt: %0.1f, az: %0.1f',
                aircraft_id,
                aircraft_altitude_km,
                aircraft_distance_km,
                aircraft_alt,
                aircraft_az,
            )

            aircraft_list.append({
                'id'        : aircraft_id,
                'flight'    : aircraft_flight,
                'squawk'    : aircraft_squawk,
                'hex'       : aircraft_hex,
                'altitude'  : aircraft_altitude_km,
                'distance'  : aircraft_distance_km,
                'alt'       : aircraft_alt,
                'az'        : aircraft_az,
            })


        # sort by most visible aircraft
        sorted_aircraft_list = sorted(aircraft_list, key=lambda x: x['alt'], reverse=True)


        return sorted_aircraft_list


    def haversine(self, lon1, lat1, lon2, lat2):
        """
        Calculate the great circle distance in kilometers between two points
        on the earth (specified in decimal degrees)
        """
        # convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        r = 6378100  # Radius of earth in meters
        return c * r

