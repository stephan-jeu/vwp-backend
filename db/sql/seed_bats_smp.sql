-- Seed generated for bats SMP protocols
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Vleermuis', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, abbreviation, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Laatvlieger', 'LV', 'Eptesicus serotinus') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, abbreviation, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Gewone dwergvleermuis', 'GD', 'Pipistrellus pipistrellus') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, abbreviation, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Vleermuis'), 'Ruige dwergvleermuis', 'RD', 'Pipistrellus nathusii') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Groepsvorming kraamverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Kraamverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Massawinterverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Paarverblijf') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger'), (SELECT id FROM functions WHERE name = 'SMP Groepsvorming kraamverblijf'), 2, 3.0, 10, 'dagen', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 3, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-15', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-15', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Groepsvorming kraamverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger'), (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf'), 2, 3, 20, 'dagen', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 3, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (2, DATE '2000-06-16', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis'), (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf'), 2, 3, 20, 'dagen', 'SUNSET', 0, NULL, NULL, NULL, NULL, 12, 3, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (2, DATE '2000-06-16', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger'), (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf'), 4, 2.5, 12, 'dagen', 'SUNRISE',NULL, NULL, NULL, 'SUNRISE', 0, 10, 3, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-15', DATE '2000-05-31', true, NULL),
  (2, DATE '2000-06-01', DATE '2000-06-30', true, NULL),
  (3, DATE '2000-06-01', DATE '2000-06-30', true, NULL),
  (4, DATE '2000-07-01', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Laatvlieger') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis'), (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf'), 4, 2.5, 12, 'dagen', 'SUNRISE', NULL, NULL, NULL, 'SUNRISE', 0, 10, 3, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-15', DATE '2000-05-31', true, NULL),
  (2, DATE '2000-06-01', DATE '2000-06-30', true, NULL),
  (3, DATE '2000-06-01', DATE '2000-06-30', true, NULL),
  (4, DATE '2000-07-01', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Kraamverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis'), (SELECT id FROM functions WHERE name = 'SMP Massawinterverblijf'), 2, 3.5, 10, 'dagen', 'SUNSET', 120, NULL, NULL, NULL, NULL, 15, 2, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-08-01', DATE '2000-08-31', true, NULL),
  (2, DATE '2000-08-01', DATE '2000-08-31', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Massawinterverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis'), (SELECT id FROM functions WHERE name = 'SMP Paarverblijf'), 1, 2.5, NULL, NULL, 'SUNSET', 180, NULL, NULL, NULL, NULL, 10, 3, 'droog', NULL, NULL, 'Minimaal 10 dagen na laatste massawinterverblijfbezoek', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-09-01', DATE '2000-09-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Gewone dwergvleermuis') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Ruige dwergvleermuis'), (SELECT id FROM functions WHERE name = 'SMP Paarverblijf'), 1, 2.5, NULL, NULL, 'SUNSET', 180, NULL, NULL, NULL, NULL, 10, 3, 'droog', NULL, NULL, 'Minimaal 10 dagen na laatste massawinterverblijfbezoek', false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-09-01', DATE '2000-09-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Vleermuis' AND s.name = 'Ruige dwergvleermuis') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Paarverblijf') ORDER BY id DESC LIMIT 1) AS p(id);
