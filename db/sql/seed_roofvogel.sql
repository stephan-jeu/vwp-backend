-- Seed generated for family Roofvogel protocols
SET statement_timeout = 0;
INSERT INTO families (name, priority) VALUES ('Roofvogel', 5) ON CONFLICT (name) DO NOTHING;
INSERT INTO functions (name) VALUES ('Nest') ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Buizerd', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Sperwer', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Slechtvalk', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Havik', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Wespendief', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Boomvalk', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO species (family_id, name, name_latin) VALUES ((SELECT id FROM families WHERE name = 'Roofvogel'), 'Ransuil', NULL) ON CONFLICT (name) DO NOTHING;
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Buizerd'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 10, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', 'Overdag', NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-03-01', DATE '2000-03-15', true, NULL),
  (2, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (3, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (4, DATE '2000-05-01', DATE '2000-05-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Buizerd') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Sperwer'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 10, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', 'Overdag', NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-03-01', DATE '2000-03-15', true, NULL),
  (2, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (3, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (4, DATE '2000-07-01', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Sperwer') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Slechtvalk'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 20, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', 'Overdag', NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-02-01', DATE '2000-03-15', true, NULL),
  (2, DATE '2000-02-01', DATE '2000-03-15', true, NULL),
  (3, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (4, DATE '2000-06-01', DATE '2000-06-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Slechtvalk') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Havik'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 10, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', 'Overdag', NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-03-01', DATE '2000-03-15', true, NULL),
  (2, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (3, DATE '2000-03-16', DATE '2000-04-30', true, NULL),
  (4, DATE '2000-06-01', DATE '2000-06-30', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Havik') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Wespendief'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 20, 'dagen', NULL, NULL, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', 'Overdag', NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (3, DATE '2000-06-16', DATE '2000-07-15', true, NULL),
  (4, DATE '2000-07-16', DATE '2000-08-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Wespendief') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Boomvalk'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 20, 'dagen', 'sunset', -60, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', NULL, NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-05-01', DATE '2000-05-15', true, NULL),
  (2, DATE '2000-05-16', DATE '2000-08-15', true, NULL),
  (3, DATE '2000-05-16', DATE '2000-08-15', true, NULL),
  (4, DATE '2000-05-16', DATE '2000-08-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Boomvalk') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
INSERT INTO protocols (species_id, function_id, visits, visit_duration_hours, min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) VALUES ((SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Ransuil'), (SELECT id FROM functions WHERE name = 'Nest'), 4, 2.0, 20, 'dagen', 'sunset', 0, NULL, NULL, NULL, NULL, NULL, 3, 'Droog', NULL, NULL, 'Geen vrieskou; Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil.', false, false, false, false, NULL);
INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)
SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label
FROM (VALUES
  (1, DATE '2000-02-15', DATE '2000-03-15', true, NULL),
  (2, DATE '2000-03-16', DATE '2000-04-15', true, NULL),
  (3, DATE '2000-05-15', DATE '2000-06-15', true, NULL),
  (4, DATE '2000-06-16', DATE '2000-07-15', true, NULL)
) AS v(visit_index, window_from, window_to, required, label),
LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = 'Roofvogel' AND s.name = 'Ransuil') AND function_id = (SELECT id FROM functions WHERE name = 'Nest') ORDER BY id DESC LIMIT 1) AS p(id);
