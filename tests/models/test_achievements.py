# -*- coding: utf-8 -*-
from datetime import datetime
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString
from nose.tools import eq_, assert_is_not_none

from skylines import model, create_app
from skylines.model import db

import config

from tests import setup_db, teardown_db, clean_db


class TestAchievements(object):

    # Create an empty database before we start our tests for this module
    @classmethod
    def setup_class(cls):
        """Function called by nose on module load"""
        cls.app = create_app(config_file=config.TESTING_CONF_PATH)

        with cls.app.app_context():
            setup_db()

    # Tear down that database
    @classmethod
    def teardown_class(cls):
        """Function called by nose after all tests in this module ran"""
        with cls.app.app_context():
            teardown_db()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()

        clean_db()

        # Create a pilot
        self.pilot = model.User(first_name='Michael', last_name='Sommer')
        db.session.add(self.pilot)

        self.follower = model.User(first_name='Sebastian', last_name='Kawa')
        db.session.add(self.follower)

        model.Follower.follow(self.follower, self.pilot)

    def tearDown(self):
        clean_db()
        db.session.rollback()
        self.context.pop()

    def create_sample_igc_file(self, fname):
        igc = model.IGCFile(filename=fname,
                            md5=str(hash(fname)),
                            owner=self.pilot,
                            date_utc=datetime(2013, 7, 7, 13, 0))
        return igc

    def create_sample_flight(self, igc_file):
        flight = model.Flight()
        flight.igc_file = igc_file
        flight.pilot = self.pilot

        flight.timestamps = []

        coordinates = [(0, 0), (1, 1)]
        linestring = LineString(coordinates)
        flight.locations = from_shape(linestring, srid=4326)

        flight.takeoff_time = datetime(2013, 7, 7, 13, 0)
        flight.landing_time = datetime(2013, 7, 7, 18, 0)
        flight.date_local = datetime(2013, 7, 7, 13, 0)
        return flight

    def test_unlock_flight_achievements_simple(self):
        from skylines.model.achievement import unlock_flight_achievements
        igc = self.create_sample_igc_file('f1.igc')
        flight = self.create_sample_flight(igc)
        db.session.add(flight)
        db.session.flush()

        unlock_flight_achievements(flight)
        db.session.flush()

        # Make sure achievements are unlocked
        eq_([a.name for a in self.pilot.achievements],
            ['duration-3', 'duration-5'])

        # Make sure events are created. We expect 2 event: for both unlocked
        # achievements
        events = list(model.Event.query())
        eq_(len(events), 2)
        eq_([(e.type, e.actor_id, e.flight_id) for e in events],
            [(model.Event.Type.ACHIEVEMENT, self.pilot.id, flight.id),
             (model.Event.Type.ACHIEVEMENT, self.pilot.id, flight.id)])

        assert_is_not_none(events[0].achievement_id)

        # Both pilot and his follower should receive notifications for both
        # achievements
        eq_(model.Notification.count_unread(self.pilot), 2)
        eq_(model.Notification.count_unread(self.follower), 2)

    def test_unlock_flight_achievements_correct_order(self):
        from skylines.model.achievement import unlock_flight_achievements
        # Create two flights
        igc1 = self.create_sample_igc_file('f1.igc')
        flight1 = self.create_sample_flight(igc1)
        flight1.takeoff_time = datetime(2013, 7, 7, 13, 0)
        flight1.landing_time = datetime(2013, 7, 7, 18, 0)
        flight1.date_local = datetime(2013, 7, 7, 13, 0)
        db.session.add(flight1)

        # Second flight was made before flight1, and only lasted 4 hours (so, 5
        # hour achievement is not earned for it)
        igc2 = self.create_sample_igc_file('f2.igc')
        flight2 = self.create_sample_flight(igc2)
        flight2.takeoff_time = datetime(2013, 7, 6, 13, 0)
        flight2.landing_time = datetime(2013, 7, 6, 17, 0)
        flight2.date_local = datetime(2013, 7, 6, 13, 0)
        db.session.add(flight2)
        db.session.flush()

        # We first unlock achievements for flight1, and then for earlier
        # flight2
        unlock_flight_achievements(flight1)
        db.session.flush()
        unlock_flight_achievements(flight2)
        db.session.flush()

        # Expect 'duration-3' achievement to be reassociated with flight2
        eq_([a.name for a in self.pilot.achievements],
            ['duration-3', 'duration-5'])

        eq_([a.name for a in flight1.achievements], ['duration-5'])
        eq_([a.name for a in flight2.achievements], ['duration-3'])

        # Event for duration-3 achievement should be reassociated too
        event1 = model.Event.query(flight_id=flight1.id).one()
        assert_is_not_none(event1)
        eq_(event1.achievement, flight1.achievements[0])
        eq_(event1.achievement.time_achieved, datetime(2013, 7, 7, 18, 0))

        event2 = model.Event.query(flight_id=flight2.id).one()
        assert_is_not_none(event2)
        eq_(event2.achievement, flight2.achievements[0])
        eq_(event2.achievement.time_achieved, datetime(2013, 7, 6, 17, 0))

    def test_user_upload_achievements(self):
        from skylines.lib.achievements import SkylinesAchievementDataCollector

        # Create two flights
        igc1 = self.create_sample_igc_file('f1.igc')
        flight1 = self.create_sample_flight(igc1)
        db.session.add(flight1)

        # Second flight was made before flight1, and only lasted 4 hours (so, 5
        # hour achievement is not earned for it)
        igc2 = self.create_sample_igc_file('f2.igc')
        flight2 = self.create_sample_flight(igc2)
        db.session.add(flight2)
        db.session.flush()

        sadc = SkylinesAchievementDataCollector(self.pilot)
        eq_(sadc.tracks_uploaded, 2)

    def test_users_followed(self):
        from skylines.lib.achievements import SkylinesAchievementDataCollector

        db.session.flush()

        sadc_pilot = SkylinesAchievementDataCollector(self.pilot)
        sadc_follower = SkylinesAchievementDataCollector(self.follower)

        eq_(sadc_pilot.users_followed, 0)
        eq_(sadc_follower.users_followed, 1)

    def test_followers_attracted(self):
        from skylines.lib.achievements import SkylinesAchievementDataCollector

        db.session.flush()

        sadc_pilot = SkylinesAchievementDataCollector(self.pilot)
        sadc_follower = SkylinesAchievementDataCollector(self.follower)

        eq_(sadc_pilot.followers_attracted, 1)
        eq_(sadc_follower.followers_attracted, 0)

    def test_comments_made(self):
        from skylines.lib.achievements import SkylinesAchievementDataCollector
        from skylines.model.flight_comment import FlightComment

        # Create flight
        igc1 = self.create_sample_igc_file('f1.igc')
        flight1 = self.create_sample_flight(igc1)
        db.session.add(flight1)

        # Create comment by user
        FlightComment(user=self.pilot, flight=flight1, text='Nice flight!')
        db.session.flush()

        sadc_pilot = SkylinesAchievementDataCollector(self.pilot)
        sadc_follower = SkylinesAchievementDataCollector(self.follower)

        eq_(sadc_pilot.comments_made, 1)
        eq_(sadc_follower.comments_made, 0)
