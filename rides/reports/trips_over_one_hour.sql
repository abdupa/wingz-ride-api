-- Count of trips whose pickup-to-dropoff duration exceeded one hour,
-- grouped by month and driver.
--
-- The events are collapsed per ride before joining, rather than joining
-- ride_event twice -- once for the pickup and once for the dropoff. That
-- second approach reads more naturally and is wrong: if a ride has two pickup
-- events the join multiplies its rows and the trip is counted twice. Nothing
-- errors; the totals simply come out too high and look entirely plausible.
--
-- "user" is quoted because it is a reserved word in PostgreSQL.

WITH trip AS (
    SELECT
        e.id_ride,
        MIN(e.created_at) FILTER (WHERE e.description = 'Status changed to pickup')
            AS picked_up_at,
        MAX(e.created_at) FILTER (WHERE e.description = 'Status changed to dropoff')
            AS dropped_off_at
    FROM ride_event e
    WHERE e.description IN ('Status changed to pickup', 'Status changed to dropoff')
    GROUP BY e.id_ride
)
SELECT
    -- AT TIME ZONE 'UTC' is not decoration. created_at is a timestamptz,
    -- and to_char formats it in whatever timezone the session happens to
    -- be set to. A trip picked up at 23:30 on the last day of a month
    -- would land in the next month for a session eight hours ahead. The
    -- report must not depend on who is running it.
    to_char(t.picked_up_at AT TIME ZONE 'UTC', 'YYYY-MM')  AS "Month",
    d.first_name || ' ' || LEFT(d.last_name, 1)           AS "Driver",
    COUNT(*)                                              AS "Count of Trips > 1 hr"
FROM trip t
JOIN ride   r ON r.id_ride = t.id_ride
JOIN "user" d ON d.id_user = r.id_driver
WHERE t.picked_up_at   IS NOT NULL          -- a trip that never started
  AND t.dropped_off_at IS NOT NULL          -- or is still running
  AND t.dropped_off_at - t.picked_up_at > INTERVAL '1 hour'   -- strictly more
-- Grouped by the driver's id, not by the rendered name: two drivers called
-- Chris Hernandez and Chris Huang both display as "Chris H" and would
-- otherwise be silently merged into one row.
GROUP BY 1, d.id_user
ORDER BY 1, 2;
