-- Seed generated for family Zangvogel (Huismus, Spreeuw)
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Zangvogel', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Zangvogel'), 'Huismus', 'HM') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, abbreviation) VALUES ((SELECT id FROM families WHERE name = 'Zangvogel'), 'Spreeuw', 'SPR') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Nest') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Nest en FL') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Nest') ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('SMP Nest en FL') ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus'), (SELECT id FROM functions WHERE name = 'Nest'), 2, 2, 10, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 6, 4, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Spreeuw'), (SELECT id FROM functions WHERE name = 'Nest'), 2, 2, 10, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 6, 4, 'droog', NULL, NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Spreeuw') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus'), (SELECT id FROM functions WHERE name = 'Nest en FL'), 2, 4, 10, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 6, 4, 'droog', '1-2 uur na zonsopkomst', NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus') AND function_id = (SELECT id FROM functions WHERE name = 'Nest en FL') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus'), (SELECT id FROM functions WHERE name = 'SMP Nest'), 2, 3, 14, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 5, 4, 'droog', '1-2 uur na zonsopkomst', NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)  
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Spreeuw'), (SELECT id FROM functions WHERE name = 'SMP Nest'), 2, 3, 14, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 5, 4, 'droog', '1-2 uur na zonsopkomst', NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Spreeuw') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus'), (SELECT id FROM functions WHERE name = 'SMP Nest en FL'), 2, 4, 14, 'dagen', 'SUNRISE', 60, NULL, NULL, NULL, NULL, 5, 4, 'droog', '1-2 uur na zonsopkomst', NULL, NULL, false, false, false, false);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-04-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-04-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Zangvogel' AND s.name = 'Huismus') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Nest en FL') ORDER BY id DESC LIMIT 1) AS p(id);
