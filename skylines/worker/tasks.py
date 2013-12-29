from __future__ import absolute_import
from celery.utils.log import get_task_logger

from skylines.lib.xcsoar_ import analysis
from skylines.worker.celery import celery
from skylines.model import db, Flight
from skylines.model.achievement import unlock_flight_achievements

logger = get_task_logger(__name__)


@celery.task
def analyse_flight(flight_id, full=2048, triangle=6144, sprint=512):
    logger.info("Analysing flight %d" % flight_id)

    flight = Flight.get(flight_id)
    success = analysis.analyse_flight(flight, full, triangle, sprint)

    if not success:
        logger.warn("Analysis of flight %d failed." % flight_id)
        return

    unlock_flight_achievements(flight)

    db.session.commit()
