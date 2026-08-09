SELECT
  dimension,
  item,
  SUM(observations) AS observations,
  SUM(instances) AS instances,
  MAX(maximum) AS maximum,
  CASE
    WHEN SUM(observations) = 0 THEN 0
    ELSE ROUND(1.0 * SUM(instances) / SUM(observations), 2)
  END AS average_instances_per_observation
FROM usage_aggregates
GROUP BY dimension, item
ORDER BY dimension, observations DESC, item;
